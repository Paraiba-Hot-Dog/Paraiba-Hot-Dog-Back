"""Testes para os endpoints de clientes."""

# Pylint doesn't understand pytest fixtures in this module.
# pylint: disable=redefined-outer-name,unused-argument

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.clientes.model import Cliente
from src.database import Base, get_db
from src.main import app

client = TestClient(app)

TEST_DATABASE_URL = "sqlite+pysqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture(scope="function")
def db_session():
    """Cria uma nova sessao de banco de dados para cada teste."""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
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
    app.dependency_overrides.clear()


@pytest.fixture
def cliente_valido(db_session):
    """Cria um cliente valido para os testes."""
    cliente = Cliente(
        nome="Maria Silva",
        telefone="83999990001",
        email="maria@email.com",
        pontos_fidelidade=3,
        ativo=True,
    )
    db_session.add(cliente)
    db_session.commit()
    db_session.refresh(cliente)
    return cliente


class TestClientes:
    """Testes para os endpoints de clientes."""

    def test_listar_clientes_vazio(self, override_get_db):
        """Testa listagem sem clientes."""
        response = client.get("/clientes/")
        assert response.status_code == 200
        assert response.json() == []

    def test_criar_cliente(self, override_get_db, monkeypatch):
        """Testa criacao de cliente com telefone sanitizado."""
        envios = []

        def fake_whatsapp(nome, telefone):
            envios.append(("whatsapp", nome, telefone))

        monkeypatch.setattr("src.clientes.router.enviar_boas_vindas", fake_whatsapp)
        payload = {
            "nome": "Joao Gabriel",
            "telefone": "(61) 9856-12117",
            "email": "joaogabriel@gmail.com",
            "pontos_fidelidade": 1,
        }
        response = client.post("/clientes/", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["nome"] == "Joao Gabriel"
        assert data["telefone"] == "61985612117"
        assert data["email"] == "joaogabriel@gmail.com"
        assert data["pontos_fidelidade"] == 1
        assert "data_cadastro" in data
        assert ("whatsapp", "Joao Gabriel", "61985612117") in envios

    def test_listar_clientes_com_filtro(self, override_get_db, cliente_valido):
        """Testa listagem com filtro por telefone."""
        response = client.get(
            "/clientes/",
            params={"telefone": cliente_valido.telefone},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == cliente_valido.id

    def test_obter_cliente_por_id(self, override_get_db, cliente_valido):
        """Testa obtencao de cliente por ID."""
        response = client.get(f"/clientes/{cliente_valido.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == cliente_valido.id
        assert data["nome"] == "Maria Silva"

    def test_obter_cliente_inexistente(self, override_get_db):
        """Testa obtencao de cliente inexistente."""
        response = client.get("/clientes/9999")
        assert response.status_code == 404
        assert "Cliente nao encontrado" in response.json()["detail"]

    def test_atualizar_cliente(self, override_get_db, cliente_valido):
        """Testa atualizacao de cliente existente."""
        payload = {"nome": "Maria Atualizada"}
        response = client.patch(f"/clientes/{cliente_valido.id}", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["nome"] == "Maria Atualizada"

    def test_atualizar_cliente_inexistente(self, override_get_db):
        """Testa atualizacao de cliente inexistente."""
        payload = {"nome": "Nao existe"}
        response = client.patch("/clientes/9999", json=payload)
        assert response.status_code == 404

    def test_excluir_cliente_soft_delete(self, override_get_db, cliente_valido):
        """Testa exclusao logica de cliente."""
        response = client.delete(f"/clientes/{cliente_valido.id}")
        assert response.status_code == 204

        response = client.get(f"/clientes/{cliente_valido.id}")
        assert response.status_code == 404

        response = client.get("/clientes/")
        assert response.status_code == 200
        assert response.json() == []

    def test_excluir_cliente_inexistente(self, override_get_db):
        """Testa exclusao de cliente inexistente."""
        response = client.delete("/clientes/9999")
        assert response.status_code == 404

    def test_conflito_telefone(self, override_get_db, cliente_valido):
        """Testa conflito de telefone duplicado."""
        payload = {
            "nome": "Outro",
            "telefone": cliente_valido.telefone,
            "email": "outro@email.com",
            "pontos_fidelidade": 0,
        }
        response = client.post("/clientes/", json=payload)
        assert response.status_code == 409
        assert "Telefone ja cadastrado" in response.json()["detail"]

    def test_validacao_email(self, override_get_db):
        """Testa validacao de email invalido."""
        payload = {
            "nome": "Invalido",
            "telefone": "83999990002",
            "email": "email-invalido",
            "pontos_fidelidade": 0,
        }
        response = client.post("/clientes/", json=payload)
        assert response.status_code == 422


@pytest.fixture
def clientes_variados(db_session):
    """Cria clientes fora de ordem alfabetica para exercitar busca e ordenacao."""
    dados = [
        ("Carla Souza", "61988887777", "carla@teste.com", True),
        ("ana costa", "61999990001", "ana.costa@example.com", True),
        ("carlos Andrade", "61977776666", "carlos@teste.com", True),
        ("Bruno Dias", "61999990002", "bruno@example.com", True),
        ("Zelia Inativa", "61911112222", "zelia@example.com", False),
    ]
    clientes = [
        Cliente(
            nome=nome,
            telefone=telefone,
            email=email,
            pontos_fidelidade=0,
            ativo=ativo,
        )
        for nome, telefone, email, ativo in dados
    ]
    db_session.add_all(clientes)
    db_session.commit()
    return clientes


def _nomes(response) -> list[str]:
    """Extrai a lista de nomes do corpo de uma resposta de listagem."""
    return [cliente["nome"] for cliente in response.json()]


class TestListagemClientes:
    """Testes de busca, ordenacao e paginacao da listagem de clientes."""

    def test_ordena_por_nome_em_ordem_alfabetica(self, override_get_db, clientes_variados):
        """A listagem sai em ordem alfabetica, ignorando maiusculas e a ordem de insercao."""
        response = client.get("/clientes/")
        assert response.status_code == 200
        assert _nomes(response) == [
            "ana costa",
            "Bruno Dias",
            "Carla Souza",
            "carlos Andrade",
        ]

    def test_busca_por_nome_parcial_ignora_maiusculas(self, override_get_db, clientes_variados):
        """A busca encontra por trecho do nome, independente de maiusculas."""
        response = client.get("/clientes/", params={"busca": "CAR"})
        assert response.status_code == 200
        assert _nomes(response) == ["Carla Souza", "carlos Andrade"]

    def test_busca_por_email_parcial(self, override_get_db, clientes_variados):
        """A busca aceita trecho de email, que nao passaria pela validacao de EmailStr."""
        response = client.get("/clientes/", params={"busca": "example.com"})
        assert response.status_code == 200
        assert _nomes(response) == ["ana costa", "Bruno Dias"]

    def test_busca_por_telefone_parcial(self, override_get_db, clientes_variados):
        """A busca encontra por trecho do telefone."""
        response = client.get("/clientes/", params={"busca": "99999"})
        assert response.status_code == 200
        assert _nomes(response) == ["ana costa", "Bruno Dias"]

    def test_busca_textual_nao_casa_com_todos_pelo_telefone(self, override_get_db, clientes_variados):
        """Termo sem digitos nao pode virar um LIKE vazio no telefone e trazer a base toda."""
        response = client.get("/clientes/", params={"busca": "ana"})
        assert response.status_code == 200
        assert _nomes(response) == ["ana costa"]

    def test_busca_escapa_curinga_do_like(self, override_get_db, clientes_variados):
        """O curinga % e tratado como texto literal, entao nao lista todos os clientes."""
        response = client.get("/clientes/", params={"busca": "%"})
        assert response.status_code == 200
        assert response.json() == []

    def test_busca_sem_resultado_retorna_lista_vazia(self, override_get_db, clientes_variados):
        """Termo que nao casa com nenhum cliente devolve lista vazia."""
        response = client.get("/clientes/", params={"busca": "zzzznaoexiste"})
        assert response.status_code == 200
        assert response.json() == []

    def test_busca_em_branco_nao_filtra(self, override_get_db, clientes_variados):
        """Busca so com espacos e tratada como ausencia de filtro."""
        response = client.get("/clientes/", params={"busca": "   "})
        assert response.status_code == 200
        assert len(response.json()) == 4

    def test_busca_ignora_clientes_inativos(self, override_get_db, clientes_variados):
        """Cliente desativado nao aparece na busca."""
        response = client.get("/clientes/", params={"busca": "Zelia"})
        assert response.status_code == 200
        assert response.json() == []

    def test_paginacao_preserva_o_filtro_de_busca(self, override_get_db, clientes_variados):
        """Paginar dentro de uma busca mantem o filtro e nao repete nem pula registros."""
        primeira = client.get("/clientes/", params={"busca": "car", "skip": 0, "limit": 1})
        segunda = client.get("/clientes/", params={"busca": "car", "skip": 1, "limit": 1})
        assert primeira.status_code == 200
        assert segunda.status_code == 200
        assert _nomes(primeira) == ["Carla Souza"]
        assert _nomes(segunda) == ["carlos Andrade"]

    def test_paginacao_sem_filtro_percorre_a_base_em_ordem(self, override_get_db, clientes_variados):
        """As paginas seguem a ordem alfabetica e cobrem a base sem sobreposicao."""
        pagina1 = client.get("/clientes/", params={"skip": 0, "limit": 2})
        pagina2 = client.get("/clientes/", params={"skip": 2, "limit": 2})
        assert _nomes(pagina1) == ["ana costa", "Bruno Dias"]
        assert _nomes(pagina2) == ["Carla Souza", "carlos Andrade"]
