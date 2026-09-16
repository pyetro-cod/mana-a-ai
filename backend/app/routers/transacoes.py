from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/transacoes", tags=["transacoes"])


@router.post("", response_model=schemas.TransacaoOut)
def lancar_transacao(payload: schemas.TransacaoCreate, db: Session = Depends(get_db)):
    carteira = db.query(models.Carteira).filter(
        models.Carteira.id == payload.carteira_id
    ).with_for_update().first()

    if not carteira:
        raise HTTPException(status_code=404, detail="Carteira não encontrada")

    if payload.produto_id:
        produto = db.query(models.Produto).filter(models.Produto.id == payload.produto_id).first()
        if not produto:
            raise HTTPException(status_code=404, detail="Produto não encontrado")

    if payload.tipo == "debito" and payload.valor > carteira.saldo:
        raise HTTPException(status_code=422, detail="Saldo insuficiente para esse débito")

    # Operação atômica: ajusta saldo e registra o histórico na mesma transação de banco.
    try:
        if payload.tipo == "credito":
            carteira.saldo += payload.valor
        else:
            carteira.saldo -= payload.valor

        transacao = models.Transacao(
            carteira_id=carteira.id,
            produto_id=payload.produto_id,
            tipo=payload.tipo,
            valor=payload.valor,
        )
        db.add(transacao)
        db.add(carteira)
        db.commit()
        db.refresh(carteira)
        db.refresh(transacao)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Falha ao registrar transação")

    return schemas.TransacaoOut(transacao_id=transacao.id, novo_saldo=carteira.saldo)
