from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_host: str = "localhost"
    postgres_port: str = "5432"
    postgres_db: str = "paraiba_hotdog_db"
    database_url: str | None = None
    twilio_account_sid: str = ""
    twilio_api_key_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    smtp_recuperacao_senha_host: str = ""
    smtp_recuperacao_senha_port: int = 587
    smtp_recuperacao_senha_username: str = ""
    smtp_recuperacao_senha_password: str = ""
    smtp_recuperacao_senha_from_email: str = ""
    smtp_recuperacao_senha_from_name: str = "Paraiba Hot Dog"
    smtp_recuperacao_senha_starttls: bool = True
    smtp_recuperacao_senha_ssl: bool = False
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_service_role_key: str = ""
    frontend_base_url: str = "http://localhost:5173"
    reset_senha_token_minutos: int = 30


settings = Settings()
