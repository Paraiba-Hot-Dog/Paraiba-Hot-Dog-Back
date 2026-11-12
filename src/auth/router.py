import base64
import json
import os
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from src.auth import repository
from src.auth.supabase_auth import login as supabase_login
from src.database import get_db
from src.permissoes.model import Permissao
from src.usuarios.model import FuncaoUsuario, Usuario

router = APIRouter()


def _dev_auth_enabled() -> bool:
    """Verifica se o login fake local esta habilitado (apenas fora de producao)."""
    if os.getenv("RENDER") or "vercel.app" in os.getenv("FRONTEND_BASE_URL", ""):
        return False
    return os.getenv("DEV_AUTH_LOCAL_ENABLED", "true").lower() in ("1", "true")


def _gerar_token_dev_local() -> str:
    """Gera um JWT simulado com perfil de administrador para testes locais."""
    header = {"alg": "none", "typ": "JWT"}
    payload = {
        "sub": "a8845965-dc2f-4bd6-a83d-6892376927c3",
        "email": "dev@teste.com",
        "role": "authenticated",
        "user_metadata": {
            "nome": "Administrador Local",
            "funcao": "administrador",
        },
        "app_metadata": {
            "role": "administrador",
        },
        "exp": 2147483647,
    }
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{h_b64}.{p_b64}.devsignature"


def _garantir_usuario_dev_local(db: Session) -> None:
    """Garante que o usuario dev@teste.com exista no banco local com todas as permissoes."""
    email = "dev@teste.com"
    sub = "a8845965-dc2f-4bd6-a83d-6892376927c3"
    usuario = db.query(Usuario).filter(Usuario.email == email).first()
    if not usuario:
        permissoes = db.query(Permissao).all()
        usuario = Usuario(
            nome="Administrador Local",
            email=email,
            senha=None,
            funcao=FuncaoUsuario.administrador,
            unidade_id=None,
            auth_provider_id=sub,
        )
        usuario.permissoes = permissoes
        db.add(usuario)
        try:
            db.commit()
        except (IntegrityError, SQLAlchemyError):
            db.rollback()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int | None = None
    refresh_token: str | None = None


class EsqueciSenhaRequest(BaseModel):
    email: EmailStr


class EsqueciSenhaResponse(BaseModel):
    message: str
    email_status: str
    aguardar_segundos: int = 0
    link_valido_minutos: int = 30
    intervalo_segundos: int = 60
    limite_por_hora: int = 30


class RedefinirSenhaRequest(BaseModel):
    token: str | None = None
    access_token: str | None = None
    nova_senha: str = Field(min_length=8)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """Autentica um usuario via Supabase Auth e retorna o token JWT."""
    if _dev_auth_enabled() and payload.email == "dev@teste.com" and payload.password == "dev123":
        _garantir_usuario_dev_local(db)
        return LoginResponse(
            access_token=_gerar_token_dev_local(),
            token_type="bearer",
            expires_in=86400,
        )

    result = supabase_login(str(payload.email), payload.password)
    return LoginResponse(
        access_token=result["access_token"],
        token_type=result.get("token_type", "bearer"),
        expires_in=result.get("expires_in"),
        refresh_token=result.get("refresh_token"),
    )


@router.post(
    "/esqueci-senha",
    response_model=EsqueciSenhaResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def esqueci_senha(
    payload: EsqueciSenhaRequest,
    db: Session = Depends(get_db),
) -> EsqueciSenhaResponse:
    resultado = repository.solicitar_recuperacao_senha(db, str(payload.email))

    return EsqueciSenhaResponse(**resultado)


@router.post("/redefinir-senha", status_code=status.HTTP_204_NO_CONTENT)
def redefinir_senha(
    payload: RedefinirSenhaRequest,
    db: Session = Depends(get_db),
) -> None:
    repository.redefinir_senha(db, payload.token, payload.nova_senha, payload.access_token)
