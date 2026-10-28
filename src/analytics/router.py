import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from sqlalchemy.orm import Session

from src.analytics import ingestao, repository
from src.analytics.model import CanalAquisicao
from src.analytics.schema import AquisicaoRead, EventoAnalyticsCreate, PeriodoAquisicao
from src.database import get_db

# Ingestao publica: registrada sem auth_dependencies e sem ler o token.
# Fica em /eventos, fora do prefixo /analytics: a lista EasyPrivacy (uBlock
# Origin) bloqueia qualquer URL com "/analytics/event".
ingestao_router = APIRouter()

# Leitura do painel: registrada com auth_dependencies em src/main.py.
router = APIRouter()


def _rejeitar(motivo: str, status_code: int, detail: str) -> HTTPException:
    ingestao.registrar_contador(f"evento_rejeitado motivo={motivo}")
    return HTTPException(status_code=status_code, detail=detail)


async def _ler_payload(request: Request) -> EventoAnalyticsCreate:
    """Valida tamanho e formato do corpo sem ecoar o conteudo recebido."""
    tamanho_declarado = request.headers.get("content-length")
    if (
        tamanho_declarado is not None
        and tamanho_declarado.isdigit()
        and int(tamanho_declarado) > ingestao.TAMANHO_MAXIMO_PAYLOAD_BYTES
    ):
        raise _rejeitar(
            "tamanho",
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "Evento excede o tamanho maximo.",
        )

    corpo = await request.body()
    if len(corpo) > ingestao.TAMANHO_MAXIMO_PAYLOAD_BYTES:
        raise _rejeitar(
            "tamanho",
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "Evento excede o tamanho maximo.",
        )

    try:
        return EventoAnalyticsCreate.model_validate(json.loads(corpo))
    except (ValueError, ValidationError) as exc:
        raise _rejeitar(
            "payload_invalido",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Evento invalido.",
        ) from exc


@ingestao_router.post("/eventos", status_code=status.HTTP_204_NO_CONTENT)
async def registrar_evento(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """Recebe um evento anonimizado do site publico. Nao exige autenticacao.

    Trafego de fora do site ou de robos e descartado com 204, sem gravar nada,
    para nao sinalizar a regra a quem envia.
    """
    if not ingestao.origem_permitida(request.headers.get("origin")):
        ingestao.registrar_contador("evento_descartado motivo=origem", logging.INFO)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if ingestao.eh_robo(request.headers.get("user-agent")):
        ingestao.registrar_contador("evento_descartado motivo=robo", logging.INFO)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    data = await _ler_payload(request)
    await run_in_threadpool(repository.registrar_evento, db, data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/aquisicao", response_model=AquisicaoRead)
def obter_aquisicao(
    *,
    periodo: PeriodoAquisicao = Query(PeriodoAquisicao.ultimos_30_dias),
    unidade_id: int | None = Query(None, gt=0),
    canal: CanalAquisicao | None = Query(None),
    db: Session = Depends(get_db),
) -> AquisicaoRead:
    """Retorna o funil e os indicadores de aquisicao. Requer autenticacao."""
    return repository.obter_aquisicao(
        db,
        periodo=periodo,
        unidade_id=unidade_id,
        canal=canal,
    )
