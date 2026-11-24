"""Limite de tentativas erradas: freia quem tenta adivinhar senha ou código de cupom.

Janela deslizante: conta as falhas dos últimos N minutos. Passou do máximo, a porta
fecha até a falha mais antiga da janela "sair" dela.
"""
from datetime import timedelta

from sqlalchemy.orm import Session

from . import models

# tipo -> (máximo de falhas, janela)
REGRAS = {
    # 5 wrong passwords per phone in 15 min: a person who forgot the password is not
    # bothered, but guessing a password at that speed takes years.
    "login": (5, timedelta(minutes=15)),
    # 10 unknown coupon codes per customer per hour: typos are fine, guessing is not.
    "cupom": (10, timedelta(hours=1)),
}


class LimiteExcedido(Exception):
    def __init__(self, segundos_para_tentar: int):
        super().__init__(segundos_para_tentar)
        self.segundos_para_tentar = segundos_para_tentar


def checar(db: Session, tipo: str, chave: str) -> None:
    """Levanta LimiteExcedido se essa chave já errou demais na janela."""
    maximo, janela = REGRAS[tipo]
    agora = models.agora_utc()
    falhas = (db.query(models.TentativaFalha.criado_em)
              .filter(models.TentativaFalha.tipo == tipo,
                      models.TentativaFalha.chave == chave,
                      models.TentativaFalha.criado_em > agora - janela)
              .order_by(models.TentativaFalha.criado_em)
              .all())
    if len(falhas) >= maximo:
        libera_em = falhas[0].criado_em + janela
        raise LimiteExcedido(max(1, int((libera_em - agora).total_seconds()) + 1))


def registrar_falha(db: Session, tipo: str, chave: str) -> None:
    """Grava a falha JÁ com commit: a requisição vai terminar em erro, e um rollback
    depois apagaria justamente o registro que serve para frear o próximo chute."""
    db.add(models.TentativaFalha(tipo=tipo, chave=chave))
    db.commit()


def limpar(db: Session, tipo: str, chave: str) -> None:
    """Acertou: zera as falhas dessa chave (sem commit)."""
    (db.query(models.TentativaFalha)
     .filter(models.TentativaFalha.tipo == tipo, models.TentativaFalha.chave == chave)
     .delete(synchronize_session=False))
