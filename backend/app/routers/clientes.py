from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..auth_utils import get_caixa_atual

router = APIRouter(prefix="/clientes", tags=["clientes"])


@router.get("/me", response_model=schemas.ClienteOut)
def meu_perfil(telefone: str, db: Session = Depends(get_db)):
    """Auto-identificação do cliente pelo próprio telefone.

    Sem autenticação por senha, de propósito: o cliente ainda não tem
    credenciais reais (isso depende da decisão de QR/login que ficou em aberto).
    Rota separada da /clientes usada pelo caixa, que exige token.
    """
    usuario = db.query(models.Usuario).filter(
        models.Usuario.telefone == telefone,
        models.Usuario.perfil == "cliente",
    ).first()

    if not usuario or not usuario.carteira:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    return usuario


@router.get("", response_model=schemas.ClienteOut)
def buscar_cliente(
    telefone: str,
    db: Session = Depends(get_db),
    _usuario_atual: models.Usuario = Depends(get_caixa_atual),
):
    usuario = db.query(models.Usuario).filter(
        models.Usuario.telefone == telefone,
        models.Usuario.perfil == "cliente",
    ).first()

    if not usuario:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    if not usuario.carteira:
        raise HTTPException(status_code=404, detail="Cliente sem carteira associada")

    return usuario