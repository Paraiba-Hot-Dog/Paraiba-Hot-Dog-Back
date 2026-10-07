from datetime import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# pylint: disable=redefined-outer-name

from src.clientes.model import Cliente
from src.database import Base, get_db
from src.main import app
from src.produtos.model import (
    Categoria,
    Produto,
    ProdutoVariacao,
    Subcategoria,
    TipoVariacao,
)
from src.unidades.model import Endereco, Unidade


TEST_DATABASE_URL = "sqlite+pysqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    """Cria uma sessao SQLite isolada para cada teste da cozinha."""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def override_get_db(db_session):
    """Substitui a dependencia get_db pela sessao de teste."""

    def _get_db():
        """Fornece a sessao fake para o FastAPI durante o teste."""
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(name="cliente")
def fixture_cliente():
    """Cria o TestClient usado nos cenarios da cozinha."""
    return TestClient(app)


@pytest.fixture
def cardapio_base(db_session):
    """Cria unidade, categoria, produto e variacao minimos para montar pedidos."""
    endereco = Endereco(
        cep="71900000",
        logradouro="Aguas Claras",
        numero="1",
        bairro="Aguas Claras",
        cidade="Brasilia",
        estado="DF",
    )
    db_session.add(endereco)
    db_session.flush()

    unidade = Unidade(
        nome="Paraiba Hot Dog Aguas Claras",
        abertura=time(16, 30),
        fechamento=time(23, 59),
        descricao="Unidade teste",
        endereco_id=endereco.id,
    )
    categoria = Categoria(nome="Hot-Dog")
    db_session.add_all([unidade, categoria])
    db_session.flush()

    subcategoria = Subcategoria(nome="Classicos", categoria_id=categoria.id)
    db_session.add(subcategoria)
    db_session.flush()

    produto = Produto(
        nome="Tradicional",
        descricao="Pao, salsicha, queijo e batata palha.",
        ativo=True,
        pontos_fidelidade_por_unidade=1,
        disponivel_todas_unidades=True,
        subcategoria_id=subcategoria.id,
    )
    db_session.add(produto)
    db_session.flush()

    variacao = ProdutoVariacao(
        produto_id=produto.id,
        nome="Tradicional",
        tipo=TipoVariacao.normal,
        preco=Decimal("19.90"),
        ativo=True,
    )
    cliente = Cliente(
        nome="Cliente Teste",
        telefone="61999990001",
        email="cliente.teste@paraibahotdog.com",
        pontos_fidelidade=0,
        ativo=True,
    )
    db_session.add_all([variacao, cliente])
    db_session.commit()

    return {"unidade": unidade, "produto": produto, "variacao": variacao, "cliente": cliente}


def _criar_pedido(cliente, cardapio_base, nome_comanda: str, quantidade: int = 1) -> dict:
    """Cria um pedido com um unico item e devolve o corpo da resposta."""
    resposta = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": cardapio_base["unidade"].id,
            "nome_comanda": nome_comanda,
            "itens": [
                {
                    "produto_variacao_id": cardapio_base["variacao"].id,
                    "quantidade": quantidade,
                    "adicional_ids": [],
                }
            ],
        },
    )
    assert resposta.status_code == 201
    return resposta.json()


def _mudar_status(cliente, pedido_id: int, status: str, lote: int = 1):
    """Dispara a mudanca de status de um lote na cozinha."""
    return cliente.patch(
        "/pedidos/cozinha/status",
        json={"pedido_id": pedido_id, "lote": lote, "status": status},
    )


def _listar_cozinha(cliente, unidade_id: int, **params):
    """Consulta a cozinha da unidade, repassando os filtros opcionais."""
    query = "&".join(f"{chave}={valor}" for chave, valor in params.items())
    sufixo = f"&{query}" if query else ""
    resposta = cliente.get(f"/pedidos/cozinha?unidade_id={unidade_id}{sufixo}")
    assert resposta.status_code == 200
    return resposta.json()


@pytest.mark.integration
def test_lote_entregue_sai_da_fila_padrao(cliente, cardapio_base):
    """Garante que um lote entregue desaparece da fila padrao da cozinha."""
    unidade_id = cardapio_base["unidade"].id
    pedido = _criar_pedido(cliente, cardapio_base, "Marcos")

    assert len(_listar_cozinha(cliente, unidade_id)) == 1

    assert _mudar_status(cliente, pedido["id"], "entregue").status_code == 200

    assert _listar_cozinha(cliente, unidade_id) == []


@pytest.mark.integration
def test_lote_entregue_aparece_com_incluir_entregues(cliente, cardapio_base):
    """Garante que o lote entregue volta a ser listado quando pedido explicitamente."""
    unidade_id = cardapio_base["unidade"].id
    pedido = _criar_pedido(cliente, cardapio_base, "Marcos", quantidade=3)
    _mudar_status(cliente, pedido["id"], "entregue")

    entregues = _listar_cozinha(cliente, unidade_id, incluir_entregues="true")

    assert len(entregues) == 1
    assert entregues[0]["pedido_id"] == pedido["id"]
    assert entregues[0]["status"] == "entregue"
    assert entregues[0]["quantidade"] == 3
    assert entregues[0]["nome_comanda"] == "Marcos"


@pytest.mark.integration
def test_fila_e_entregues_nao_se_misturam(cliente, cardapio_base):
    """Garante a separacao entre a fila pendente e o historico de entregues."""
    unidade_id = cardapio_base["unidade"].id
    entregue = _criar_pedido(cliente, cardapio_base, "Entregue")
    pendente = _criar_pedido(cliente, cardapio_base, "Pendente")
    _mudar_status(cliente, entregue["id"], "entregue")

    fila = _listar_cozinha(cliente, unidade_id)
    assert [item["pedido_id"] for item in fila] == [pendente["id"]]

    completo = _listar_cozinha(cliente, unidade_id, incluir_entregues="true")
    assert len(completo) == 2
    # Pendentes sempre antes dos entregues, para a fila nao perder o topo.
    assert completo[0]["pedido_id"] == pendente["id"]
    assert completo[0]["status"] == "aberto"
    assert completo[1]["pedido_id"] == entregue["id"]
    assert completo[1]["status"] == "entregue"


@pytest.mark.integration
def test_entregues_vem_do_mais_recente_para_o_mais_antigo(cliente, cardapio_base):
    """Garante que o historico de entregues comeca pela entrega mais recente."""
    unidade_id = cardapio_base["unidade"].id
    pedidos = [_criar_pedido(cliente, cardapio_base, f"Comanda {indice}") for indice in range(3)]
    for pedido in pedidos:
        _mudar_status(cliente, pedido["id"], "entregue")

    entregues = _listar_cozinha(cliente, unidade_id, incluir_entregues="true")

    assert [item["pedido_id"] for item in entregues] == [p["id"] for p in reversed(pedidos)]


@pytest.mark.integration
def test_limite_de_entregues_corta_os_mais_antigos(cliente, cardapio_base):
    """Garante que apenas os N entregues mais recentes sao devolvidos."""
    unidade_id = cardapio_base["unidade"].id
    pedidos = [_criar_pedido(cliente, cardapio_base, f"Comanda {indice}") for indice in range(5)]
    for pedido in pedidos:
        _mudar_status(cliente, pedido["id"], "entregue")

    entregues = _listar_cozinha(
        cliente, unidade_id, incluir_entregues="true", limite_entregues=2
    )

    assert len(entregues) == 2
    assert [item["pedido_id"] for item in entregues] == [pedidos[4]["id"], pedidos[3]["id"]]


@pytest.mark.integration
def test_limite_nao_descarta_pedidos_pendentes(cliente, cardapio_base):
    """Garante que o limite vale so para entregues e nunca corta a fila."""
    unidade_id = cardapio_base["unidade"].id
    pendentes = [_criar_pedido(cliente, cardapio_base, f"Pendente {i}") for i in range(3)]
    entregues = [_criar_pedido(cliente, cardapio_base, f"Entregue {i}") for i in range(3)]
    for pedido in entregues:
        _mudar_status(cliente, pedido["id"], "entregue")

    resposta = _listar_cozinha(
        cliente, unidade_id, incluir_entregues="true", limite_entregues=1
    )

    pendentes_retornados = [item for item in resposta if item["status"] != "entregue"]
    entregues_retornados = [item for item in resposta if item["status"] == "entregue"]
    assert len(pendentes_retornados) == len(pendentes)
    assert len(entregues_retornados) == 1


@pytest.mark.integration
def test_preparando_continua_na_fila(cliente, cardapio_base):
    """Garante que marcar como preparando nao tira o lote da fila."""
    unidade_id = cardapio_base["unidade"].id
    pedido = _criar_pedido(cliente, cardapio_base, "Marcos")

    assert _mudar_status(cliente, pedido["id"], "preparando").status_code == 200

    fila = _listar_cozinha(cliente, unidade_id)
    assert len(fila) == 1
    assert fila[0]["status"] == "preparando"


@pytest.mark.integration
def test_entregar_duas_vezes_e_idempotente(cliente, cardapio_base):
    """Garante que reenviar entregue para o mesmo lote nao vira erro."""
    unidade_id = cardapio_base["unidade"].id
    pedido = _criar_pedido(cliente, cardapio_base, "Marcos")

    assert _mudar_status(cliente, pedido["id"], "entregue").status_code == 200
    repetida = _mudar_status(cliente, pedido["id"], "entregue")

    assert repetida.status_code == 200
    assert all(item["status"] == "entregue" for item in repetida.json())
    # Continua aparecendo uma unica vez no historico, sem duplicar.
    assert len(_listar_cozinha(cliente, unidade_id, incluir_entregues="true")) == 1


@pytest.mark.integration
def test_lote_inexistente_retorna_404(cliente, cardapio_base):
    """Garante que um lote que nunca existiu continua devolvendo 404."""
    pedido = _criar_pedido(cliente, cardapio_base, "Marcos")

    resposta = _mudar_status(cliente, pedido["id"], "entregue", lote=99)

    assert resposta.status_code == 404


@pytest.mark.integration
def test_pedido_cancelado_nao_aparece_entre_os_entregues(cliente, cardapio_base):
    """Garante que cancelar um pedido o remove das duas visoes da cozinha."""
    unidade_id = cardapio_base["unidade"].id
    pedido = _criar_pedido(cliente, cardapio_base, "Marcos")
    _mudar_status(cliente, pedido["id"], "entregue")

    cancelamento = cliente.post(
        f"/pedidos/{pedido['id']}/cancelar",
        json={"motivo_cancelamento": "Cliente desistiu"},
    )
    assert cancelamento.status_code == 200

    assert _listar_cozinha(cliente, unidade_id) == []
    assert _listar_cozinha(cliente, unidade_id, incluir_entregues="true") == []


@pytest.mark.integration
def test_entregues_respeitam_o_filtro_de_unidade(cliente, cardapio_base, db_session):
    """Garante que o historico de entregues nao vaza de uma unidade para outra."""
    outro_endereco = Endereco(
        cep="70000000",
        logradouro="Asa Sul",
        numero="2",
        bairro="Asa Sul",
        cidade="Brasilia",
        estado="DF",
    )
    db_session.add(outro_endereco)
    db_session.flush()
    outra_unidade = Unidade(
        nome="Paraiba Hot Dog Asa Sul",
        abertura=time(16, 30),
        fechamento=time(23, 59),
        descricao="Segunda unidade",
        endereco_id=outro_endereco.id,
    )
    db_session.add(outra_unidade)
    db_session.commit()

    pedido = _criar_pedido(cliente, cardapio_base, "Marcos")
    _mudar_status(cliente, pedido["id"], "entregue")

    assert _listar_cozinha(cliente, outra_unidade.id, incluir_entregues="true") == []
    assert len(_listar_cozinha(cliente, cardapio_base["unidade"].id, incluir_entregues="true")) == 1
