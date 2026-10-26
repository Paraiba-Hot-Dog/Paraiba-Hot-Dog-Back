"""Regras de ingestao de eventos: filtro de trafego, normalizacao e canal."""

import logging
import re
from collections import Counter
from datetime import UTC, datetime
from threading import Lock
from urllib.parse import urlsplit

from src.analytics.model import CanalAquisicao
from src.config import settings

logger = logging.getLogger(__name__)

TAMANHO_MAXIMO_UTM = 100
TAMANHO_MAXIMO_REFERRER_HOST = 255
TAMANHO_MAXIMO_PAYLOAD_BYTES = 2048

_FORMATO_UTM = re.compile(r"^[a-z0-9][a-z0-9 ._+\-]*$")
_FORMATO_HOST = re.compile(
    r"^(?=.{1,255}$)[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?"
    r"(\.[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?)*$"
)

# Trechos de User-Agent de robos conhecidos (comparados em minusculas).
_TRECHOS_USER_AGENT_ROBO = (
    "bot",
    "crawler",
    "spider",
    "slurp",
    "headlesschrome",
    "phantomjs",
    "lighthouse",
    "facebookexternalhit",
    "python-requests",
    "curl/",
    "wget/",
)

_HOSTS_BUSCA = (
    re.compile(r"^(www\.)?google(\.[a-z]{2,3}){1,2}$"),
    re.compile(r"^(www\.|cn\.)?bing\.com$"),
    re.compile(r"^(www\.|html\.)?duckduckgo\.com$"),
    re.compile(r"^([a-z]{2}\.)?search\.yahoo\.com$"),
    re.compile(r"^(www\.)?ecosia\.org$"),
    re.compile(r"^(www\.)?yandex(\.[a-z]{2,3}){1,2}$"),
)

_contadores: Counter[str] = Counter()
_contadores_lock = Lock()


def registrar_contador(nome: str, nivel: int = logging.WARNING) -> None:
    """Incrementa um contador do processo e registra o total no log, sem payload."""
    with _contadores_lock:
        _contadores[nome] += 1
        total = _contadores[nome]
    logger.log(nivel, "analytics %s total=%d", nome, total)


def _origem(url: str) -> str | None:
    partes = urlsplit(url.strip().lower())
    if not partes.scheme or not partes.netloc:
        return None
    return f"{partes.scheme}://{partes.netloc}"


def origem_permitida(origin: str | None) -> bool:
    """Aceita apenas requisicoes vindas do site configurado em FRONTEND_BASE_URL."""
    if not origin:
        return False
    esperada = _origem(settings.frontend_base_url)
    return esperada is not None and _origem(origin) == esperada


def eh_robo(user_agent: str | None) -> bool:
    """Identifica User-Agents ausentes ou de robos conhecidos."""
    if not user_agent or not user_agent.strip():
        return True
    agente = user_agent.lower()
    return any(trecho in agente for trecho in _TRECHOS_USER_AGENT_ROBO)


def normalizar_utm(valor: str | None, campo: str) -> str | None:
    """Minusculas, sem espacos nas pontas e ate 100 caracteres; fora disso vira None."""
    if valor is None:
        return None
    normalizado = valor.strip().lower()
    if not normalizado:
        return None
    if len(normalizado) > TAMANHO_MAXIMO_UTM or not _FORMATO_UTM.match(normalizado):
        registrar_contador(f"campo_descartado campo={campo}")
        return None
    return normalizado


def normalizar_referrer_host(valor: str | None) -> str | None:
    """Aceita apenas um nome de dominio; URL completa ou valor invalido vira None."""
    if valor is None:
        return None
    normalizado = valor.strip().lower().rstrip(".")
    if not normalizado:
        return None
    if (
        len(normalizado) > TAMANHO_MAXIMO_REFERRER_HOST
        or not _FORMATO_HOST.match(normalizado)
    ):
        registrar_contador("campo_descartado campo=referrer_host")
        return None
    return normalizado


def _host_instagram(host: str) -> bool:
    return host == "instagram.com" or host.endswith(".instagram.com")


def _host_busca(host: str) -> bool:
    return any(padrao.match(host) for padrao in _HOSTS_BUSCA)


def calcular_canal(
    utm_source: str | None,
    referrer_host: str | None,
) -> CanalAquisicao:
    """Aplica a tabela de mapeamento de canal, em ordem, sobre valores ja normalizados."""
    if utm_source == "instagram":
        return CanalAquisicao.instagram
    if utm_source == "qrcode":
        return CanalAquisicao.qrcode
    if utm_source:
        return CanalAquisicao.campanha_outros
    if referrer_host:
        if _host_instagram(referrer_host):
            return CanalAquisicao.instagram
        if _host_busca(referrer_host):
            return CanalAquisicao.busca
        return CanalAquisicao.outros_sites
    return CanalAquisicao.direto


def horario_truncado_utc(agora: datetime | None = None) -> datetime:
    """Retorna o horario atual em UTC, sem fuso, arredondado para baixo na hora."""
    momento = agora or datetime.now(UTC)
    if momento.tzinfo is not None:
        momento = momento.astimezone(UTC).replace(tzinfo=None)
    return momento.replace(minute=0, second=0, microsecond=0)
