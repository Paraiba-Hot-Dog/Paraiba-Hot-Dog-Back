from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.avaliacoes.model import Avaliacao
from src.avaliacoes.schema import AvaliacaoCreate
from src.clientes.model import Cliente
from src.unidades.model import Unidade


def criar_avaliacao(
    db: Session, cliente_id: int, unidade_id: int, data: AvaliacaoCreate
) -> Avaliacao:
    """Persiste uma nova avaliacao vinculada a um cliente e a uma unidade."""
    if not db.get(Cliente, cliente_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente nao encontrado",
        )
    if not db.get(Unidade, unidade_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unidade nao encontrada",
        )

    avaliacao = Avaliacao(
        cliente_id=cliente_id,
        unidade_id=unidade_id,
        **data.model_dump(),
    )
    db.add(avaliacao)
    db.commit()
    db.refresh(avaliacao)
    return avaliacao
