import os
import re
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette import status

from src.bi.router import router as bi_router
from src.auth.router import router as auth_router
from src.clientes.router import router as clientes_router
from src.fidelidade.router import router as fidelidade_router
from src.usuarios.router import router as usuarios_router
from src.produtos.router import router as produtos_router
from src.unidades.router import router as unidades_router
from src.permissoes.router import router as permissoes_router
from src.blog.router import router as blog_router
from src.sobre_nos.router import router as sobre_nos_router
from src.pedidos.router import router as pedidos_router
from src.institucional.router import router as institucional_router
from src.security import get_current_user

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Paraiba Hot Dog API")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


def _sanitize_validation_errors(value):
    if isinstance(value, bytes):
        return "<bytes>"
    if isinstance(value, list):
        return [_sanitize_validation_errors(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_validation_errors(item) for item in value)
    if isinstance(value, dict):
        return {
            key: _sanitize_validation_errors(item)
            for key, item in value.items()
        }
    return value


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(_request, exc):
    """Retorna erros de validacao sem tentar decodificar bytes de uploads."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": jsonable_encoder(
                _sanitize_validation_errors(exc.errors())
            )
        },
    )

# CORS: localhost (dev) + FRONTEND_BASE_URL (produção)
_frontend_url = os.getenv("FRONTEND_BASE_URL", "")
_localhost_pattern = r"http://(localhost|127\.0\.0\.1):\d+"

if _frontend_url:
    _escaped = re.escape(_frontend_url.rstrip("/"))
    _cors_regex = rf"({_localhost_pattern}|{_escaped})"
else:
    _cors_regex = _localhost_pattern

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=_cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

auth_dependencies = [Depends(get_current_user)]

app.include_router(
    auth_router,
    prefix="/auth",
    tags=["auth"],
)
app.include_router(
    clientes_router,
    prefix="/clientes",
    tags=["clientes"],
    dependencies=auth_dependencies,
)
app.include_router(
    fidelidade_router,
    prefix="/fidelidade",
    tags=["fidelidade"],
)
app.include_router(
    usuarios_router,
    prefix="/usuarios",
    tags=["usuarios"],
    dependencies=auth_dependencies,
)
app.include_router(
    produtos_router,
    prefix="/produtos",
    tags=["produtos"],
)
app.include_router(
    unidades_router,
    prefix="/unidades",
    tags=["unidades"],
)
app.include_router(
    permissoes_router,
    prefix="/permissoes",
    tags=["permissoes"],
    dependencies=auth_dependencies,
)
app.include_router(
    blog_router,
    prefix="/blog",
    tags=["blog"],
)
app.include_router(
    sobre_nos_router,
    prefix="/sobre-nos",
    tags=["sobre-nos"],
)
app.include_router(
    pedidos_router,
    prefix="/pedidos",
    tags=["pedidos"],
    dependencies=auth_dependencies,
)
app.include_router(
    institucional_router,
    prefix="/institucional",
    tags=["institucional"],
)
app.include_router(
    bi_router,
    prefix="/bi",
    tags=["bi"],
    dependencies=auth_dependencies,
)


@app.get("/")
def read_root() -> dict[str, str]:
    """Verifica se a API esta em execucao e retorna o status de saude."""
    return {"status": "ok"}
