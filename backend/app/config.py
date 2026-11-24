"""Configuração da API lida de variáveis de ambiente (arquivo backend/.env em dev).

Nenhum segredo fica no código: o .env está no .gitignore e o .env.example
documenta só os nomes das variáveis.
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# HS256 keys shorter than 32 bytes can be brute-forced offline from a single token.
MIN_SECRET_LENGTH = 32

AMBIENTES = ("dev", "prod")
PROVEDORES_OTP = ("console", "whatsapp")


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    jwt_secret: str
    jwt_algorithm: str
    jwt_expire_minutes: int
    jwt_cliente_expire_dias: int
    cors_origins: list[str]
    otp_provider: str
    otp_expire_minutes: int
    whatsapp_token: str
    whatsapp_phone_number_id: str
    whatsapp_template: str
    app_public_url: str
    otp_mostrar_no_app: bool


def _int_positivo(nome: str, padrao: str) -> int:
    try:
        valor = int(os.getenv(nome, padrao))
    except ValueError as exc:
        raise RuntimeError(f"{nome} deve ser um número inteiro") from exc
    if valor <= 0:
        raise RuntimeError(f"{nome} deve ser maior que zero")
    return valor


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./mana.db")
    # Supabase/Heroku-style URLs use the bare "postgres(ql)://" scheme; SQLAlchemy needs
    # the driver spelled out to pick psycopg 3 instead of the legacy psycopg2.
    for prefixo in ("postgres://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url[len(prefixo):]
    return url


def _load_settings() -> Settings:
    app_env = os.getenv("APP_ENV", "dev")
    if app_env not in AMBIENTES:
        raise RuntimeError(f"APP_ENV deve ser um de {AMBIENTES}")

    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET ausente ou curto demais (mínimo {MIN_SECRET_LENGTH} caracteres). "
            "Gere um com: python -c \"import secrets; print(secrets.token_urlsafe(48))\" "
            "e coloque em backend/.env"
        )

    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    if "*" in origins:
        raise RuntimeError("CORS_ORIGINS não pode conter '*': liste as origens do front explicitamente")

    otp_provider = os.getenv("OTP_PROVIDER", "console")
    if otp_provider not in PROVEDORES_OTP:
        raise RuntimeError(f"OTP_PROVIDER deve ser um de {PROVEDORES_OTP}")
    if otp_provider == "console" and app_env == "prod":
        # The console provider prints login codes to the server log: never acceptable in production.
        raise RuntimeError("OTP_PROVIDER=console não é permitido com APP_ENV=prod")

    whatsapp_token = os.getenv("WHATSAPP_TOKEN", "")
    whatsapp_phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    whatsapp_template = os.getenv("WHATSAPP_TEMPLATE", "")
    if otp_provider == "whatsapp" and not (whatsapp_token and whatsapp_phone_number_id and whatsapp_template):
        raise RuntimeError(
            "OTP_PROVIDER=whatsapp exige WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID e WHATSAPP_TEMPLATE"
        )

    # Dev-only shortcut: the login code comes back in the API response and the app shows
    # it, so you can test the customer login without reading the server terminal.
    # Anyone could log in as any phone with this on, hence the hard refusals below.
    otp_mostrar_no_app = os.getenv("OTP_MOSTRAR_NO_APP", "0").strip().lower() in ("1", "true", "sim")
    if otp_mostrar_no_app and (app_env != "dev" or otp_provider != "console"):
        raise RuntimeError("OTP_MOSTRAR_NO_APP só é permitido com APP_ENV=dev e OTP_PROVIDER=console")

    database_url = _database_url()
    if os.getenv("VERCEL") and database_url.startswith("sqlite"):
        # Vercel's filesystem is ephemeral: a SQLite file there would silently lose every balance.
        raise RuntimeError("Na Vercel é obrigatório definir DATABASE_URL apontando para o Postgres")

    # Where the customer app lives: printed coupon QRs point here (?cupom=CODE).
    app_public_url = os.getenv("APP_PUBLIC_URL", "http://localhost:5500").rstrip("/")
    if not app_public_url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        raise RuntimeError("APP_PUBLIC_URL deve usar https:// (http só para localhost)")

    return Settings(
        app_env=app_env,
        database_url=database_url,
        jwt_secret=secret,
        jwt_algorithm="HS256",
        jwt_expire_minutes=_int_positivo("JWT_EXPIRE_MINUTES", "480"),
        jwt_cliente_expire_dias=_int_positivo("JWT_CLIENTE_EXPIRE_DIAS", "30"),
        cors_origins=origins,
        otp_provider=otp_provider,
        otp_expire_minutes=_int_positivo("OTP_EXPIRE_MINUTES", "10"),
        whatsapp_token=whatsapp_token,
        whatsapp_phone_number_id=whatsapp_phone_number_id,
        whatsapp_template=whatsapp_template,
        app_public_url=app_public_url,
        otp_mostrar_no_app=otp_mostrar_no_app,
    )


settings = _load_settings()
