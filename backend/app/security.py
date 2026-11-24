"""Criação e validação dos tokens JWT de acesso."""
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings


class TokenExpirado(Exception):
    pass


class TokenInvalido(Exception):
    pass


def criar_token(usuario_id: str, perfil: str, validade: timedelta | None = None) -> str:
    agora = datetime.now(timezone.utc)
    payload = {
        "sub": usuario_id,
        "perfil": perfil,
        "iat": agora,
        "exp": agora + (validade or timedelta(minutes=settings.jwt_expire_minutes)),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def ler_token(token: str) -> dict:
    """Valida assinatura e expiração e devolve os dados do token."""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            # Pinning the algorithm blocks "alg: none" and algorithm-confusion attacks.
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpirado() from exc
    except jwt.InvalidTokenError as exc:
        raise TokenInvalido() from exc
