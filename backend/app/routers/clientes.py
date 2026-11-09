from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, regras, schemas
from ..database import get_db
from ..auth_utils import get_caixa_atual, get_cliente_atual
from .carteira import montar_extrato

router = APIRouter(prefix="/clientes", tags=["clientes"])

# The detail is a stable code the app turns into a friendly message.
STATUS_RECUSA = {
    "cupom_inexistente": 404,
    "cupom_ja_usado": 409,
    "cupom_expirado": 410,
    "limite_diario": 429,
}


@router.get("/me", response_model=schemas.ClienteOut)
def meu_perfil(cliente: models.Usuario = Depends(get_cliente_atual), db: Session = Depends(get_db)):
    """Dados do cliente logado no app (identificado pelo token, não pelo telefone)."""
    if regras.aplicar_expiracao(db, cliente.carteira, regras.configuracao(db)) or db.dirty:
        db.commit()
        db.refresh(cliente)
    return cliente


@router.get("/me/extrato", response_model=schemas.ExtratoOut)
def meu_extrato(cliente: models.Usuario = Depends(get_cliente_atual), db: Session = Depends(get_db)):
    """Saldo e histórico do cliente logado."""
    return montar_extrato(db, cliente.carteira)


@router.post("/me/cupons", response_model=schemas.UsarCupomOut)
def usar_cupom(
    payload: schemas.UsarCupomRequest,
    cliente: models.Usuario = Depends(get_cliente_atual),
    db: Session = Depends(get_db),
):
    """O cliente escaneia o QR do cupom e o crédito cai na hora (com o bônus, no 1º)."""
    try:
        resultado = regras.resgatar_cupom(db, cliente, payload.codigo)
        db.commit()
    except regras.CupomRecusado as recusa:
        db.rollback()
        raise HTTPException(status_code=STATUS_RECUSA[recusa.motivo], detail=recusa.motivo)
    return resultado


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


@router.post("", response_model=schemas.ClienteOut, status_code=201)
def cadastrar_cliente(
    payload: schemas.ClienteCreate,
    db: Session = Depends(get_db),
    _usuario_atual: models.Usuario = Depends(get_caixa_atual),
):
    existente = db.query(models.Usuario).filter(models.Usuario.telefone == payload.telefone).first()
    if existente:
        raise HTTPException(status_code=409, detail="Já existe um cadastro com esse telefone")

    usuario = models.Usuario(nome=payload.nome, telefone=payload.telefone, perfil="cliente")
    db.add(usuario)
    db.flush()  # garante usuario.id antes de criar a carteira

    carteira = models.Carteira(usuario_id=usuario.id, saldo=0)
    db.add(carteira)
    db.commit()
    db.refresh(usuario)

    return usuario