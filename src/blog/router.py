import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from src.blog import repository
from src.blog.schema import BlogCreate, BlogMultipartCreate, BlogRead, BlogUpdate
from src.database import get_db
from src.security import get_current_user

router = APIRouter()
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "blog"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _multipart_request_body(schema: type[BaseModel]) -> dict:
    return {
        "content": {
            "multipart/form-data": {
                "schema": schema.model_json_schema(),
            },
        },
        "required": True,
    }


CRIAR_POST_REQUEST_BODY = _multipart_request_body(BlogMultipartCreate)


async def salvar_imagem_upload(imagem: UploadFile) -> str:
    """Salva uma imagem enviada via multipart e retorna a URL publica."""
    if not imagem.content_type or not imagem.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Envie um arquivo de imagem valido.",
        )

    extensao = Path(imagem.filename or "").suffix.lower()
    nome_arquivo = f"{uuid4()}{extensao}"
    caminho = UPLOAD_DIR / nome_arquivo

    with caminho.open("wb") as buffer:
        buffer.write(await imagem.read())

    return f"/uploads/blog/{nome_arquivo}"


def _erro_validacao(exc: ValidationError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors())


def _is_upload_file(value: object) -> bool:
    return hasattr(value, "read") and hasattr(value, "content_type")


def _content_type(request: Request) -> str:
    return request.headers.get("content-type", "").split(";", maxsplit=1)[0].lower()


def _unsupported_media_type() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Content-Type nao suportado.",
    )


def _imagem_obrigatoria() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=[
            {
                "type": "missing",
                "loc": ("body", "imagem"),
                "msg": "Field required",
                "input": None,
            }
        ],
    )


def _remover_imagem_url(imagem_url: str | None) -> None:
    prefixo = "/uploads/blog/"
    if not imagem_url or not imagem_url.startswith(prefixo):
        return

    caminho = UPLOAD_DIR / imagem_url.removeprefix(prefixo)
    if caminho.exists():
        caminho.unlink()


async def _blog_data_from_request(request: Request) -> BlogCreate:
    content_type = _content_type(request)
    try:
        if content_type == "multipart/form-data":
            form = await request.form()
            imagem = form.get("imagem")
            if not _is_upload_file(imagem):
                raise _imagem_obrigatoria()
            BlogMultipartCreate.model_validate(
                {
                    "titulo": form.get("titulo"),
                    "descricao": form.get("descricao"),
                    "tipo": form.get("tipo"),
                    "data": form.get("data"),
                    "imagem": b"upload",
                }
            )
            imagem_url = await salvar_imagem_upload(imagem)
            return BlogCreate.model_validate(
                {
                    "titulo": form.get("titulo"),
                    "imagem_url": imagem_url,
                    "descricao": form.get("descricao"),
                    "tipo": form.get("tipo"),
                    "data": form.get("data"),
                }
            )
        if content_type == "application/json":
            return BlogCreate.model_validate(await request.json())
        raise _unsupported_media_type()
    except ValidationError as exc:
        raise _erro_validacao(exc) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="JSON invalido.",
        ) from exc


@router.get("/", response_model=list[BlogRead])
def listar_posts(tipo: str | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Lista as postagens do blog com paginacao e filtro opcional por tipo."""
    return repository.listar_posts(db, tipo, skip, limit)


@router.post(
    "/",
    response_model=BlogRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_user)],
    openapi_extra={"requestBody": CRIAR_POST_REQUEST_BODY},
)
async def criar_post(
    request: Request,
    db: Session = Depends(get_db),
):
    """Cria uma postagem do blog via JSON ou multipart com imagem."""
    post_data = await _blog_data_from_request(request)
    try:
        return repository.criar_post(db, post_data)
    except Exception:
        _remover_imagem_url(post_data.imagem_url)
        raise


@router.get("/{post_id}", response_model=BlogRead)
def obter_post(post_id: int, db: Session = Depends(get_db)):
    """Retorna uma postagem pelo ID."""
    return repository.obter_post(db, post_id)


@router.patch(
    "/{post_id}",
    response_model=BlogRead,
    dependencies=[Depends(get_current_user)],
)
def atualizar_post(post_id: int, data: BlogUpdate, db: Session = Depends(get_db)):
    """Atualiza parcialmente uma postagem existente. Requer autenticacao."""
    return repository.atualizar_post(db, post_id, data)


@router.delete(
    "/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_user)],
)
def excluir_post(post_id: int, db: Session = Depends(get_db)):
    """Remove uma postagem do blog pelo ID. Requer autenticacao."""
    repository.excluir_post(db, post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
