from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from . import models
from .database import get_db


def get_caixa_atual(authorization: str = Header(None), db: Session = Depends(get_db)) -> models.Usuario:
    """Valida o token stub do MVP e garante que quem chama é caixa ou admin.

    NOTE: token stub (mesmo aviso do auth.py) — trocar por JWT assinado antes de produção.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado")

    token = authorization.removeprefix("Bearer ").strip()
    if not token.startswith("stub-token."):
        raise HTTPException(status_code=401, detail="Token inválido")

    usuario_id = token.split(".", 1)[1]
    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()

    if not usuario or usuario.perfil not in ("caixa", "admin"):
        raise HTTPException(status_code=401, detail="Não autorizado")

    return usuario


def get_admin_atual(usuario_atual: models.Usuario = Depends(get_caixa_atual)) -> models.Usuario:
    """Mesma validação de token, mas exige perfil admin — usado na gestão de catálogo."""
    if usuario_atual.perfil != "admin":
        raise HTTPException(status_code=403, detail="Ação restrita a administradores")
    return usuario_atual