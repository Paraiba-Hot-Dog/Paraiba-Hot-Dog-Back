from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from src.auth import repository
from src.auth.supabase_auth import login as supabase_login
from src.database import get_db

router = APIRouter()


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


class RedefinirSenhaRequest(BaseModel):
    token: str
    nova_senha: str = Field(min_length=8)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    """Autentica um usuario via Supabase Auth e retorna o token JWT."""
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

    return EsqueciSenhaResponse(
        message=resultado["message"],
        email_status=resultado["email_status"],
    )


@router.post("/redefinir-senha", status_code=status.HTTP_204_NO_CONTENT)
def redefinir_senha(
    payload: RedefinirSenhaRequest,
    db: Session = Depends(get_db),
) -> None:
    repository.redefinir_senha(db, payload.token, payload.nova_senha)
