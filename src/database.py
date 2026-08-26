from os import getenv
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


load_dotenv()


def _build_database_url() -> str:
    """Constroi a URL de conexao com o banco de dados a partir das variaveis de ambiente."""
    database_url = getenv("DATABASE_URL")
    if database_url:
        # Supabase/Heroku usam 'postgres://' mas SQLAlchemy precisa de 'postgresql://'
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        # Garante que o driver psycopg2 seja usado
        if database_url.startswith("postgresql://") and "+" not in database_url.split("://")[0]:
            database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return database_url

    user = getenv("POSTGRES_USER", "postgres")
    password = getenv("POSTGRES_PASSWORD", "postgres")
    host = getenv("POSTGRES_HOST", "localhost")
    port = getenv("POSTGRES_PORT", "5432")
    database = getenv("POSTGRES_DB", "paraiba_hotdog_db")

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"


DATABASE_URL = _build_database_url()

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependencia FastAPI que fornece uma sessao de banco de dados e a fecha ao final da requisicao."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
