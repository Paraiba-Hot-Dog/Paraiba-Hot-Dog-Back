"""Serviço de armazenamento de arquivos com Supabase Storage e fallback local."""

import logging
import os
import sys
from pathlib import Path
from uuid import uuid4
import httpx
from fastapi import UploadFile

from src.config import settings

logger = logging.getLogger(__name__)


async def upload_para_supabase_ou_local(
    arquivo: UploadFile,
    pasta: str,
    upload_dir_local: Path,
    conteudo: bytes | None = None,
) -> str:
    """
    Envia o arquivo para o Supabase Storage se as credenciais estiverem disponíveis.
    Em ambiente de testes automatizados ou caso o Supabase não esteja configurado,
    salva localmente em upload_dir_local.
    """
    if conteudo is None:
        conteudo = await arquivo.read()

    extensao = Path(arquivo.filename or "").suffix.lower()
    nome_arquivo = f"{uuid4()}{extensao}"

    supabase_url = settings.supabase_url or os.getenv("SUPABASE_URL", "")
    supabase_key = settings.supabase_service_role_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    esta_em_teste = os.getenv("TESTING", "").lower() in ("1", "true") or "pytest" in sys.modules

    if supabase_url and supabase_key and not esta_em_teste:
        try:
            base_url = supabase_url.rstrip("/")
            bucket_name = pasta
            caminho_storage = f"{base_url}/storage/v1/object/{bucket_name}/{nome_arquivo}"
            headers = {
                "Authorization": f"Bearer {supabase_key}",
                "apikey": supabase_key,
                "Content-Type": arquivo.content_type or "application/octet-stream",
            }
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(caminho_storage, headers=headers, content=conteudo)
                # Se o bucket não existir, cria-o como público e tenta novamente
                if res.status_code in (404, 400):
                    await client.post(
                        f"{base_url}/storage/v1/bucket",
                        headers=headers,
                        json={"id": bucket_name, "name": bucket_name, "public": True},
                    )
                    res = await client.post(caminho_storage, headers=headers, content=conteudo)

                if res.status_code in (200, 201):
                    return f"{base_url}/storage/v1/object/public/{bucket_name}/{nome_arquivo}"
                logger.warning(
                    "Supabase Storage respondeu status %d ao enviar %s: %s",
                    res.status_code,
                    nome_arquivo,
                    res.text,
                )
        except Exception as err:
            logger.warning("Falha ao comunicar com Supabase Storage: %s. Usando fallback local.", err)

    # Fallback local (usado em testes ou se o Supabase Storage estiver offline)
    upload_dir_local.mkdir(parents=True, exist_ok=True)
    caminho = upload_dir_local / nome_arquivo
    with caminho.open("wb") as buffer:
        buffer.write(conteudo)

    return f"/uploads/{pasta}/{nome_arquivo}"
