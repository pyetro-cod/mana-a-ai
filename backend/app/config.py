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


@dataclass(frozen=True)
class Settings:
    jwt_secret: str
    jwt_algorithm: str
    jwt_expire_minutes: int
    cors_origins: list[str]


def _load_settings() -> Settings:
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET ausente ou curto demais (mínimo {MIN_SECRET_LENGTH} caracteres). "
            "Gere um com: python -c \"import secrets; print(secrets.token_urlsafe(48))\" "
            "e coloque em backend/.env"
        )

    try:
        expire_minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
    except ValueError as exc:
        raise RuntimeError("JWT_EXPIRE_MINUTES deve ser um número inteiro de minutos") from exc
    if expire_minutes <= 0:
        raise RuntimeError("JWT_EXPIRE_MINUTES deve ser maior que zero")

    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    if "*" in origins:
        raise RuntimeError("CORS_ORIGINS não pode conter '*': liste as origens do front explicitamente")

    return Settings(
        jwt_secret=secret,
        jwt_algorithm="HS256",
        jwt_expire_minutes=expire_minutes,
        cors_origins=origins,
    )


settings = _load_settings()
