from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, regras, schemas
from ..database import get_db
from ..auth_utils import get_caixa_atual

router = APIRouter(prefix="/transacoes", tags=["transacoes"])


@router.post("", response_model=schemas.TransacaoOut)
def lancar_transacao(
    payload: schemas.TransacaoCreate,
    db: Session = Depends(get_db),
    operador: models.Usuario = Depends(get_caixa_atual),
):
    carteira = db.query(models.Carteira).filter(
        models.Carteira.id == payload.carteira_id
    ).with_for_update().first()

    if not carteira:
        raise HTTPException(status_code=404, detail="Carteira não encontrada")

    if payload.produto_id:
        produto = db.query(models.Produto).filter(models.Produto.id == payload.produto_id).first()
        if not produto:
            raise HTTPException(status_code=404, detail="Produto não encontrado")

    # A expired balance cannot be spent, and a manual credit counts as a purchase.
    momento = regras.agora()
    regras.atualizar_carteira(db, carteira, regras.configuracao(db), momento)

    if payload.tipo == "debito" and payload.valor > carteira.saldo:
        raise HTTPException(status_code=422, detail="Saldo insuficiente para esse débito")

    # Operação atômica: ajusta saldo e registra o histórico na mesma transação de banco.
    try:
        if payload.tipo == "credito":
            carteira.saldo += payload.valor
            carteira.ultima_compra_em = momento
        else:
            carteira.saldo -= payload.valor

        transacao = models.Transacao(
            carteira_id=carteira.id,
            produto_id=payload.produto_id,
            tipo=payload.tipo,
            valor=payload.valor,
            motivo="manual",
            operador_id=operador.id,
            criado_em=momento,
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