import logging
import re

import requests

from src.config import settings

logger = logging.getLogger(__name__)


def _formatar_telefone_whatsapp(telefone: str) -> str:
    """Formata um numero de telefone para o padrao internacional do WhatsApp com codigo do Brasil."""
    numeros = re.sub(r"\D", "", str(telefone or ""))
    if numeros.startswith("55"):
        return numeros
    return f"55{numeros}"


def _credenciais_configuradas() -> bool:
    """Verifica se as credenciais do Twilio estao corretamente preenchidas nas configuracoes."""
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        return False
    if settings.twilio_account_sid == "SEU_TWILIO_ACCOUNT_SID_AQUI":
        return False
    if settings.twilio_auth_token == "SEU_TWILIO_AUTH_TOKEN_AQUI":
        return False
    if not settings.twilio_whatsapp_from.startswith("whatsapp:"):
        return False
    return True


def enviar_boas_vindas(nome: str, telefone: str) -> dict:
    """Envia mensagem de boas-vindas via WhatsApp ao cliente usando a API do Twilio.

    Retorna um dict com o status do envio. Nao faz nada se as credenciais nao estiverem configuradas.
    """
    logger.warning(
        "Iniciando envio de WhatsApp para cliente=%s telefone=%s",
        nome,
        telefone,
    )
    if not _credenciais_configuradas():
        logger.warning(
            "Envio WhatsApp ignorado: credenciais ausentes para cliente=%s telefone=%s",
            nome,
            telefone,
        )
        return {"status": "skipped", "reason": "missing_whatsapp_credentials"}

    telefone_formatado = _formatar_telefone_whatsapp(telefone)
    destino = f"whatsapp:+{telefone_formatado}"
    logger.warning(
        "Credenciais OK. Preparando request Twilio para cliente=%s destino=%s",
        nome,
        destino,
    )
    api_url = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{settings.twilio_account_sid}/Messages.json"
    )
    payload = {
        "From": settings.twilio_whatsapp_from,
        "To": destino,
        "Body": (
            f"Ola, {nome}!\n\n"
            "Seja bem-vindo ao nosso programa de fidelidade!\n\n"
            "A partir de agora, voce acumula pontos a cada compra e pode trocar por hot dogs.\n\n"
            "Para conferir seus pontos, acesse o nosso site.\n\n"
            "Obrigado pela parceria e fidelidade.\n\n"
            "PARAIBA HOTDOG"
        ),
    }

    try:
        logger.warning(
            "Enviando request Twilio para cliente=%s destino=%s",
            nome,
            destino,
        )
        response = requests.post(
            api_url,
            data=payload,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            timeout=10,
        )
        logger.warning(
            "Resposta Twilio recebida para cliente=%s destino=%s status=%s",
            nome,
            destino,
            response.status_code,
        )
        if response.status_code in (200, 201):
            logger.warning(
                "Mensagem de boas-vindas enviada com sucesso para cliente=%s telefone=%s",
                nome,
                destino,
            )
        else:
            logger.error(
                "Falha ao enviar WhatsApp para cliente=%s telefone=%s status=%s body=%s",
                nome,
                destino,
                response.status_code,
                response.text,
            )
        return response.json()
    except requests.RequestException as exc:
        logger.exception(
            "Erro de rede no envio de WhatsApp para cliente=%s telefone=%s: %s",
            nome,
            telefone_formatado,
            exc,
        )
        return {"status": "error", "reason": "request_exception"}
    except Exception as exc:  # pragma: no cover - defensivo para diagnostico em runtime
        logger.exception(
            "Erro inesperado no envio de WhatsApp para cliente=%s telefone=%s: %s",
            nome,
            telefone_formatado,
            exc,
        )
        return {"status": "error", "reason": "unexpected_exception"}
