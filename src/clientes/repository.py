import re

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.clientes.model import Cliente, ClienteAjustePontos, MotivoAjustePontos
from src.clientes.schema import (
    AjustePontos,
    ClienteCreate,
    ClienteFiltro,
    ClienteUpdate,
    OperacaoAjustePontos,
)
from src.usuarios.model import Usuario


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


class AjustePontosInvalido(ValueError):
    """Ajuste de pontos rejeitado por regra de negocio."""


def listar_motivos_ajuste(db: Session) -> list[MotivoAjustePontos]:
    """Lista os motivos de ajuste de pontos ativos, em ordem alfabetica."""
    return (
        db.query(MotivoAjustePontos)
        .filter(MotivoAjustePontos.ativo.is_(True))
        .order_by(MotivoAjustePontos.descricao.asc())
        .all()
    )


def _obter_usuario_id(db: Session, auth_provider_id: str | None) -> int | None:
    """Resolve o ID local do usuario autenticado a partir do ID do provedor de auth."""
    if not auth_provider_id:
        return None
    return (
        db.query(Usuario.id)
        .filter(Usuario.auth_provider_id == auth_provider_id)
        .scalar()
    )


def _aplicar_ajuste_pontos(
    db: Session,
    cliente: Cliente,
    ajuste: AjustePontos,
    auth_provider_id: str | None,
) -> None:
    """Altera o saldo do cliente e adiciona o registro de auditoria na sessao, sem commit.

    Levanta AjustePontosInvalido quando o motivo for invalido, faltar observacao
    ou a remocao deixar o saldo negativo.
    """
    motivo = (
        db.query(MotivoAjustePontos)
        .filter(MotivoAjustePontos.id == ajuste.motivo_id, MotivoAjustePontos.ativo.is_(True))
        .first()
    )
    if not motivo:
        raise AjustePontosInvalido("Motivo de ajuste invalido")
    if motivo.exige_observacao and not ajuste.observacao:
        raise AjustePontosInvalido("Observacao obrigatoria para o motivo informado")

    pontos_anterior = cliente.pontos_fidelidade
    if ajuste.operacao == OperacaoAjustePontos.remover:
        if ajuste.quantidade > pontos_anterior:
            raise AjustePontosInvalido(
                "Quantidade a remover maior que o saldo atual do cliente")
        pontos_atual = pontos_anterior - ajuste.quantidade
    else:
        pontos_atual = pontos_anterior + ajuste.quantidade

    cliente.pontos_fidelidade = pontos_atual
    db.add(
        ClienteAjustePontos(
            cliente_id=cliente.id,
            motivo_id=motivo.id,
            observacao=ajuste.observacao,
            pontos_anterior=pontos_anterior,
            pontos_atual=pontos_atual,
            usuario_id=_obter_usuario_id(db, auth_provider_id),
        )
    )


def atualizar_cliente(
    db: Session,
    cliente_id: int,
    data: ClienteUpdate,
    auth_provider_id: str | None = None,
) -> Cliente | None:
    """Atualiza os campos fornecidos do cliente e o retorna, ou None se nao encontrado.

    Quando houver ajuste de pontos, o saldo e a auditoria sao gravados na mesma
    transacao dos demais campos; em caso de AjustePontosInvalido nada e persistido.
    """
    query = db.query(Cliente).filter(Cliente.id == cliente_id, Cliente.ativo.is_(True))
    if data.ajuste_pontos:
        # Trava a linha para que ajustes simultaneos nao usem o mesmo saldo anterior.
        query = query.with_for_update()
    cliente = query.first()
    if not cliente:
        return None
    if data.ajuste_pontos:
        _aplicar_ajuste_pontos(db, cliente, data.ajuste_pontos, auth_provider_id)
    for field, value in data.model_dump(exclude_unset=True, exclude={"ajuste_pontos"}).items():
        setattr(cliente, field, value)
    db.commit()
    db.refresh(cliente)
    return cliente


def listar_ajustes_pontos(db: Session, cliente_id: int) -> list[ClienteAjustePontos]:
    """Lista o historico de ajustes de pontos do cliente, do mais recente ao mais antigo."""
    return (
        db.query(ClienteAjustePontos)
        .filter(ClienteAjustePontos.cliente_id == cliente_id)
        .order_by(ClienteAjustePontos.data_ajuste.desc(), ClienteAjustePontos.id.desc())
        .all()
    )


def excluir_cliente(db: Session, cliente_id: int) -> bool:
    """Desativa (soft delete) um cliente pelo ID. Retorna True se encontrado, False caso contrario."""
    cliente = obter_cliente(db, cliente_id)
    if not cliente:
        return False
    cliente.ativo = False
    db.commit()
    return True
