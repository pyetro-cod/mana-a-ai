import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from .database import Base


def gen_uuid():
    return str(uuid.uuid4())


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
    criado_em = Column(DateTime, default=datetime.utcnow)

    carteira = relationship("Carteira", back_populates="transacoes")
    produto = relationship("Produto")
