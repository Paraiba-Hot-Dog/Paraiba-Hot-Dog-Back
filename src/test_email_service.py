from src import email_service


def test_enviar_recuperacao_senha_usa_smtp_recuperacao(monkeypatch):
    """Garante uso do SMTP dedicado a recuperacao de senha."""
    chamadas = []

    def fake_enviar(config, destino, assunto, corpo):
        chamadas.append((config, destino, assunto, corpo))
        return {"status": "sent"}

    monkeypatch.setattr(email_service, "_enviar_email", fake_enviar)
    monkeypatch.setattr(
        email_service,
        "_smtp_recuperacao_senha",
        lambda: email_service.SmtpConfig(
            host="smtp-recuperacao",
            port=587,
            username="user-recuperacao",
            password="secret",
            from_email="recuperacao@example.com",
            from_name="Recuperacao",
        ),
    )

    resultado = email_service.enviar_recuperacao_senha("maria@example.com", "https://reset.local/token")

    assert resultado == {"status": "sent"}
    assert chamadas[0][0].host == "smtp-recuperacao"
    assert chamadas[0][1] == "maria@example.com"
    assert "recuperacao" in chamadas[0][2].lower()
    assert "https://reset.local/token" in chamadas[0][3]


def test_email_sem_smtp_configurado_e_ignorado():
    """Garante que SMTP ausente nao derruba a API."""
    resultado = email_service._enviar_email(
        email_service.SmtpConfig(
            host="",
            port=587,
            username="",
            password="",
            from_email="",
            from_name="Paraiba Hot Dog",
        ),
        "maria@example.com",
        "Assunto",
        "Corpo",
    )

    assert resultado == {"status": "skipped", "reason": "missing_smtp_credentials"}
