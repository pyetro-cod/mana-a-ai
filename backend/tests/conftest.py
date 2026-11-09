"""Ambiente isolado para os testes: banco SQLite temporário e segredo de teste.

As variáveis precisam existir ANTES de importar o app, porque config.py e
database.py leem o ambiente no momento do import.
"""
import os
import tempfile
from pathlib import Path

_tmp_dir = tempfile.mkdtemp(prefix="mana-testes-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp_dir, 'teste.db').as_posix()}"
os.environ["JWT_SECRET"] = "segredo-exclusivo-dos-testes-com-mais-de-32-caracteres"
os.environ["JWT_EXPIRE_MINUTES"] = "480"
os.environ["CORS_ORIGINS"] = "http://localhost:5500"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from passlib.context import CryptContext  # noqa: E402

from app import models  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

SENHA = "senha1234"
TEL_CAIXA = "83988887777"
TEL_ADMIN = "83977776666"
TEL_CLIENTE = "83999998888"

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture(autouse=True)
def banco_limpo():
    """Cada teste começa com um banco novo e os mesmos usuários de exemplo."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        senha_hash = _pwd.hash(SENHA)
        db.add_all([
            models.Usuario(nome="Caixa", telefone=TEL_CAIXA, perfil="caixa", senha_hash=senha_hash),
            models.Usuario(nome="Admin", telefone=TEL_ADMIN, perfil="admin", senha_hash=senha_hash),
        ])
        cliente = models.Usuario(nome="Ana", telefone=TEL_CLIENTE, perfil="cliente")
        db.add(cliente)
        db.flush()
        db.add(models.Carteira(usuario_id=cliente.id, saldo=50))
        # Same rows migration 0002 seeds in the real database.
        db.add(models.Estabelecimento(id=models.ESTABELECIMENTO_PADRAO, nome="Manaçaí"))
        db.flush()
        db.add(models.Configuracao(estabelecimento_id=models.ESTABELECIMENTO_PADRAO))
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def login(client, telefone):
    res = client.post("/auth/login", json={"telefone": telefone, "senha": SENHA})
    assert res.status_code == 200, res.text
    return res.json()["token"]


@pytest.fixture
def token_caixa(client):
    return login(client, TEL_CAIXA)


@pytest.fixture
def token_admin(client):
    return login(client, TEL_ADMIN)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def usuario_id(telefone):
    db = SessionLocal()
    try:
        return db.query(models.Usuario).filter_by(telefone=telefone).one().id
    finally:
        db.close()


@pytest.fixture
def codigos_enviados(monkeypatch):
    """Intercepta o envio: em vez de WhatsApp/terminal, guarda {telefone: último código}."""
    from app import otp
    enviados = {}
    monkeypatch.setattr(otp, "enviar_codigo", lambda telefone, codigo: enviados.__setitem__(telefone, codigo))
    return enviados


def entrar_como_cliente(client, codigos_enviados, telefone=TEL_CLIENTE, **cadastro):
    assert client.post("/auth/cliente/codigo", json={"telefone": telefone}).status_code == 202
    res = client.post("/auth/cliente/entrar",
                      json={"telefone": telefone, "codigo": codigos_enviados[telefone], **cadastro})
    assert res.status_code == 200, res.text
    return res.json()["token"]
