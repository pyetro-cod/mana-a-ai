"""Troca de créditos por prêmio: o cliente gera um código, o caixa confirma a entrega.

Os créditos saem da carteira NO MOMENTO em que o código é gerado (ficam reservados).
Assim o cliente não consegue gastar o mesmo saldo duas vezes enquanto espera no balcão.
Se o caixa não confirmar a tempo, ou o cliente cancelar, os créditos voltam (estorno).
Nenhuma função faz commit.
"""
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import models, regras

DIGITOS_RESGATE = 6


class ResgateRecusado(Exception):
    def __init__(self, motivo: str):
        super().__init__(motivo)
        # premio_inexistente | saldo_insuficiente | resgate_inexistente | resgate_expirado
        self.motivo = motivo


def _codigo_livre(db: Session, momento: datetime) -> str:
    """6 dígitos que nenhum outro resgate em aberto está usando agora."""
    while True:
        codigo = f"{secrets.randbelow(10 ** DIGITOS_RESGATE):0{DIGITOS_RESGATE}d}"
        em_uso = (db.query(models.Resgate)
                  .filter(models.Resgate.codigo == codigo,
                          models.Resgate.status == "pendente",
                          models.Resgate.expira_em > momento)
                  .first())
        if em_uso is None:
            return codigo


def _carteira_travada(db: Session, carteira_id: str) -> models.Carteira:
    return (db.query(models.Carteira).filter(models.Carteira.id == carteira_id)
            .with_for_update().one())


def pendente_do_cliente(db: Session, carteira: models.Carteira, momento: datetime | None = None):
    momento = momento or regras.agora()
    return (db.query(models.Resgate)
            .filter(models.Resgate.carteira_id == carteira.id,
                    models.Resgate.status == "pendente",
                    models.Resgate.expira_em > momento)
            .first())


def solicitar(db: Session, cliente: models.Usuario, premio_id: str,
              momento: datetime | None = None) -> models.Resgate:
    """Reserva os créditos e gera o código. Um pedido novo substitui o anterior em aberto."""
    momento = momento or regras.agora()
    config = regras.configuracao(db)
    carteira = _carteira_travada(db, cliente.carteira.id)
    regras.atualizar_carteira(db, carteira, config, momento)

    premio = db.get(models.Premio, premio_id)
    if premio is None or not premio.ativo:
        raise ResgateRecusado("premio_inexistente")

    # Changing your mind at the counter is normal: the old code dies and its credits return
    # before checking the balance, so they count towards the new prize.
    anterior = pendente_do_cliente(db, carteira, momento)
    if anterior is not None:
        regras.estornar_resgate(db, carteira, anterior, "cancelado", momento)

    if carteira.saldo < premio.custo_creditos:
        raise ResgateRecusado("saldo_insuficiente")

    resgate = models.Resgate(
        carteira_id=carteira.id, premio_id=premio.id, codigo=_codigo_livre(db, momento),
        custo_creditos=premio.custo_creditos,  # price frozen now, even if the admin edits it later
        status="pendente", criado_em=momento,
        expira_em=momento + timedelta(minutes=config.validade_resgate_minutos),
    )
    db.add(resgate)
    db.flush()

    carteira.saldo -= premio.custo_creditos
    db.add(models.Transacao(carteira_id=carteira.id, tipo="debito", valor=premio.custo_creditos,
                            motivo="resgate", resgate_id=resgate.id, criado_em=momento))
    return resgate


def cancelar(db: Session, cliente: models.Usuario, momento: datetime | None = None) -> int:
    """Cliente desistiu: devolve os créditos do código em aberto. Devolve quanto voltou (0 se nada)."""
    momento = momento or regras.agora()
    carteira = _carteira_travada(db, cliente.carteira.id)
    pendente = pendente_do_cliente(db, carteira, momento)
    if pendente is None:
        return 0
    devolvido = regras.estornar_resgate(db, carteira, pendente, "cancelado", momento)
    return pendente.custo_creditos if devolvido else 0


def buscar_para_o_caixa(db: Session, codigo: str, momento: datetime | None = None) -> models.Resgate:
    """O caixa digitou o código: acha o resgate em aberto (sem confirmar ainda)."""
    momento = momento or regras.agora()
    candidatos = (db.query(models.Resgate)
                  .filter(models.Resgate.codigo == codigo, models.Resgate.status == "pendente")
                  .all())
    valido = next((r for r in candidatos if r.expira_em > momento), None)
    if valido is not None:
        return valido
    if candidatos:
        # Expired while the customer waited: refund now, so the customer sees the credits back.
        for resgate in candidatos:
            regras.estornar_resgate(db, _carteira_travada(db, resgate.carteira_id), resgate, "expirado",
                             resgate.expira_em)
        raise ResgateRecusado("resgate_expirado")
    raise ResgateRecusado("resgate_inexistente")


def confirmar(db: Session, operador: models.Usuario, codigo: str,
              momento: datetime | None = None) -> models.Resgate:
    """Caixa entregou o prêmio. Os créditos já tinham saído na reserva: aqui só fecha o resgate."""
    momento = momento or regras.agora()
    resgate = buscar_para_o_caixa(db, codigo, momento)
    if not regras.mudar_status_se_pendente(db, resgate, "confirmado",
                                           confirmado_em=momento, confirmado_por=operador.id):
        raise ResgateRecusado("resgate_inexistente")  # cancelled or confirmed a moment ago
    return resgate
