from datetime import datetime
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


class ClienteUpdate(ClienteTelefoneMixin):
    nome: Optional[str] = Field(None, max_length=120)
    telefone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = Field(None, max_length=120)
    pontos_fidelidade: Optional[int] = None


class ClienteRead(ClienteBase):
    id: int
    data_cadastro: datetime

    model_config = ConfigDict(from_attributes=True)


class ClienteFiltro(ClienteTelefoneMixin):
    telefone: Optional[str] = None
    nome: Optional[str] = None
    email: Optional[EmailStr] = None
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, gt=0)
