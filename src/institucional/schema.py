from pydantic import BaseModel, ConfigDict, Field


class SobreNosUpdate(BaseModel):
    texto: str = Field(..., min_length=1)


class SobreNosRead(SobreNosUpdate):
    id: int

    model_config = ConfigDict(from_attributes=True)
