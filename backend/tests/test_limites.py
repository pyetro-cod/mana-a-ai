"""Correções: limite de tentativas erradas e lançamento manual só do admin."""
from datetime import timedelta

from app import limites, models
from app.database import SessionLocal

from .conftest import SENHA, TEL_ADMIN, TEL_CAIXA, TEL_CLIENTE, auth, entrar_como_cliente


def _login(client, telefone, senha):
    return client.post("/auth/login", json={"telefone": telefone, "senha": senha})


def _envelhecer_falhas(minutos):
    db = SessionLocal()
    try:
        for t in db.query(models.TentativaFalha):
            t.criado_em -= timedelta(minutes=minutos)
        db.commit()
    finally:
        db.close()


# ---------- login do painel ----------

def test_login_bloqueia_depois_de_5_senhas_erradas(client):
    for _ in range(5):
        assert _login(client, TEL_CAIXA, "senha-errada").status_code == 401
    res = _login(client, TEL_CAIXA, SENHA)  # even the right password waits
    assert res.status_code == 429
    assert int(res.headers["retry-after"]) > 0


def test_bloqueio_do_login_passa_com_o_tempo(client):
    for _ in range(5):
        _login(client, TEL_CAIXA, "senha-errada")
    _envelhecer_falhas(16)
    assert _login(client, TEL_CAIXA, SENHA).status_code == 200


def test_acertar_a_senha_zera_as_falhas(client):
    for _ in range(4):
        _login(client, TEL_CAIXA, "senha-errada")
    assert _login(client, TEL_CAIXA, SENHA).status_code == 200
    for _ in range(4):
        assert _login(client, TEL_CAIXA, "senha-errada").status_code == 401
    assert _login(client, TEL_CAIXA, SENHA).status_code == 200


def test_bloqueio_de_um_telefone_nao_afeta_outro(client):
    for _ in range(5):
        _login(client, TEL_CAIXA, "senha-errada")
    assert _login(client, TEL_ADMIN, SENHA).status_code == 200


def test_telefone_inexistente_tambem_e_limitado(client):
    """Senão o 429 revelaria quais telefones têm conta no painel."""
    for _ in range(5):
        assert _login(client, "83911112222", "qualquer-coisa").status_code == 401
    assert _login(client, "83911112222", "qualquer-coisa").status_code == 429


# ---------- código de cupom ----------

def test_cupom_bloqueia_depois_de_10_codigos_inventados(client, codigos_enviados):
    token = entrar_como_cliente(client, codigos_enviados, TEL_CLIENTE)
    for i in range(limites.REGRAS["cupom"][0]):
        res = client.post("/clientes/me/cupons", json={"codigo": f"CHUTE{i:04d}"}, headers=auth(token))
        assert res.status_code == 404
    res = client.post("/clientes/me/cupons", json={"codigo": "CHUTE9999"}, headers=auth(token))
    assert (res.status_code, res.json()["detail"]) == (429, "muitas_tentativas")


# ---------- lançamento manual ----------

def test_caixa_nao_faz_lancamento_manual(client, token_caixa):
    carteira_id = client.get("/clientes", params={"telefone": TEL_CLIENTE},
                             headers=auth(token_caixa)).json()["carteira"]["id"]
    res = client.post("/transacoes", headers=auth(token_caixa),
                      json={"carteira_id": carteira_id, "tipo": "credito", "valor": 10})
    assert res.status_code == 403
