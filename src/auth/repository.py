import logging
import math
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.auth.model import RecuperacaoSenhaToken
from src.auth.supabase_auth import (
    atualizar_senha_com_sessao,
    enviar_email_recuperacao as enviar_recuperacao_senha,
    update_user as supabase_update_user,
)
from src.config import settings
from src.usuarios.model import Usuario

logger = logging.getLogger(__name__)

MENSAGEM_RECUPERACAO = (
    "Se este e-mail estiver cadastrado, enviaremos as instruções para recuperar sua senha."
)
MENSAGEM_LIMITE = (
    "Já enviamos um e-mail de recuperação há pouco. Confira a caixa de entrada e o spam. "
    "Se não aparecer, espere alguns minutos antes de tentar de novo."
)


def _agora() -> datetime:
    return datetime.now(UTC)


def _normalizar_data(data: datetime) -> datetime:
    if data.tzinfo is None:
        return data.replace(tzinfo=UTC)
    return data


def _hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _pagina_redefinicao() -> str:
    return f"{settings.frontend_base_url.rstrip('/')}/recuperar-senha"


def _resposta(message: str, email_status: str, aguardar_segundos: int = 0) -> dict:
    return {
        "message": message,
        "email_status": email_status,
        "aguardar_segundos": max(aguardar_segundos, 0),
        "link_valido_minutos": settings.reset_senha_token_minutos,
        "intervalo_segundos": settings.reset_senha_intervalo_segundos,
        "limite_por_hora": settings.reset_senha_limite_por_hora,
    }


def _ultimo_pedido(db: Session, usuario_id: int) -> RecuperacaoSenhaToken | None:
    return (
        db.query(RecuperacaoSenhaToken)
        .filter(RecuperacaoSenhaToken.usuario_id == usuario_id)
        .order_by(RecuperacaoSenhaToken.created_at.desc())
        .first()
    )


def _pedidos_na_ultima_hora(db: Session, agora: datetime) -> list[RecuperacaoSenhaToken]:
    limite = agora - timedelta(hours=1)
    pedidos = db.query(RecuperacaoSenhaToken).all()
    return [
        pedido
        for pedido in pedidos
        if _normalizar_data(pedido.created_at) >= limite
    ]


def _segundos_ate(origem: datetime, agora: datetime, janela_segundos: int) -> int:
    decorrido = (agora - _normalizar_data(origem)).total_seconds()
    return max(math.ceil(janela_segundos - decorrido), 0)


def _buscar_usuario_por_email(db: Session, email: str) -> Usuario | None:
    email_normalizado = email.strip().lower()
    return (
        db.query(Usuario)
        .filter(func.lower(Usuario.email) == email_normalizado)
        .first()
    )


def solicitar_recuperacao_senha(db: Session, email: str) -> dict:
    usuario = _buscar_usuario_por_email(db, email)
    if usuario is None:
        return _resposta(MENSAGEM_RECUPERACAO, "skipped")

    agora = _agora()
    ultimo = _ultimo_pedido(db, usuario.id)
    if ultimo is not None:
        espera = _segundos_ate(ultimo.created_at, agora, settings.reset_senha_intervalo_segundos)
        if espera > 0:
            minutos = max(math.ceil(espera / 60), 1)
            unidade = "minuto" if minutos == 1 else "minutos"
            return _resposta(
                f"O link enviado expira em {minutos} {unidade}. "
                "Um novo e-mail só pode ser enviado quando ele expirar.",
                "cooldown",
                espera,
            )

    pedidos_recentes = _pedidos_na_ultima_hora(db, agora)
    if len(pedidos_recentes) >= settings.reset_senha_limite_por_hora:
        ordenados = sorted(pedidos_recentes, key=lambda pedido: _normalizar_data(pedido.created_at))
        marco = ordenados[len(ordenados) - settings.reset_senha_limite_por_hora]
        espera = _segundos_ate(marco.created_at, agora, 3600)
        return _resposta(
            "A plataforma envia no máximo "
            f"{settings.reset_senha_limite_por_hora} e-mails de recuperação por hora, "
            "somando todos os usuários. Tente novamente mais tarde.",
            "limite",
            espera,
        )

    db.query(RecuperacaoSenhaToken).filter(
        RecuperacaoSenhaToken.usuario_id == usuario.id,
        RecuperacaoSenhaToken.used_at.is_(None),
    ).update({"used_at": agora})

    token = token_urlsafe(32)
    token_db = RecuperacaoSenhaToken(
        usuario_id=usuario.id,
        token_hash=_hash_token(token),
        expires_at=agora + timedelta(minutes=settings.reset_senha_token_minutos),
        created_at=agora,
    )
    db.add(token_db)
    db.commit()

    resultado = enviar_recuperacao_senha(usuario.email, _pagina_redefinicao())
    if resultado.get("status") != "sent":
        motivo = str(resultado.get("reason") or "")
        logger.warning("Falha ao enviar e-mail de recuperacao: %s", motivo)
        db.delete(token_db)
        db.commit()
        limite = any(termo in motivo.lower() for termo in ("rate", "limit"))
        return _resposta(
            MENSAGEM_LIMITE if limite else "Não foi possível enviar o e-mail de recuperação. Tente novamente em instantes.",
            "error",
            settings.reset_senha_intervalo_segundos if limite else 0,
        )

    return _resposta(
        MENSAGEM_RECUPERACAO,
        "sent",
        settings.reset_senha_intervalo_segundos,
    )


def redefinir_senha(
    db: Session,
    token: str | None,
    nova_senha: str,
    access_token: str | None = None,
) -> None:
    if access_token:
        atualizar_senha_com_sessao(access_token, nova_senha)
        return

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de recuperacao invalido ou expirado",
        )

    token_db = (
        db.query(RecuperacaoSenhaToken)
        .filter(RecuperacaoSenhaToken.token_hash == _hash_token(token))
        .first()
    )
    agora = _agora()
    if (
        token_db is None
        or token_db.used_at is not None
        or _normalizar_data(token_db.expires_at) <= agora
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de recuperacao invalido ou expirado",
        )

    usuario = db.get(Usuario, token_db.usuario_id)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de recuperacao invalido ou expirado",
        )

    if not usuario.auth_provider_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario sem autenticacao configurada",
        )

    supabase_update_user(usuario.auth_provider_id, password=nova_senha)
    usuario.senha = None
    token_db.used_at = agora
    db.commit()
