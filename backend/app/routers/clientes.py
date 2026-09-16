from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/clientes", tags=["clientes"])


@router.get("", response_model=schemas.ClienteOut)
def buscar_cliente(telefone: str, db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).filter(
        models.Usuario.telefone == telefone,
        models.Usuario.perfil == "cliente",
    ).first()

    if not usuario:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    if not usuario.carteira:
        raise HTTPException(status_code=404, detail="Cliente sem carteira associada")

    return usuario
