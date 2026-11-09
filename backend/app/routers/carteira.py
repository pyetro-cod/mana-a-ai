from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, regras, schemas
from ..auth_utils import get_caixa_atual
from ..database import get_db

router = APIRouter(prefix="/carteira", tags=["carteira"])

HISTORICO_LIMITE = 20


def montar_extrato(db: Session, carteira: models.Carteira) -> schemas.ExtratoOut:
    """Saldo + últimas transações. Aplica a expiração antes, para nunca mostrar saldo vencido."""
    config = regras.configuracao(db)
    if regras.aplicar_expiracao(db, carteira, config) or db.dirty or db.new:
        db.commit()
        db.refresh(carteira)
    historico = (
        db.query(models.Transacao)
        .filter(models.Transacao.carteira_id == carteira.id)
        .order_by(models.Transacao.criado_em.desc())
        .limit(HISTORICO_LIMITE)
        .all()
    )
    return schemas.ExtratoOut(saldo=carteira.saldo, vence_em=regras.vence_em(carteira, config),
                              historico=historico)


@router.get("/{carteira_id}", response_model=schemas.ExtratoOut)
def consultar_carteira(
    carteira_id: str,
    db: Session = Depends(get_db),
    _usuario_atual: models.Usuario = Depends(get_caixa_atual),
):
    """Extrato de qualquer carteira: uso exclusivo do caixa/admin."""
    carteira = db.query(models.Carteira).filter(models.Carteira.id == carteira_id).first()
    if not carteira:
        raise HTTPException(status_code=404, detail="Carteira não encontrada")
    return montar_extrato(db, carteira)
