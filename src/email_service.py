import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
# pylint: disable=too-many-instance-attributes
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    from_email: str
    from_name: str
    starttls: bool = True
    ssl: bool = False


def _smtp_recuperacao_senha() -> SmtpConfig:
    return SmtpConfig(
        host=settings.smtp_recuperacao_senha_host,
        port=settings.smtp_recuperacao_senha_port,
        username=settings.smtp_recuperacao_senha_username,
        password=settings.smtp_recuperacao_senha_password,
        from_email=settings.smtp_recuperacao_senha_from_email,
        from_name=settings.smtp_recuperacao_senha_from_name,
        starttls=settings.smtp_recuperacao_senha_starttls,
        ssl=settings.smtp_recuperacao_senha_ssl,
    )


def _configurado(config: SmtpConfig) -> bool:
    return bool(config.host and config.from_email)


def _enviar_email(config: SmtpConfig, destino: str, assunto: str, corpo: str) -> dict:
    if not destino:
        return {"status": "skipped", "reason": "missing_recipient"}

    if not _configurado(config):
        logger.warning(
            "Envio de e-mail ignorado: SMTP nao configurado para destino=%s assunto=%s",
            destino,
            assunto,
        )
        return {"status": "skipped", "reason": "missing_smtp_credentials"}

    mensagem = EmailMessage()
    mensagem["From"] = formataddr((config.from_name, config.from_email))
    mensagem["To"] = destino
    mensagem["Subject"] = assunto
    mensagem.set_content(corpo)

    try:
        smtp_cls = smtplib.SMTP_SSL if config.ssl else smtplib.SMTP
        with smtp_cls(config.host, config.port, timeout=10) as smtp:
            if config.starttls and not config.ssl:
                smtp.starttls()
            if config.username:
                smtp.login(config.username, config.password)
            smtp.send_message(mensagem)
        logger.info("E-mail enviado com sucesso para destino=%s assunto=%s", destino, assunto)
        return {"status": "sent"}
    except smtplib.SMTPException as exc:
        logger.exception("Falha SMTP ao enviar e-mail para destino=%s: %s", destino, exc)
        return {"status": "error", "reason": "smtp_exception"}
    except OSError as exc:
        logger.exception("Falha de rede ao enviar e-mail para destino=%s: %s", destino, exc)
        return {"status": "error", "reason": "network_exception"}


def enviar_recuperacao_senha(email: str, link_recuperacao: str) -> dict:
    """Envia e-mail de recuperacao de senha usando o SMTP dedicado a reset de senha."""
    corpo = (
        "Recebemos uma solicitacao para recuperar sua senha.\n\n"
        f"Acesse o link abaixo para continuar:\n{link_recuperacao}\n\n"
        "Se voce nao solicitou essa alteracao, ignore esta mensagem.\n\n"
        "PARAIBA HOTDOG"
    )
    return _enviar_email(
        _smtp_recuperacao_senha(),
        email,
        "Recuperacao de senha Paraiba Hot Dog",
        corpo,
    )
