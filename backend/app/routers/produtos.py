from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..auth_utils import get_caixa_atual, get_admin_atual

router = APIRouter(prefix="/produtos", tags=["produtos"])


@router.get("", response_model=list[schemas.ProdutoOut])
def listar_produtos(
    db: Session = Depends(get_db),
    _usuario_atual: models.Usuario = Depends(get_caixa_atual),
):
    return db.query(models.Produto).order_by(models.Produto.nome).all()


@router.post("", response_model=schemas.ProdutoOut, status_code=201)
def criar_produto(
    payload: schemas.ProdutoCreate,
    db: Session = Depends(get_db),
    _admin_atual: models.Usuario = Depends(get_admin_atual),
):
    produto = models.Produto(nome=payload.nome, valor_creditos=payload.valor_creditos)
    db.add(produto)
    db.commit()
    db.refresh(produto)
    return produto


@router.put("/{produto_id}", response_model=schemas.ProdutoOut)
def editar_produto(
    produto_id: str,
    payload: schemas.ProdutoUpdate,
    db: Session = Depends(get_db),
    _admin_atual: models.Usuario = Depends(get_admin_atual),
):
    produto = db.query(models.Produto).filter(models.Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    if payload.nome is not None:
        produto.nome = payload.nome
    if payload.valor_creditos is not None:
        produto.valor_creditos = payload.valor_creditos

    db.commit()
    db.refresh(produto)
    return produto