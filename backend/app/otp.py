"""Códigos de acesso de uso único (OTP) para o login do cliente."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import models
from .config import settings
from .envio_codigo import enviar_codigo

DIGITOS = 6
MAX_TENTATIVAS = 5
INTERVALO_MINIMO_SEGUNDOS = 60
MAX_CODIGOS_POR_HORA = 5


class LimiteExcedido(Exception):
    def __init__(self, segundos_para_tentar: int):
        super().__init__(segundos_para_tentar)
        self.segundos_para_tentar = segundos_para_tentar


class CodigoInvalido(Exception):
    pass


def _agora() -> datetime:
    # Naive UTC, matching how the existing models store datetimes.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash(telefone: str, codigo: str) -> str:
    # Keyed hash: with only 10^6 possible codes, a plain SHA-256 could be reversed
    # by brute force if the database leaked. Without JWT_SECRET it cannot.
    mensagem = f"{telefone}:{codigo}".encode()
    return hmac.new(settings.jwt_secret.encode(), mensagem, hashlib.sha256).hexdigest()


def _checar_limites(db: Session, telefone: str) -> None:
    agora = _agora()
    recentes = (
        db.query(models.CodigoAcesso)
        .filter(models.CodigoAcesso.telefone == telefone,
                models.CodigoAcesso.criado_em > agora - timedelta(hours=1))
        .order_by(models.CodigoAcesso.criado_em.desc())
        .all()
    )
    if recentes:
        desde_ultimo = (agora - recentes[0].criado_em).total_seconds()
        if desde_ultimo < INTERVALO_MINIMO_SEGUNDOS:
            raise LimiteExcedido(int(INTERVALO_MINIMO_SEGUNDOS - desde_ultimo) + 1)
    if len(recentes) >= MAX_CODIGOS_POR_HORA:
        mais_antigo = recentes[-1].criado_em
        raise LimiteExcedido(int((mais_antigo + timedelta(hours=1) - agora).total_seconds()) + 1)


def solicitar_codigo(db: Session, telefone: str) -> None:
    """Gera, guarda (só o hash) e envia um código novo. Códigos anteriores deixam de valer."""
    _checar_limites(db, telefone)

    agora = _agora()
    db.query(models.CodigoAcesso).filter(
        models.CodigoAcesso.telefone == telefone,
        models.CodigoAcesso.usado_em.is_(None),
        models.CodigoAcesso.expira_em > agora,
    ).update({"expira_em": agora}, synchronize_session=False)

    # secrets, not random: random's output can be predicted from earlier values.
    codigo = f"{secrets.randbelow(10 ** DIGITOS):0{DIGITOS}d}"
    registro = models.CodigoAcesso(
        telefone=telefone,
        codigo_hash=_hash(telefone, codigo),
        criado_em=agora,
        expira_em=agora + timedelta(minutes=settings.otp_expire_minutes),
    )
    db.add(registro)
    db.commit()

    try:
        enviar_codigo(telefone, codigo)
    except Exception:
        # A code the customer never received must not count against their rate limit.
        db.delete(registro)
        db.commit()
        raise


def conferir_codigo(db: Session, telefone: str, codigo: str, consumir: bool = True) -> None:
    """Valida o código mais recente do telefone. Erro conta tentativa; acerto consome o código
    (a menos que consumir=False, usado quando ainda falta completar o cadastro)."""
    agora = _agora()
    registro = (
        db.query(models.CodigoAcesso)
        .filter(models.CodigoAcesso.telefone == telefone,
                models.CodigoAcesso.usado_em.is_(None),
                models.CodigoAcesso.expira_em > agora)
        .order_by(models.CodigoAcesso.criado_em.desc())
        .first()
    )
    if not registro or registro.tentativas >= MAX_TENTATIVAS:
        raise CodigoInvalido()

    # compare_digest takes the same time whether the first or the last character differs.
    if not hmac.compare_digest(registro.codigo_hash, _hash(telefone, codigo)):
        registro.tentativas += 1
        db.commit()
        raise CodigoInvalido()

    if consumir:
        registro.usado_em = agora
        db.commit()
