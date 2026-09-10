from pydantic import BaseModel, ConfigDict, Field


class EstatisticaCard(BaseModel):
    valor: str = Field(..., min_length=1, max_length=20)
    legenda: str = Field(..., min_length=1, max_length=80)


class SobreNosUpdate(BaseModel):
    texto: str = Field(..., min_length=1)
    estatisticas: list[EstatisticaCard] = Field(..., min_length=3, max_length=3)


class SobreNosRead(SobreNosUpdate):
    id: int

    model_config = ConfigDict(from_attributes=True)
