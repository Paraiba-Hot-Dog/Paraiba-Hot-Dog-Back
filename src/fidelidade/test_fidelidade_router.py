from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.clientes.model import Cliente
from src.database import Base, get_db
from src.main import app

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


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


def test_consultar_fidelidade_por_telefone():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    try:
        db = TestingSessionLocal()
        cliente = Cliente(
            nome="Thiago",
            telefone="61985612117",
            email="thiago@example.com",
            pontos_fidelidade=7,
        )
        db.add(cliente)
        db.commit()
        db.close()

        response = client.get("/fidelidade", params={"cadastro": "(61) 98561-2117"})

        assert response.status_code == 200
        assert response.json()["nome"] == "Thiago"
        assert response.json()["pontos"] == 7
        assert response.json()["total_para_premio"] == 10
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=test_engine)


def test_consultar_fidelidade_nao_encontrado():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.get("/fidelidade", params={"cadastro": "naoexiste@example.com"})

        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=test_engine)
