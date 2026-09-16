from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/carteira", tags=["carteira"])


@router.get("/{carteira_id}", response_model=schemas.ExtratoOut)
def consultar_carteira(carteira_id: str, db: Session = Depends(get_db)):
    carteira = db.query(models.Carteira).filter(models.Carteira.id == carteira_id).first()
    if not carteira:
        raise HTTPException(status_code=404, detail="Carteira não encontrada")

    historico = (
        db.query(models.Transacao)
        .filter(models.Transacao.carteira_id == carteira_id)
        .order_by(models.Transacao.criado_em.desc())
        .limit(20)
        .all()
    )

    return schemas.ExtratoOut(saldo=carteira.saldo, historico=historico)
