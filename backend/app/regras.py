"""Regras do programa de créditos: cupom, bônus de boas-vindas e expiração do saldo.

Todas as funções recebem a sessão e NÃO fazem commit: quem chama decide quando
gravar, para que saldo e histórico (ledger) mudem juntos numa única transação.
"""
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from . import models

# João Pessoa: UTC-3 o ano todo (o Brasil não tem horário de verão desde 2019).
# "1 cupom por dia" é o dia do calendário da loja, não as últimas 24 horas.
FUSO_LOJA = timezone(timedelta(hours=-3))


# No 0/O, 1/I/L: a customer typing the code by hand cannot confuse them.
ALFABETO_CUPOM = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
TAMANHO_CUPOM = 10  # 31^10 ≈ 8 * 10^14 possibilities: guessing a valid one is hopeless


class CupomRecusado(Exception):
    """Cupom não pode ser usado. `motivo` vai para o app traduzir em mensagem."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo  # cupom_inexistente | cupom_ja_usado | cupom_expirado | cupom_cancelado | limite_diario


def agora() -> datetime:
    """UTC sem fuso (naive), o mesmo formato das colunas DateTime do banco."""
    return models.agora_utc()


def inicio_do_dia_na_loja(momento: datetime) -> datetime:
    """Meia-noite (horário da loja) do dia de `momento`, convertida de volta para UTC naive."""
    local = momento.replace(tzinfo=timezone.utc).astimezone(FUSO_LOJA)
    meia_noite = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return meia_noite.astimezone(timezone.utc).replace(tzinfo=None)


def gerar_codigo_cupom() -> str:
    # `secrets`, not `random`: random's sequence can be predicted from a few outputs.
    return "".join(secrets.choice(ALFABETO_CUPOM) for _ in range(TAMANHO_CUPOM))


def formatar_codigo(codigo: str) -> str:
    """ABCDEFGHJK -> ABCDE-FGHJK (only for printing; the app strips the hyphen)."""
    meio = len(codigo) // 2
    return f"{codigo[:meio]}-{codigo[meio:]}"


def gerar_lote(db: Session, admin: models.Usuario, quantidade: int,
               momento: datetime | None = None) -> models.LoteCupom:
    """Cria um lote com códigos únicos, usando as regras atuais (créditos e validade). Sem commit."""
    momento = momento or agora()
    config = configuracao(db)
    expira = momento + timedelta(days=config.validade_cupom_dias)

    codigos: set[str] = set()
    while len(codigos) < quantidade:
        faltam = {gerar_codigo_cupom() for _ in range(quantidade - len(codigos))}
        ja_existem = {c for (c,) in db.query(models.Cupom.codigo).filter(models.Cupom.codigo.in_(faltam))}
        codigos |= faltam - ja_existem

    lote = models.LoteCupom(estabelecimento_id=models.ESTABELECIMENTO_PADRAO, quantidade=quantidade,
                            creditos=config.creditos_por_cupom, criado_por=admin.id,
                            criado_em=momento, expira_em=expira)
    db.add(lote)
    db.flush()
    db.add_all(models.Cupom(lote_id=lote.id, codigo=c, creditos=lote.creditos, expira_em=expira)
               for c in sorted(codigos))
    return lote


def configuracao(db: Session) -> models.Configuracao:
    config = db.get(models.Configuracao, models.ESTABELECIMENTO_PADRAO)
    if config is None:
        raise RuntimeError("Configuração da loja ausente: rode `alembic upgrade head`.")
    return config


def vence_em(carteira: models.Carteira, config: models.Configuracao):
    """Quando o saldo atual vence, ou None se não há saldo (ou o relógio ainda não começou)."""
    if carteira.saldo <= 0 or carteira.ultima_compra_em is None:
        return None
    return carteira.ultima_compra_em + timedelta(days=config.dias_expiracao_saldo)


def estornar_resgates_vencidos(db: Session, carteira: models.Carteira,
                               momento: datetime | None = None) -> int:
    """Código de resgate que venceu sem o caixa confirmar: os créditos reservados voltam.

    Mesmo princípio da expiração do saldo: roda quando alguém olha a carteira.
    Devolve quanto foi estornado.
    """
    momento = momento or agora()
    vencidos = (db.query(models.Resgate)
                .filter(models.Resgate.carteira_id == carteira.id,
                        models.Resgate.status == "pendente",
                        models.Resgate.expira_em <= momento)
                .all())
    return sum(r.custo_creditos for r in vencidos
               if estornar_resgate(db, carteira, r, "expirado", r.expira_em))


def estornar_resgate(db: Session, carteira: models.Carteira, resgate: models.Resgate,
                     novo_status: str, quando: datetime) -> bool:
    """Fecha um resgate pendente devolvendo os créditos. False se ele já não estava pendente.

    Atualização condicional, como no cupom: se o caixa confirmar no mesmo instante em
    que o cliente cancela, só uma das duas mudanças acontece, nunca prêmio + estorno.
    """
    if not mudar_status_se_pendente(db, resgate, novo_status):
        return False
    carteira.saldo += resgate.custo_creditos
    db.add(models.Transacao(carteira_id=carteira.id, tipo="credito", valor=resgate.custo_creditos,
                            motivo="estorno_resgate", resgate_id=resgate.id, criado_em=quando))
    return True


def mudar_status_se_pendente(db: Session, resgate: models.Resgate, novo_status: str, **campos) -> bool:
    resultado = db.execute(
        update(models.Resgate)
        .where(models.Resgate.id == resgate.id, models.Resgate.status == "pendente")
        .values(status=novo_status, **campos)
        .execution_options(synchronize_session="fetch")
    )
    return resultado.rowcount == 1


def atualizar_carteira(db: Session, carteira: models.Carteira, config: models.Configuracao,
                       momento: datetime | None = None) -> None:
    """Põe a carteira em dia antes de mostrar ou mexer no saldo.

    Ordem: primeiro devolve resgates vencidos, depois expira o saldo. Assim um
    estorno de créditos que já estavam vencidos também expira, em vez de escapar.
    """
    momento = momento or agora()
    estornar_resgates_vencidos(db, carteira, momento)
    aplicar_expiracao(db, carteira, config, momento)


def aplicar_expiracao(db: Session, carteira: models.Carteira, config: models.Configuracao,
                      momento: datetime | None = None) -> int:
    """Zera o saldo vencido por inatividade, registrando um débito `expiracao`.

    Roda "na hora da leitura" (ao abrir o extrato, ao usar um cupom...): não precisa
    de um agendador, e o resultado é o mesmo, porque ninguém vê o saldo sem passar aqui.
    Devolve quanto expirou (0 se nada).
    """
    momento = momento or agora()

    if carteira.saldo > 0 and carteira.ultima_compra_em is None:
        # Carteira de antes da regra existir: o prazo começa a contar agora,
        # em vez de apagar de surpresa um saldo que o cliente acumulou de boa-fé.
        carteira.ultima_compra_em = momento
        return 0

    vencimento = vence_em(carteira, config)
    if vencimento is None or momento < vencimento:
        return 0

    expirado = carteira.saldo
    carteira.saldo = 0
    db.add(models.Transacao(
        carteira_id=carteira.id,
        tipo="debito",
        valor=expirado,
        motivo="expiracao",
        criado_em=vencimento,  # o extrato mostra quando venceu, não quando foi notado
    ))
    return expirado


def resgatar_cupom(db: Session, cliente: models.Usuario, codigo: str,
                   momento: datetime | None = None) -> dict:
    """Credita um cupom (e o bônus, se for o primeiro) na carteira do cliente.

    Levanta CupomRecusado. Não faz commit.
    """
    momento = momento or agora()
    config = configuracao(db)

    # Trava a carteira: dois cupons do mesmo cliente ao mesmo tempo não podem
    # ler o mesmo saldo e um sobrescrever o outro.
    carteira = (db.query(models.Carteira)
                .filter(models.Carteira.id == cliente.carteira.id)
                .with_for_update().one())

    cupom = db.query(models.Cupom).filter(models.Cupom.codigo == codigo).first()
    if cupom is None:
        raise CupomRecusado("cupom_inexistente")
    if cupom.usado_em is not None:
        raise CupomRecusado("cupom_ja_usado")
    if cupom.lote.cancelado_em is not None:
        raise CupomRecusado("cupom_cancelado")
    if momento >= cupom.expira_em:
        raise CupomRecusado("cupom_expirado")

    usados_hoje = (db.query(models.Transacao)
                   .filter(models.Transacao.carteira_id == carteira.id,
                           models.Transacao.motivo == "cupom",
                           models.Transacao.criado_em >= inicio_do_dia_na_loja(momento))
                   .count())
    if usados_hoje >= config.max_cupons_por_dia:
        raise CupomRecusado("limite_diario")

    # Marca o cupom como usado SÓ se ainda estiver livre, numa única instrução.
    # Se duas pessoas escanearem o mesmo QR no mesmo instante, o banco deixa
    # apenas uma das atualizações acontecer; a outra afeta 0 linhas e é recusada.
    resultado = db.execute(
        update(models.Cupom)
        .where(models.Cupom.id == cupom.id, models.Cupom.usado_em.is_(None))
        .values(usado_em=momento, usado_por=cliente.id)
    )
    if resultado.rowcount != 1:
        raise CupomRecusado("cupom_ja_usado")

    # Saldo vencido expira ANTES do crédito novo: senão a compra de hoje
    # "ressuscitaria" créditos que já tinham vencido.
    estornar_resgates_vencidos(db, carteira, momento)
    expirado = aplicar_expiracao(db, carteira, config, momento)

    ja_ganhou_bonus = (db.query(models.Transacao)
                       .filter(models.Transacao.carteira_id == carteira.id,
                               models.Transacao.motivo == "bonus")
                       .first() is not None)
    bonus = 0 if ja_ganhou_bonus else config.bonus_boas_vindas

    db.add(models.Transacao(carteira_id=carteira.id, tipo="credito", valor=cupom.creditos,
                            motivo="cupom", cupom_id=cupom.id, criado_em=momento))
    if bonus > 0:
        db.add(models.Transacao(carteira_id=carteira.id, tipo="credito", valor=bonus,
                                motivo="bonus", cupom_id=cupom.id, criado_em=momento))

    carteira.saldo += cupom.creditos + bonus
    carteira.ultima_compra_em = momento  # toda compra renova o prazo do saldo inteiro

    return {
        "creditos": cupom.creditos,
        "bonus": bonus,
        "expirado": expirado,
        "novo_saldo": carteira.saldo,
        "vence_em": vence_em(carteira, config),
    }
