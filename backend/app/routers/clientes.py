from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import limites, models, regras, resgates, schemas
from ..database import get_db
from ..auth_utils import get_caixa_atual, get_cliente_atual
from .carteira import montar_extrato

router = APIRouter(prefix="/clientes", tags=["clientes"])

# The detail is a stable code the app turns into a friendly message.
STATUS_RECUSA = {
    "cupom_inexistente": 404,
    "cupom_ja_usado": 409,
    "cupom_expirado": 410,
    "cupom_cancelado": 410,
    "limite_diario": 429,
    "premio_inexistente": 404,
    "saldo_insuficiente": 422,
}


@router.get("/me", response_model=schemas.ClienteOut)
def meu_perfil(cliente: models.Usuario = Depends(get_cliente_atual), db: Session = Depends(get_db)):
    """Dados do cliente logado no app (identificado pelo token, não pelo telefone)."""
    regras.atualizar_carteira(db, cliente.carteira, regras.configuracao(db))
    if db.dirty or db.new:
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
        limites.checar(db, "cupom", cliente.id)
    except limites.LimiteExcedido as exc:
        raise HTTPException(status_code=429, detail="muitas_tentativas",
                            headers={"Retry-After": str(exc.segundos_para_tentar)})
    try:
        resultado = regras.resgatar_cupom(db, cliente, payload.codigo)
        db.commit()
    except regras.CupomRecusado as recusa:
        db.rollback()
        if recusa.motivo == "cupom_inexistente":
            # Only made-up codes count: a used or expired coupon is a real one, not a guess.
            limites.registrar_falha(db, "cupom", cliente.id)
        raise HTTPException(status_code=STATUS_RECUSA[recusa.motivo], detail=recusa.motivo)
    return resultado


@router.get("/me/premios", response_model=list[schemas.PremioOut])
def premios_disponiveis(_cliente: models.Usuario = Depends(get_cliente_atual), db: Session = Depends(get_db)):
    """Catálogo que o cliente vê: só prêmios ativos, do mais barato ao mais caro."""
    return (db.query(models.Premio).filter(models.Premio.ativo.is_(True))
            .order_by(models.Premio.custo_creditos).all())


def _resgate_out(resgate: models.Resgate, carteira: models.Carteira) -> schemas.ResgateOut:
    return schemas.ResgateOut(codigo=resgate.codigo, premio=resgate.premio.nome,
                              custo_creditos=resgate.custo_creditos, expira_em=resgate.expira_em,
                              novo_saldo=carteira.saldo)


@router.post("/me/resgates", response_model=schemas.ResgateOut, status_code=201)
def pedir_resgate(
    payload: schemas.SolicitarResgateRequest,
    cliente: models.Usuario = Depends(get_cliente_atual),
    db: Session = Depends(get_db),
):
    """Reserva os créditos e devolve o código de 6 dígitos para mostrar no caixa."""
    try:
        resgate = resgates.solicitar(db, cliente, payload.premio_id)
        db.commit()
    except resgates.ResgateRecusado as recusa:
        db.rollback()
        raise HTTPException(status_code=STATUS_RECUSA[recusa.motivo], detail=recusa.motivo)
    db.refresh(cliente)
    return _resgate_out(resgate, cliente.carteira)


@router.get("/me/resgates/pendente", response_model=schemas.ResgateOut | None)
def resgate_em_aberto(cliente: models.Usuario = Depends(get_cliente_atual), db: Session = Depends(get_db)):
    """Código ainda válido (para o app reabrir a tela do código), ou null."""
    regras.atualizar_carteira(db, cliente.carteira, regras.configuracao(db))
    db.commit()
    resgate = resgates.pendente_do_cliente(db, cliente.carteira)
    return _resgate_out(resgate, cliente.carteira) if resgate else None


@router.post("/me/resgates/cancelar", response_model=schemas.CancelarResgateOut)
def cancelar_resgate(cliente: models.Usuario = Depends(get_cliente_atual), db: Session = Depends(get_db)):
    devolvido = resgates.cancelar(db, cliente)
    db.commit()
    db.refresh(cliente)
    return schemas.CancelarResgateOut(devolvido=devolvido, novo_saldo=cliente.carteira.saldo)


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