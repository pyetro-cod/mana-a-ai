"""Critério de saída da fase 2: nenhuma rota do caixa aceita token forjado,
o CORS só libera o front e a API recusa entrada que vire HTML/JS."""
import time

import jwt
import pytest

from app import models
from app.config import settings
from app.database import SessionLocal

from .conftest import SENHA, TEL_CAIXA, TEL_CLIENTE, auth, usuario_id


def _token(payload, segredo=None, algoritmo="HS256"):
    return jwt.encode(payload, segredo or settings.jwt_secret, algorithm=algoritmo)


def _payload(sub, perfil="caixa", exp_em_segundos=3600):
    agora = int(time.time())
    return {"sub": sub, "perfil": perfil, "iat": agora, "exp": agora + exp_em_segundos}


# ---------- login ----------

def test_login_devolve_jwt_valido(client):
    res = client.post("/auth/login", json={"telefone": TEL_CAIXA, "senha": SENHA})
    assert res.status_code == 200
    dados = jwt.decode(res.json()["token"], settings.jwt_secret, algorithms=["HS256"])
    assert dados["perfil"] == "caixa"
    assert dados["exp"] - dados["iat"] == settings.jwt_expire_minutes * 60


def test_login_com_senha_errada_recusado(client):
    res = client.post("/auth/login", json={"telefone": TEL_CAIXA, "senha": "senhaerrada"})
    assert res.status_code == 401


def test_cliente_nao_faz_login_no_painel(client):
    res = client.post("/auth/login", json={"telefone": TEL_CLIENTE, "senha": SENHA})
    assert res.status_code == 401


# ---------- tokens inválidos nas rotas do caixa ----------

def test_token_valido_acessa_rota_do_caixa(client, token_caixa):
    assert client.get("/produtos", headers=auth(token_caixa)).status_code == 200


@pytest.mark.parametrize("cabecalho", [
    {},
    {"Authorization": "Bearer "},
    {"Authorization": "Basic dXNlcjpzZW5oYQ=="},
    {"Authorization": "Bearer nao-e-um-jwt"},
])
def test_sem_token_ou_token_malformado_recusado(client, cabecalho):
    assert client.get("/produtos", headers=cabecalho).status_code == 401


def test_stub_antigo_recusado(client):
    res = client.get("/produtos", headers=auth(f"stub-token.{usuario_id(TEL_CAIXA)}"))
    assert res.status_code == 401


def test_token_assinado_com_outro_segredo_recusado(client):
    falso = _token(_payload(usuario_id(TEL_CAIXA), "admin"), segredo="segredo-do-atacante-com-mais-de-32-chars")
    assert client.get("/produtos", headers=auth(falso)).status_code == 401


def test_token_adulterado_recusado(client, token_caixa):
    cabecalho, _, assinatura = token_caixa.split(".")
    dados_admin = jwt.utils.base64url_encode(
        jwt.api_jws.json.dumps(_payload(usuario_id(TEL_CAIXA), "admin")).encode()
    ).decode()
    adulterado = f"{cabecalho}.{dados_admin}.{assinatura}"
    res = client.post("/produtos", headers=auth(adulterado), json={"nome": "Hack", "valor_creditos": 1})
    assert res.status_code == 401


def test_token_expirado_recusado(client):
    expirado = _token(_payload(usuario_id(TEL_CAIXA), exp_em_segundos=-60))
    res = client.get("/produtos", headers=auth(expirado))
    assert res.status_code == 401
    assert "expirada" in res.json()["detail"]


def test_token_sem_assinatura_alg_none_recusado(client):
    sem_assinatura = jwt.encode(_payload(usuario_id(TEL_CAIXA), "admin"), None, algorithm="none")
    assert client.get("/produtos", headers=auth(sem_assinatura)).status_code == 401


def test_token_sem_exp_recusado(client):
    agora = int(time.time())
    sem_exp = _token({"sub": usuario_id(TEL_CAIXA), "perfil": "caixa", "iat": agora})
    assert client.get("/produtos", headers=auth(sem_exp)).status_code == 401


def test_token_de_usuario_inexistente_recusado(client):
    fantasma = _token(_payload("id-que-nao-existe"))
    assert client.get("/produtos", headers=auth(fantasma)).status_code == 401


