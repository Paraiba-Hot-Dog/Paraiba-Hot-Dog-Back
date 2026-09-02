from pydantic import BaseModel, ConfigDict

from src.permissoes.model import TipoPermissao


class PermissaoBase(BaseModel):
    nome: TipoPermissao


class PermissaoCreate(PermissaoBase):
    pass


class PermissaoUpdate(BaseModel):
    nome: TipoPermissao


class PermissaoRead(PermissaoBase):
    id: int
    model_config = ConfigDict(from_attributes=True)
