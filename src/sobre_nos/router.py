from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from src.database import get_db
from src.security import require_roles
from src.sobre_nos import repository
from src.sobre_nos.schema import SobreNosImagemCreate, SobreNosImagemRead, SobreNosImagemUpdate

router = APIRouter()
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "sobre_nos"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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

    return f"/uploads/sobre_nos/{nome_arquivo}"


def _remover_imagem_url(imagem_url: str | None) -> None:
    prefixo = "/uploads/sobre_nos/"
    if not imagem_url or not imagem_url.startswith(prefixo):
        return

    caminho = UPLOAD_DIR / imagem_url.removeprefix(prefixo)
    if caminho.exists():
        caminho.unlink()


@router.get("/imagens", response_model=list[SobreNosImagemRead])
def listar_imagens(db: Session = Depends(get_db)):
    """Lista as imagens do carrossel 'Nossa historia' ordenadas."""
    return repository.listar_imagens(db)


@router.post(
    "/imagens",
    response_model=SobreNosImagemRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("administrador"))],
)
async def criar_imagem(
    imagem: UploadFile = File(...),
    posicao: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Adiciona uma nova imagem ao carrossel via upload multipart. Requer role administrador."""
    imagem_url = await salvar_imagem_upload(imagem)
    try:
        return repository.criar_imagem(db, SobreNosImagemCreate(imagem_url=imagem_url, posicao=posicao))
    except Exception:
        _remover_imagem_url(imagem_url)
        raise


@router.patch(
    "/imagens/{imagem_id}",
    response_model=SobreNosImagemRead,
    dependencies=[Depends(require_roles("administrador"))],
)
def atualizar_imagem(imagem_id: int, data: SobreNosImagemUpdate, db: Session = Depends(get_db)):
    """Atualiza ordem/posicao de uma imagem existente. Requer role administrador."""
    return repository.atualizar_imagem(db, imagem_id, data)


@router.delete(
    "/imagens/{imagem_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("administrador"))],
)
def excluir_imagem(imagem_id: int, db: Session = Depends(get_db)):
    """Remove uma imagem do carrossel pelo ID. Requer role administrador."""
    imagem = repository.obter_imagem(db, imagem_id)
    _remover_imagem_url(imagem.imagem_url)
    repository.excluir_imagem(db, imagem_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
