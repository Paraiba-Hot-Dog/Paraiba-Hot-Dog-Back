from datetime import datetime
from enum import Enum
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ClienteTelefoneMixin(BaseModel):
    @field_validator("telefone", mode="before", check_fields=False)
    @classmethod
    def sanitizar_telefone(cls, value: str | None) -> str | None:
        """Remove todos os caracteres nao numericos do telefone antes da validacao."""
        if value is None:
            return value
        return re.sub(r"\D", "", str(value))


class ClienteBase(ClienteTelefoneMixin):
    nome: str = Field(..., max_length=120)
    telefone: str = Field(..., max_length=20)
    email: Optional[EmailStr] = Field(None, max_length=120)
    pontos_fidelidade: int = 0


class ClienteCreate(ClienteBase):
    pass


class ClienteRead(ClienteBase):
    id: int
    data_cadastro: datetime

    model_config = ConfigDict(from_attributes=True)


class OperacaoAjustePontos(str, Enum):
    adicionar = "adicionar"
    remover = "remover"


class AjustePontos(BaseModel):
    operacao: OperacaoAjustePontos
    quantidade: int = Field(..., gt=0)
    motivo_id: int
    observacao: Optional[str] = Field(None, max_length=255)

    @field_validator("observacao")
    @classmethod
    def normalizar_observacao(cls, value: str | None) -> str | None:
        """Remove espacos das bordas e trata observacao em branco como ausente."""
        if value is None:
            return None
        return value.strip() or None


class ClienteUpdate(ClienteTelefoneMixin):
    # O saldo de pontos so muda via ajuste_pontos, que exige motivo e gera auditoria.
    model_config = ConfigDict(extra="forbid")

    nome: Optional[str] = Field(None, max_length=120)
    telefone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = Field(None, max_length=120)
    ajuste_pontos: Optional[AjustePontos] = None


class MotivoAjustePontosRead(BaseModel):
    id: int
    descricao: str
    exige_observacao: bool

    model_config = ConfigDict(from_attributes=True)


class AjustePontosRead(BaseModel):
    id: int
    cliente_id: int
    motivo: MotivoAjustePontosRead
    observacao: Optional[str]
    pontos_anterior: int
    pontos_atual: int
    usuario_id: Optional[int]
    usuario_nome: Optional[str]
    data_ajuste: datetime

    model_config = ConfigDict(from_attributes=True)


class ClienteFiltro(ClienteTelefoneMixin):
    telefone: Optional[str] = None
    nome: Optional[str] = None
    email: Optional[EmailStr] = None
    busca: Optional[str] = Field(None, max_length=120)
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, gt=0)
