from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from urllib.parse import urlencode

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.auth.model import RecuperacaoSenhaToken
from src.auth.supabase_auth import update_user as supabase_update_user
from src.config import settings
from src.email_service import enviar_recuperacao_senha
from src.usuarios.model import Usuario

MENSAGEM_RECUPERACAO = (
    "Se este e-mail estiver cadastrado, enviaremos as instrucoes para recuperar sua senha."
)


def _agora() -> datetime:
    return datetime.now(UTC)


def _normalizar_data(data: datetime) -> datetime:
    if data.tzinfo is None:
        return data.replace(tzinfo=UTC)
    return data


def _hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _link_recuperacao(token: str) -> str:
    base_url = settings.frontend_base_url.rstrip("/")
    query = urlencode({"token": token})
    return f"{base_url}/recuperar-senha?{query}"


def _buscar_usuario_por_email(db: Session, email: str) -> Usuario | None:
    return db.query(Usuario).filter(Usuario.email == email).first()


def solicitar_recuperacao_senha(db: Session, email: str) -> dict:
    usuario = _buscar_usuario_por_email(db, email)
    if usuario is None:
        return {"message": MENSAGEM_RECUPERACAO, "email_status": "skipped"}

    agora = _agora()
    db.query(RecuperacaoSenhaToken).filter(
        RecuperacaoSenhaToken.usuario_id == usuario.id,
        RecuperacaoSenhaToken.used_at.is_(None),
    ).update({"used_at": agora})

    token = token_urlsafe(32)
    db.add(
        RecuperacaoSenhaToken(
            usuario_id=usuario.id,
            token_hash=_hash_token(token),
            expires_at=agora + timedelta(minutes=settings.reset_senha_token_minutos),
            created_at=agora,
        )
    )
    db.commit()

    resultado = enviar_recuperacao_senha(email, _link_recuperacao(token))
    return {
        "message": MENSAGEM_RECUPERACAO,
        "email_status": resultado.get("status", "unknown"),
    }


def redefinir_senha(db: Session, token: str, nova_senha: str) -> None:
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

    # Atualiza senha no Supabase Auth
    supabase_update_user(usuario.auth_provider_id, password=nova_senha)
    usuario.senha = None
    token_db.used_at = agora
    db.commit()