def test_token_de_cliente_recusado_nas_rotas_do_caixa(client):
    token_cliente = _token(_payload(usuario_id(TEL_CLIENTE), "cliente"))
    assert client.get("/produtos", headers=auth(token_cliente)).status_code == 401


def test_caixa_rebaixado_perde_acesso_antes_do_token_expirar(client, token_caixa):
    db = SessionLocal()
    try:
        db.query(models.Usuario).filter_by(telefone=TEL_CAIXA).update({"perfil": "cliente"})
        db.commit()
    finally:
        db.close()
    assert client.get("/produtos", headers=auth(token_caixa)).status_code == 401


# ---------- permissões por perfil ----------

def test_caixa_nao_gerencia_catalogo(client, token_caixa):
    res = client.post("/produtos", headers=auth(token_caixa), json={"nome": "Teste", "valor_creditos": 1})
    assert res.status_code == 403


def test_admin_gerencia_catalogo(client, token_admin):
    res = client.post("/produtos", headers=auth(token_admin), json={"nome": "Açaí 500ml", "valor_creditos": 2})
    assert res.status_code == 201


# ---------- extrato ----------

def _carteira_id(client, token):
    return client.get("/clientes", params={"telefone": TEL_CLIENTE}, headers=auth(token)).json()["carteira"]["id"]


def test_extrato_da_carteira_exige_token(client, token_caixa):
    carteira_id = _carteira_id(client, token_caixa)
    assert client.get(f"/carteira/{carteira_id}").status_code == 401
    assert client.get(f"/carteira/{carteira_id}", headers=auth(token_caixa)).status_code == 200


def test_extrato_do_cliente_nao_aceita_mais_so_o_telefone(client):
    assert client.get("/clientes/me/extrato", params={"telefone": TEL_CLIENTE}).status_code == 401
    assert client.get("/clientes/me", params={"telefone": TEL_CLIENTE}).status_code == 401


# ---------- validação de entrada (XSS armazenado) ----------

@pytest.mark.parametrize("nome", [
    "<script>alert(1)</script>",
    '<img src=x onerror="fetch(1)">',
    'Açaí"><svg onload=alert(1)>',
    "nome `com` crase",
])
def test_nome_de_produto_com_html_recusado(client, token_admin, nome):
    res = client.post("/produtos", headers=auth(token_admin), json={"nome": nome, "valor_creditos": 1})
    assert res.status_code == 422


@pytest.mark.parametrize("nome", ["Açaí 500ml", "Pizza (média)", "Combo 2+1", "Copo 300ml - 10% off"])
def test_nome_de_produto_comum_aceito(client, token_admin, nome):
    res = client.post("/produtos", headers=auth(token_admin), json={"nome": nome, "valor_creditos": 1})
    assert res.status_code == 201


@pytest.mark.parametrize("telefone", ["(83)9999-8888", "83 99999 8888", "839999988880", "83999998888 OR 1=1"])
def test_telefone_fora_do_padrao_recusado(client, token_caixa, telefone):
    res = client.post("/clientes", headers=auth(token_caixa), json={"nome": "Joao", "telefone": telefone})
    assert res.status_code == 422


# ---------- CORS ----------

def _preflight(client, origem):
    return client.options("/produtos", headers={
        "Origin": origem,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    })


def test_cors_libera_o_front(client):
    res = _preflight(client, "http://localhost:5500")
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:5500"


@pytest.mark.parametrize("origem", ["https://site-malicioso.com", "null", "http://localhost:3000"])
def test_cors_bloqueia_outras_origens(client, origem):
    res = _preflight(client, origem)
    assert res.status_code == 400
    assert "access-control-allow-origin" not in res.headers


# ---------- configuração ----------

@pytest.mark.parametrize("variavel,valor", [
    ("JWT_SECRET", ""),
    ("JWT_SECRET", "curto"),
    ("CORS_ORIGINS", "*"),
    ("JWT_EXPIRE_MINUTES", "0"),
    ("JWT_EXPIRE_MINUTES", "oito horas"),
])
def test_configuracao_insegura_impede_a_api_de_subir(monkeypatch, variavel, valor):
    from app import config
    monkeypatch.setenv(variavel, valor)
    with pytest.raises(RuntimeError):
        config._load_settings()
