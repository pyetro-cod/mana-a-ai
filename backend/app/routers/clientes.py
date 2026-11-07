from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..auth_utils import get_caixa_atual
from .carteira import montar_extrato

router = APIRouter(prefix="/clientes", tags=["clientes"])


def _cliente_por_telefone(db: Session, telefone: str) -> models.Usuario:
    usuario = db.query(models.Usuario).filter(
        models.Usuario.telefone == telefone,
        models.Usuario.perfil == "cliente",
    ).first()
    if not usuario or not usuario.carteira:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return usuario


# NOTE: /me e /me/extrato identificam o cliente só pelo telefone, sem prova de que
# ele é o dono do número. É um risco conhecido (LGPD) que a fase 3 fecha com login
# por código no WhatsApp; até lá o app do cliente não deve ir para produção.
@router.get("/me", response_model=schemas.ClienteOut)
def meu_perfil(telefone: str, db: Session = Depends(get_db)):
    """Auto-identificação do cliente pelo próprio telefone."""
    return _cliente_por_telefone(db, telefone)


@router.get("/me/extrato", response_model=schemas.ExtratoOut)
def meu_extrato(telefone: str, db: Session = Depends(get_db)):
    """Saldo e histórico do próprio cliente (app do cliente)."""
    usuario = _cliente_por_telefone(db, telefone)
    return montar_extrato(db, usuario.carteira)


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