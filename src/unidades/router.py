import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from src.database import get_db
from src.unidades import repository
from src.unidades.schema import (
    UnidadeCreate,
    UnidadeMultipartCreate,
    UnidadeMultipartUpdate,
    UnidadeRead,
    UnidadeUpdate,
)
from src.security import require_roles

router = APIRouter()
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "unidades"
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


CRIAR_UNIDADE_REQUEST_BODY = _multipart_request_body(UnidadeMultipartCreate)
ATUALIZAR_UNIDADE_REQUEST_BODY = _multipart_request_body(UnidadeMultipartUpdate)


async def salvar_imagem_upload(imagem: UploadFile) -> str:
    """Salva uma imagem de unidade enviada via multipart e retorna a URL publica."""
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

    return f"/uploads/unidades/{nome_arquivo}"


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
    prefixo = "/uploads/unidades/"
    if not imagem_url or not imagem_url.startswith(prefixo):
        return

    caminho = UPLOAD_DIR / imagem_url.removeprefix(prefixo)
    if caminho.exists():
        caminho.unlink()


async def _unidade_data_from_request(request: Request) -> UnidadeCreate:
    content_type = _content_type(request)
    try:
        if content_type == "multipart/form-data":
            form = await request.form()
            imagem = form.get("imagem")
            form_data = {
                "nome": form.get("nome"),
                "abertura": form.get("abertura"),
                "fechamento": form.get("fechamento"),
                "descricao": form.get("descricao"),
                "mapa_url": form.get("mapa_url"),
                "cep": form.get("cep"),
                "logradouro": form.get("logradouro"),
                "numero": form.get("numero"),
                "complemento": form.get("complemento"),
                "bairro": form.get("bairro"),
                "cidade": form.get("cidade"),
                "estado": form.get("estado"),
            }
            if not _is_upload_file(imagem):
                raise _imagem_obrigatoria()
            UnidadeMultipartCreate.model_validate({**form_data, "imagem": b"upload"})
            imagem_url = await salvar_imagem_upload(imagem)
            return UnidadeCreate.model_validate(
                {
                    "nome": form_data["nome"],
                    "imagem": imagem_url,
                    "abertura": form_data["abertura"],
                    "fechamento": form_data["fechamento"],
                    "descricao": form_data["descricao"],
                    "mapa_url": form_data["mapa_url"],
                    "endereco": {
                        "cep": form_data["cep"],
                        "logradouro": form_data["logradouro"],
                        "numero": form_data["numero"],
                        "complemento": form_data["complemento"],
                        "bairro": form_data["bairro"],
                        "cidade": form_data["cidade"],
                        "estado": form_data["estado"],
                    },
                }
            )
        if content_type == "application/json":
            return UnidadeCreate.model_validate(await request.json())
        raise _unsupported_media_type()
    except ValidationError as exc:
        raise _erro_validacao(exc) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="JSON invalido.",
        ) from exc


async def _unidade_update_from_request(request: Request) -> tuple[UnidadeUpdate, str | None]:
    """Interpreta JSON ou multipart/form-data e retorna (dados, nova_imagem_url)."""
    content_type = _content_type(request)
    nova_imagem_url: str | None = None
    try:
        if content_type == "multipart/form-data":
            form = await request.form()
            imagem = form.get("imagem")

            if _is_upload_file(imagem):
                nova_imagem_url = await salvar_imagem_upload(imagem)

            campos_unidade = ["nome", "abertura", "fechamento", "descricao", "mapa_url"]
            update_data: dict = {k: form.get(k) for k in campos_unidade if form.get(k) is not None}

            if nova_imagem_url:
                update_data["imagem"] = nova_imagem_url

            campos_endereco = ["cep", "logradouro", "numero", "complemento", "bairro", "cidade", "estado"]
            endereco_data = {k: form.get(k) for k in campos_endereco if form.get(k) is not None}
            if endereco_data:
                update_data["endereco"] = endereco_data

            return UnidadeUpdate.model_validate(update_data), nova_imagem_url

        if content_type == "application/json":
            return UnidadeUpdate.model_validate(await request.json()), None

        raise _unsupported_media_type()
    except ValidationError as exc:
        _remover_imagem_url(nova_imagem_url)
        raise _erro_validacao(exc) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="JSON invalido.",
        ) from exc


@router.get("/", response_model=list[UnidadeRead])
def listar_unidades(db: Session = Depends(get_db)):
    """Lista todas as unidades cadastradas."""
    return repository.listar_unidades(db)


@router.get("/{unidade_id}", response_model=UnidadeRead)
def obter_unidade(unidade_id: int, db: Session = Depends(get_db)):
    """Retorna os detalhes de uma unidade pelo ID."""
    return repository.obter_unidade(db, unidade_id)


@router.post(
    "/",
    response_model=UnidadeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("administrador"))],
    openapi_extra={"requestBody": CRIAR_UNIDADE_REQUEST_BODY},
)
async def criar_unidade(
    request: Request,
    db: Session = Depends(get_db),
):
    """Cria uma unidade via JSON ou multipart com imagem. Requer role administrador."""
    data = await _unidade_data_from_request(request)
    try:
        return repository.criar_unidade(db, data)
    except Exception:
        _remover_imagem_url(data.imagem)
        raise


@router.patch(
    "/{unidade_id}",
    response_model=UnidadeRead,
    dependencies=[Depends(require_roles("administrador"))],
    openapi_extra={"requestBody": ATUALIZAR_UNIDADE_REQUEST_BODY},
)
async def atualizar_unidade(
    request: Request,
    unidade_id: int,
    db: Session = Depends(get_db),
):
    """Atualiza parcialmente uma unidade via JSON ou multipart. Requer role administrador."""
    data, nova_imagem_url = await _unidade_update_from_request(request)

    unidade = repository.obter_unidade(db, unidade_id)
    imagem_antiga = unidade.imagem if nova_imagem_url else None

    try:
        updated = repository.atualizar_unidade(db, unidade_id, data)
    except Exception:
        _remover_imagem_url(nova_imagem_url)
        raise

    _remover_imagem_url(imagem_antiga)
    return updated


@router.delete(
    "/{unidade_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("administrador"))],
)
def excluir_unidade(unidade_id: int, db: Session = Depends(get_db)):
    """Remove uma unidade, seu endereco e sua imagem. Requer role administrador."""
    imagem_url = repository.excluir_unidade(db, unidade_id)
    _remover_imagem_url(imagem_url)
