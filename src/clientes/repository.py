import re

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.clientes.model import Cliente
from src.clientes.schema import ClienteCreate, ClienteFiltro, ClienteUpdate


def _mapear_erro_integridade(error: IntegrityError) -> str:
    """Traduz um erro de integridade do banco para uma mensagem legivel ao usuario."""
    message = str(error.orig)
    if "telefone" in message:
        return "Telefone ja cadastrado"
    if "email" in message:
        return "Email ja cadastrado"
    return "Violacao de integridade"


def _escapar_like(termo: str) -> str:
    """Neutraliza os curingas do LIKE para que sejam buscados como texto literal."""
    return termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _condicao_busca(termo: str):
    """Monta a condicao OR que procura o termo em nome, email ou telefone."""
    padrao = f"%{_escapar_like(termo)}%"
    condicoes = [
        Cliente.nome.ilike(padrao, escape="\\"),
        Cliente.email.ilike(padrao, escape="\\"),
    ]
    digitos = re.sub(r"\D", "", termo)
    if digitos:
        condicoes.append(Cliente.telefone.like(f"%{digitos}%"))
    return or_(*condicoes)


def listar_clientes(db: Session, filtro: ClienteFiltro) -> list[Cliente]:
    """Lista os clientes ativos aplicando os filtros informados, em ordem alfabetica."""
    query = db.query(Cliente).filter(Cliente.ativo.is_(True))
    if filtro.telefone:
        query = query.filter(Cliente.telefone == filtro.telefone)
    if filtro.nome:
        query = query.filter(Cliente.nome.ilike(f"%{filtro.nome}%"))
    if filtro.email:
        query = query.filter(Cliente.email == filtro.email)
    termo = (filtro.busca or "").strip()
    if termo:
        query = query.filter(_condicao_busca(termo))
    return (
        query.order_by(func.lower(Cliente.nome).asc(), Cliente.id.asc())
        .offset(filtro.skip)
        .limit(filtro.limit)
        .all()
    )


def obter_cliente(db: Session, cliente_id: int) -> Cliente | None:
    """Retorna o cliente ativo pelo ID, ou None se nao encontrado."""
    return (
        db.query(Cliente)
        .filter(Cliente.id == cliente_id, Cliente.ativo.is_(True))
        .first()
    )


def criar_cliente(db: Session, data: ClienteCreate) -> Cliente:
    """Persiste um novo cliente no banco de dados e o retorna."""
    cliente = Cliente(**data.model_dump())
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


def atualizar_cliente(db: Session, cliente_id: int, data: ClienteUpdate) -> Cliente | None:
    """Atualiza os campos fornecidos do cliente e o retorna, ou None se nao encontrado."""
    cliente = obter_cliente(db, cliente_id)
    if not cliente:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(cliente, field, value)
    db.commit()
    db.refresh(cliente)
    return cliente


def excluir_cliente(db: Session, cliente_id: int) -> bool:
    """Desativa (soft delete) um cliente pelo ID. Retorna True se encontrado, False caso contrario."""
    cliente = obter_cliente(db, cliente_id)
    if not cliente:
        return False
    cliente.ativo = False
    db.commit()
    return True
