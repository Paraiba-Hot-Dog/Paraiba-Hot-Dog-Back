"""Schemas Pydantic para validacao dos dados de Sobre Nos."""

from pydantic import BaseModel, ConfigDict, Field


class EstatisticaItem(BaseModel):
    """Item individual de estatistica (ex: 10+ anos, 4.9 nota)."""

    valor: str = Field(min_length=1, max_length=50)
    legenda: str = Field(min_length=1, max_length=100)


class SobreNosRead(BaseModel):
    """Retorno do texto e estatisticas de Sobre Nos."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    texto: str
    estatisticas: list[EstatisticaItem]


class SobreNosUpdate(BaseModel):
    """Payload para atualizacao do texto e das estatisticas."""

    texto: str = Field(min_length=10, max_length=5000)
    estatisticas: list[EstatisticaItem] = Field(min_length=3, max_length=3)


class SobreNosImagemRead(BaseModel):
    """Retorno de uma imagem do carrossel Sobre Nos."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    imagem_url: str
    ordem: int
    posicao: str | None = None


class SobreNosImagemCreate(BaseModel):
    """Criacao interna de imagem vinculada ao upload."""

    imagem_url: str = Field(min_length=1, max_length=500)
    posicao: str | None = Field(default=None, max_length=50)


class SobreNosImagemUpdate(BaseModel):
    """Atualizacao de ordem ou posicao de imagem do carrossel."""

    ordem: int | None = Field(default=None, ge=0)
    posicao: str | None = Field(default=None, max_length=50)
