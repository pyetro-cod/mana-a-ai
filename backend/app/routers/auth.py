from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from .. import models, schemas
from ..database import get_db
from ..security import criar_token

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.post("/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).filter(
        models.Usuario.telefone == payload.telefone,
        models.Usuario.perfil.in_(["caixa", "admin"]),
    ).first()

    if not usuario or not usuario.senha_hash or not pwd_context.verify(payload.senha, usuario.senha_hash):
        raise HTTPException(status_code=401, detail="Telefone ou senha inválidos")

    token = criar_token(usuario.id, usuario.perfil)
    return schemas.LoginResponse(token=token, perfil=usuario.perfil)
