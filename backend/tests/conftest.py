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
# The developer's backend/.env may turn the dev shortcut on; tests must see the default.
os.environ["OTP_MOSTRAR_NO_APP"] = "0"

import pytest  # noqa: E402
from sqlalchemy import event, inspect  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from passlib.context import CryptContext  # noqa: E402

from app import models  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

SENHA = "senha1234"
TEL_CAIXA = "83988887777"
TEL_ADMIN = "83977776666"
TEL_CLIENTE = "83999998888"

# bcrypt is slow on purpose (~0.45 s per check, cost 12). The cost is stored inside the
# hash, so test users get the minimum cost (4): logins in tests become instant while
# the API keeps verifying real passwords exactly as in production.
_pwd = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4)
SENHA_HASH = _pwd.hash(SENHA)


@event.listens_for(engine, "connect")
def _sqlite_rapido(conexao, _registro):
    # Test-only: skip forcing every write to disk. On Windows each fsync also goes
    # through the antivirus, which made the suite take minutes. Never do this in prod.
    cursor = conexao.cursor()
    cursor.execute("PRAGMA synchronous=OFF")
    cursor.execute("PRAGMA journal_mode=MEMORY")
    cursor.close()


@pytest.fixture(scope="session", autouse=True)
def esquema():
    """Cria as tabelas uma vez só para a sessão inteira de testes."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def banco_limpo(esquema):
    """Cada teste começa com as tabelas vazias e os mesmos usuários de exemplo.

    Apagar as linhas é bem mais rápido que recriar as tabelas a cada teste.
    """
    if not inspect(engine).has_table("usuarios"):  # test_migracoes dropped everything
        Base.metadata.create_all(bind=engine)
    with engine.begin() as conexao:
        for tabela in reversed(Base.metadata.sorted_tables):  # children before parents
            conexao.execute(tabela.delete())
    db = SessionLocal()
    try:
        senha_hash = SENHA_HASH
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
