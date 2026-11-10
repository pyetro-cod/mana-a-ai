import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, true
from sqlalchemy.orm import relationship

from .database import Base


def gen_uuid():
    return str(uuid.uuid4())


def agora_utc() -> datetime:
    """UTC without tzinfo, the format every DateTime column stores.

    Replaces datetime.utcnow(), deprecated since Python 3.12.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Single store for now; the column exists so a partner network can be added later
# without migrating every row.
ESTABELECIMENTO_PADRAO = "manacai"

# Why a ledger entry happened. "manual" covers entries made before coupons existed.
MOTIVOS_TRANSACAO = ("manual", "cupom", "bonus", "resgate", "estorno_resgate", "expiracao")


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(String, primary_key=True, default=gen_uuid)
    nome = Column(String, nullable=False)
    telefone = Column(String, unique=True, index=True, nullable=False)
    perfil = Column(String, nullable=False, default="cliente")  # cliente | caixa | admin
    senha_hash = Column(String, nullable=True)  # só usado por caixa/admin no MVP

    carteira = relationship("Carteira", back_populates="usuario", uselist=False)


class Carteira(Base):
    __tablename__ = "carteiras"

    id = Column(String, primary_key=True, default=gen_uuid)
    usuario_id = Column(String, ForeignKey("usuarios.id"), unique=True, nullable=False)
    saldo = Column(Integer, nullable=False, default=0)
    # Drives inactivity expiry: the balance expires N days after the last purchase.
    ultima_compra_em = Column(DateTime, nullable=True)

    usuario = relationship("Usuario", back_populates="carteira")
    transacoes = relationship("Transacao", back_populates="carteira")


class Produto(Base):
    __tablename__ = "produtos"

    id = Column(String, primary_key=True, default=gen_uuid)
    nome = Column(String, nullable=False)
    valor_creditos = Column(Integer, nullable=False)


class Transacao(Base):
    __tablename__ = "transacoes"

    id = Column(String, primary_key=True, default=gen_uuid)
    carteira_id = Column(String, ForeignKey("carteiras.id"), nullable=False)
    produto_id = Column(String, ForeignKey("produtos.id"), nullable=True)
    tipo = Column(String, nullable=False)  # credito | debito
    valor = Column(Integer, nullable=False)
    motivo = Column(String, nullable=False, default="manual", server_default="manual")
    cupom_id = Column(String, ForeignKey("cupons.id"), nullable=True)
    resgate_id = Column(String, ForeignKey("resgates.id"), nullable=True)
    operador_id = Column(String, ForeignKey("usuarios.id"), nullable=True)  # caixa/admin que agiu, se houver
    criado_em = Column(DateTime, default=agora_utc)

    carteira = relationship("Carteira", back_populates="transacoes")
    produto = relationship("Produto")


class CodigoAcesso(Base):
    """Código de uso único enviado ao cliente para login (OTP)."""
    __tablename__ = "codigos_acesso"

    id = Column(String, primary_key=True, default=gen_uuid)
    telefone = Column(String, index=True, nullable=False)
    codigo_hash = Column(String, nullable=False)  # HMAC do código, nunca o código em texto
    tentativas = Column(Integer, nullable=False, default=0)
    criado_em = Column(DateTime, nullable=False, default=agora_utc)
    expira_em = Column(DateTime, nullable=False)
    usado_em = Column(DateTime, nullable=True)


class Consentimento(Base):
    """Registro do aceite dos termos (LGPD): quem aceitou, qual versão e quando."""
    __tablename__ = "consentimentos"

    id = Column(String, primary_key=True, default=gen_uuid)
    usuario_id = Column(String, ForeignKey("usuarios.id"), index=True, nullable=False)
    versao_termos = Column(String, nullable=False)
    aceito_em = Column(DateTime, nullable=False, default=agora_utc)


class Estabelecimento(Base):
    __tablename__ = "estabelecimentos"

    id = Column(String, primary_key=True)
    nome = Column(String, nullable=False)
    criado_em = Column(DateTime, nullable=False, default=agora_utc)


class Configuracao(Base):
    """Regras do programa que o admin pode mudar sem mexer no código (uma linha por loja)."""
    __tablename__ = "configuracoes"

    estabelecimento_id = Column(String, ForeignKey("estabelecimentos.id"), primary_key=True)
    creditos_por_cupom = Column(Integer, nullable=False, default=50)
    bonus_boas_vindas = Column(Integer, nullable=False, default=100)
    validade_cupom_dias = Column(Integer, nullable=False, default=7)
    dias_expiracao_saldo = Column(Integer, nullable=False, default=30)
    validade_resgate_minutos = Column(Integer, nullable=False, default=10)
    max_cupons_por_dia = Column(Integer, nullable=False, default=1)
    atualizado_em = Column(DateTime, nullable=False, default=agora_utc)


class LoteCupom(Base):
    """Conjunto de cupons gerados de uma vez pelo admin para imprimir."""
    __tablename__ = "lotes_cupom"

    id = Column(String, primary_key=True, default=gen_uuid)
    estabelecimento_id = Column(String, ForeignKey("estabelecimentos.id"), nullable=False)
    quantidade = Column(Integer, nullable=False)
    creditos = Column(Integer, nullable=False)  # copied from the config at creation time
    criado_por = Column(String, ForeignKey("usuarios.id"), nullable=False)
    criado_em = Column(DateTime, nullable=False, default=agora_utc)
    expira_em = Column(DateTime, nullable=False)
    # Set when a printed sheet is lost or stolen: its unused coupons stop working.
    cancelado_em = Column(DateTime, nullable=True)

    cupons = relationship("Cupom", back_populates="lote")


class Cupom(Base):
    """Um QR impresso: vale uma vez, até expirar."""
    __tablename__ = "cupons"

    id = Column(String, primary_key=True, default=gen_uuid)
    lote_id = Column(String, ForeignKey("lotes_cupom.id"), index=True, nullable=False)
    codigo = Column(String, unique=True, index=True, nullable=False)
    creditos = Column(Integer, nullable=False)
    expira_em = Column(DateTime, nullable=False)
    usado_em = Column(DateTime, nullable=True)
    usado_por = Column(String, ForeignKey("usuarios.id"), nullable=True)

    lote = relationship("LoteCupom", back_populates="cupons")


class Premio(Base):
    """O que o cliente pode trocar e quanto custa em créditos."""
    __tablename__ = "premios"

    id = Column(String, primary_key=True, default=gen_uuid)
    estabelecimento_id = Column(String, ForeignKey("estabelecimentos.id"), nullable=False)
    nome = Column(String, nullable=False)
    custo_creditos = Column(Integer, nullable=False)
    ativo = Column(Boolean, nullable=False, default=True, server_default=true())
    criado_em = Column(DateTime, nullable=False, default=agora_utc)


class Resgate(Base):
    """Troca de créditos por um prêmio: o cliente gera o código, o caixa confirma."""
    __tablename__ = "resgates"

    id = Column(String, primary_key=True, default=gen_uuid)
    carteira_id = Column(String, ForeignKey("carteiras.id"), index=True, nullable=False)
    premio_id = Column(String, ForeignKey("premios.id"), nullable=False)
    codigo = Column(String, index=True, nullable=False)  # 6 digits, unique among pending ones
    custo_creditos = Column(Integer, nullable=False)  # price at the time of the request
    status = Column(String, nullable=False, default="pendente")  # pendente | confirmado | expirado | cancelado
    criado_em = Column(DateTime, nullable=False, default=agora_utc)
    expira_em = Column(DateTime, nullable=False)
    confirmado_em = Column(DateTime, nullable=True)
    confirmado_por = Column(String, ForeignKey("usuarios.id"), nullable=True)

    premio = relationship("Premio")


class TentativaFalha(Base):
    """Uma tentativa errada (senha do painel, código de cupom inexistente).

    Fica no banco, e não na memória do servidor, porque na Vercel cada requisição
    pode cair numa instância diferente: um contador em memória zeraria sozinho.
    """
    __tablename__ = "tentativas_falhas"

    id = Column(String, primary_key=True, default=gen_uuid)
    tipo = Column(String, nullable=False)   # login | cupom
    chave = Column(String, nullable=False)  # telefone (login) ou id do cliente (cupom)
    criado_em = Column(DateTime, nullable=False, default=agora_utc)

    __table_args__ = (Index("ix_tentativas_tipo_chave_criado", "tipo", "chave", "criado_em"),)
