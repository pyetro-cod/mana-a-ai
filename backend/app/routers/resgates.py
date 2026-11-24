"""Balcão: o caixa digita o código que o cliente mostra e confirma a entrega do prêmio."""
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from .. import models, resgates, schemas
from ..auth_utils import get_caixa_atual
from ..database import get_db

router = APIRouter(prefix="/resgates", tags=["resgates"])

CODIGO = Path(..., pattern=r"^\d{6}$")
STATUS_RECUSA = {"resgate_inexistente": 404, "resgate_expirado": 410}


def _saida(resgate: models.Resgate, db: Session) -> schemas.ResgateCaixaOut:
    cliente = db.get(models.Carteira, resgate.carteira_id).usuario
    return schemas.ResgateCaixaOut(codigo=resgate.codigo, cliente=cliente.nome, premio=resgate.premio.nome,
                                   custo_creditos=resgate.custo_creditos, expira_em=resgate.expira_em,
                                   status=resgate.status)


def _recusar(db: Session, recusa: resgates.ResgateRecusado):
    # An expired code was just refunded: keep that refund even though the request fails.
    db.commit()
    raise HTTPException(status_code=STATUS_RECUSA[recusa.motivo], detail=recusa.motivo)


@router.get("/{codigo}", response_model=schemas.ResgateCaixaOut)
def consultar(codigo: str = CODIGO, db: Session = Depends(get_db),
              _operador: models.Usuario = Depends(get_caixa_atual)):
    """Mostra quem é o cliente e qual o prêmio, antes de entregar."""
    try:
        return _saida(resgates.buscar_para_o_caixa(db, codigo), db)
    except resgates.ResgateRecusado as recusa:
        _recusar(db, recusa)


@router.post("/{codigo}/confirmar", response_model=schemas.ResgateCaixaOut)
def confirmar(codigo: str = CODIGO, db: Session = Depends(get_db),
              operador: models.Usuario = Depends(get_caixa_atual)):
    try:
        resgate = resgates.confirmar(db, operador, codigo)
    except resgates.ResgateRecusado as recusa:
        _recusar(db, recusa)
    db.commit()
    db.refresh(resgate)
    return _saida(resgate, db)
