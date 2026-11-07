from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .security import TokenExpirado, TokenInvalido, ler_token

# auto_error=False so we answer 401 (not FastAPI's default 403) when the header is missing.
bearer = HTTPBearer(auto_error=False)


def _nao_autenticado(detalhe: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detalhe, headers={"WWW-Authenticate": "Bearer"})


def _usuario_do_token(
    credenciais: HTTPAuthorizationCredentials | None, db: Session, perfis: tuple[str, ...]
) -> models.Usuario:
    if credenciais is None:
        raise _nao_autenticado("Não autenticado")

    try:
        dados = ler_token(credenciais.credentials)
    except TokenExpirado:
        raise _nao_autenticado("Sessão expirada, faça login novamente")
    except TokenInvalido:
        raise _nao_autenticado("Token inválido")

    # The database is the source of truth: a demoted or deleted user loses access
    # immediately, even while their token has not expired yet.
    usuario = db.query(models.Usuario).filter(models.Usuario.id == dados["sub"]).first()
    if not usuario or usuario.perfil not in perfis:
        raise _nao_autenticado("Não autorizado")

    return usuario


def get_caixa_atual(
    credenciais: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> models.Usuario:
    """Valida o JWT e garante que quem chama é caixa ou admin."""
    return _usuario_do_token(credenciais, db, ("caixa", "admin"))


def get_admin_atual(usuario_atual: models.Usuario = Depends(get_caixa_atual)) -> models.Usuario:
    """Mesma validação de token, mas exige perfil admin — usado na gestão de catálogo."""
    if usuario_atual.perfil != "admin":
        raise HTTPException(status_code=403, detail="Ação restrita a administradores")
    return usuario_atual


def get_cliente_atual(
    credenciais: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> models.Usuario:
    """Valida o JWT do app do cliente: o cliente só enxerga a própria carteira."""
    usuario = _usuario_do_token(credenciais, db, ("cliente",))
    if not usuario.carteira:
        raise _nao_autenticado("Cliente sem carteira associada")
    return usuario
