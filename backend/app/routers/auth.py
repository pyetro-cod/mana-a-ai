from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .. import limites, models, otp, schemas
from ..config import settings
from ..database import get_db
from ..envio_codigo import EnvioFalhou
from ..security import criar_token

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bump whenever the terms text changes, so every consent record points to what was accepted.
VERSAO_TERMOS = "2026-11"


@router.post("/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    try:
        # Keyed by phone, checked before bcrypt: a blocked phone costs the server nothing.
        limites.checar(db, "login", payload.telefone)
    except limites.LimiteExcedido as exc:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas erradas. Aguarde alguns minutos e tente de novo",
            headers={"Retry-After": str(exc.segundos_para_tentar)},
        )

    usuario = db.query(models.Usuario).filter(
        models.Usuario.telefone == payload.telefone,
        models.Usuario.perfil.in_(["caixa", "admin"]),
    ).first()

    if not usuario or not usuario.senha_hash or not pwd_context.verify(payload.senha, usuario.senha_hash):
        # Counted for unknown phones too, so the limit does not reveal which phones exist.
        limites.registrar_falha(db, "login", payload.telefone)
        raise HTTPException(status_code=401, detail="Telefone ou senha inválidos")

    limites.limpar(db, "login", payload.telefone)
    db.commit()
    token = criar_token(usuario.id, usuario.perfil)
    return schemas.LoginResponse(token=token, perfil=usuario.perfil)


# ---------- Login do cliente por código (OTP) ----------

@router.post("/cliente/codigo", status_code=202)
def solicitar_codigo(payload: schemas.SolicitarCodigoRequest, db: Session = Depends(get_db)):
    """Envia um código de acesso ao telefone. A resposta é a mesma para telefone
    cadastrado ou não, para não revelar quem é cliente."""
    try:
        codigo = otp.solicitar_codigo(db, payload.telefone)
    except otp.LimiteExcedido as exc:
        raise HTTPException(
            status_code=429,
            detail=f"Aguarde {exc.segundos_para_tentar}s para pedir um novo código",
            headers={"Retry-After": str(exc.segundos_para_tentar)},
        )
    except EnvioFalhou:
        raise HTTPException(status_code=503, detail="Não foi possível enviar o código agora, tente de novo")
    if settings.otp_mostrar_no_app:
        return {"detail": "Código enviado", "codigo_dev": codigo}
    return {"detail": "Código enviado"}


@router.post("/cliente/entrar", response_model=schemas.EntrarClienteResponse)
def entrar_cliente(payload: schemas.EntrarClienteRequest, db: Session = Depends(get_db)):
    """Confere o código. Telefone já cadastrado: entra. Telefone novo: exige nome e
    aceite dos termos e cria a conta (autocadastro)."""
    usuario = db.query(models.Usuario).filter(models.Usuario.telefone == payload.telefone).first()
    if usuario and usuario.perfil != "cliente":
        raise HTTPException(status_code=403, detail="Este telefone usa o login do painel")

    precisa_cadastro = usuario is None and not (payload.nome and payload.aceite_termos)
    try:
        # A correct code is kept alive when the sign-up data is missing, so the app can
        # ask for name + consent and resend the same code instead of requesting a new one.
        otp.conferir_codigo(db, payload.telefone, payload.codigo, consumir=not precisa_cadastro)
    except otp.CodigoInvalido:
        raise HTTPException(status_code=401, detail="Código inválido ou expirado")

    if precisa_cadastro:
        raise HTTPException(status_code=409, detail="cadastro_necessario")

    novo_cadastro = usuario is None
    if novo_cadastro:
        usuario = models.Usuario(nome=payload.nome, telefone=payload.telefone, perfil="cliente")
        db.add(usuario)
        db.flush()
        db.add(models.Carteira(usuario_id=usuario.id, saldo=0))
        db.add(models.Consentimento(usuario_id=usuario.id, versao_termos=VERSAO_TERMOS))
        db.commit()
        db.refresh(usuario)

    token = criar_token(usuario.id, "cliente", validade=timedelta(days=settings.jwt_cliente_expire_dias))
    return schemas.EntrarClienteResponse(token=token, novo_cadastro=novo_cadastro)
