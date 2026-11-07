"""Fase 3: login do cliente por código de uso único (OTP) e autocadastro."""
from datetime import timedelta

import jwt
import pytest

from app import models, otp
from app.config import settings
from app.database import SessionLocal
from app.envio_codigo import EnvioFalhou

from .conftest import TEL_CAIXA, TEL_CLIENTE, auth, entrar_como_cliente

TEL_NOVO = "83955554444"


def _pedir(client, telefone=TEL_CLIENTE):
    return client.post("/auth/cliente/codigo", json={"telefone": telefone})


def _entrar(client, telefone, codigo, **extras):
    return client.post("/auth/cliente/entrar", json={"telefone": telefone, "codigo": codigo, **extras})


def _codigo_errado(certo):
    return "000000" if certo != "000000" else "111111"


def _envelhecer_codigos(telefone, minutos):
    """Simula a passagem do tempo sem sleep: empurra os códigos para o passado."""
    db = SessionLocal()
    try:
        for c in db.query(models.CodigoAcesso).filter_by(telefone=telefone):
            c.criado_em -= timedelta(minutes=minutos)
            c.expira_em -= timedelta(minutes=minutos)
        db.commit()
    finally:
        db.close()


# ---------- fluxo feliz ----------

def test_cliente_existente_entra_e_ve_o_proprio_extrato(client, codigos_enviados):
    token = entrar_como_cliente(client, codigos_enviados)
    res = client.get("/clientes/me/extrato", headers=auth(token))
    assert res.status_code == 200
    assert res.json()["saldo"] == 50
    assert client.get("/clientes/me", headers=auth(token)).json()["telefone"] == TEL_CLIENTE


def test_token_do_cliente_vale_30_dias(client, codigos_enviados):
    dados = jwt.decode(entrar_como_cliente(client, codigos_enviados), settings.jwt_secret, algorithms=["HS256"])
    assert dados["perfil"] == "cliente"
    assert dados["exp"] - dados["iat"] == settings.jwt_cliente_expire_dias * 86400


def test_autocadastro_de_telefone_novo(client, codigos_enviados):
    assert _pedir(client, TEL_NOVO).status_code == 202
    codigo = codigos_enviados[TEL_NOVO]

    sem_dados = _entrar(client, TEL_NOVO, codigo)
    assert sem_dados.status_code == 409
    assert sem_dados.json()["detail"] == "cadastro_necessario"

    # The same code still works after the app asks for name + consent.
    res = _entrar(client, TEL_NOVO, codigo, nome="Bia", aceite_termos=True)
    assert res.status_code == 200
    assert res.json()["novo_cadastro"] is True

    extrato = client.get("/clientes/me/extrato", headers=auth(res.json()["token"])).json()
    assert extrato == {"saldo": 0, "historico": []}

    db = SessionLocal()
    try:
        usuario = db.query(models.Usuario).filter_by(telefone=TEL_NOVO).one()
        assert usuario.perfil == "cliente"
        consentimento = db.query(models.Consentimento).filter_by(usuario_id=usuario.id).one()
        assert consentimento.versao_termos
    finally:
        db.close()


def test_autocadastro_exige_aceite_dos_termos(client, codigos_enviados):
    _pedir(client, TEL_NOVO)
    res = _entrar(client, TEL_NOVO, codigos_enviados[TEL_NOVO], nome="Bia", aceite_termos=False)
    assert res.status_code == 409


def test_autocadastro_recusa_nome_com_html(client, codigos_enviados):
    _pedir(client, TEL_NOVO)
    res = _entrar(client, TEL_NOVO, codigos_enviados[TEL_NOVO], nome="<script>x</script>", aceite_termos=True)
    assert res.status_code == 422


# ---------- proteção do código ----------

def test_codigo_e_guardado_so_como_hash(client, codigos_enviados):
    _pedir(client)
    db = SessionLocal()
    try:
        registro = db.query(models.CodigoAcesso).filter_by(telefone=TEL_CLIENTE).one()
        assert codigos_enviados[TEL_CLIENTE] not in registro.codigo_hash
        assert len(registro.codigo_hash) == 64
    finally:
        db.close()


def test_codigo_errado_recusado(client, codigos_enviados):
    _pedir(client)
    assert _entrar(client, TEL_CLIENTE, _codigo_errado(codigos_enviados[TEL_CLIENTE])).status_code == 401


def test_codigo_nao_pode_ser_reusado(client, codigos_enviados):
    _pedir(client)
    codigo = codigos_enviados[TEL_CLIENTE]
    assert _entrar(client, TEL_CLIENTE, codigo).status_code == 200
    assert _entrar(client, TEL_CLIENTE, codigo).status_code == 401


def test_codigo_de_outro_telefone_nao_serve(client, codigos_enviados):
    _pedir(client, TEL_NOVO)
    _pedir(client, TEL_CLIENTE)
    if codigos_enviados[TEL_NOVO] == codigos_enviados[TEL_CLIENTE]:
        pytest.skip("os dois códigos sorteados coincidiram (1 chance em 1 milhão)")
    assert _entrar(client, TEL_CLIENTE, codigos_enviados[TEL_NOVO]).status_code == 401


def test_codigo_expira(client, codigos_enviados):
    _pedir(client)
    _envelhecer_codigos(TEL_CLIENTE, settings.otp_expire_minutes + 1)
    assert _entrar(client, TEL_CLIENTE, codigos_enviados[TEL_CLIENTE]).status_code == 401


def test_codigo_bloqueia_apos_5_tentativas_erradas(client, codigos_enviados):
    _pedir(client)
    certo = codigos_enviados[TEL_CLIENTE]
    for _ in range(otp.MAX_TENTATIVAS):
        assert _entrar(client, TEL_CLIENTE, _codigo_errado(certo)).status_code == 401
    # Even the right code no longer works: guessing all 10^6 codes is off the table.
    assert _entrar(client, TEL_CLIENTE, certo).status_code == 401


def test_novo_codigo_invalida_o_anterior(client, codigos_enviados):
    _pedir(client)
    antigo = codigos_enviados[TEL_CLIENTE]
    _envelhecer_codigos(TEL_CLIENTE, 2)  # past the 1-minute resend interval, still within validity
    _pedir(client)
    novo = codigos_enviados[TEL_CLIENTE]
    if antigo != novo:
        assert _entrar(client, TEL_CLIENTE, antigo).status_code == 401
    assert _entrar(client, TEL_CLIENTE, novo).status_code == 200


# ---------- limites de envio ----------

def test_um_codigo_por_minuto(client, codigos_enviados):
    assert _pedir(client).status_code == 202
    res = _pedir(client)
    assert res.status_code == 429
    assert int(res.headers["retry-after"]) > 0


def test_no_maximo_5_codigos_por_hora(client, codigos_enviados):
    for _ in range(otp.MAX_CODIGOS_POR_HORA):
        assert _pedir(client).status_code == 202
        _envelhecer_codigos(TEL_CLIENTE, 2)
    assert _pedir(client).status_code == 429


def test_falha_no_envio_nao_conta_no_limite(client, monkeypatch):
    def falha(telefone, codigo):
        raise EnvioFalhou("fora do ar")
    monkeypatch.setattr(otp, "enviar_codigo", falha)
    assert _pedir(client).status_code == 503
    monkeypatch.setattr(otp, "enviar_codigo", lambda telefone, codigo: None)
    assert _pedir(client).status_code == 202


def test_resposta_igual_para_telefone_cadastrado_ou_nao(client, codigos_enviados):
    cadastrado = _pedir(client, TEL_CLIENTE)
    novo = _pedir(client, TEL_NOVO)
    assert (cadastrado.status_code, cadastrado.json()) == (novo.status_code, novo.json())


@pytest.mark.parametrize("telefone", ["8399999", "(83)99999-8888", "abc"])
def test_telefone_invalido_nem_gera_codigo(client, codigos_enviados, telefone):
    assert _pedir(client, telefone).status_code == 422
    assert codigos_enviados == {}


# ---------- separação entre perfis ----------

def test_telefone_do_caixa_nao_entra_no_app_do_cliente(client, codigos_enviados):
    _pedir(client, TEL_CAIXA)
    assert _entrar(client, TEL_CAIXA, codigos_enviados[TEL_CAIXA]).status_code == 403


def test_token_de_cliente_nao_acessa_o_painel(client, codigos_enviados):
    token = entrar_como_cliente(client, codigos_enviados)
    assert client.get("/produtos", headers=auth(token)).status_code == 401
    assert client.get("/clientes", params={"telefone": TEL_CLIENTE}, headers=auth(token)).status_code == 401


def test_token_de_caixa_nao_acessa_o_app_do_cliente(client, token_caixa):
    assert client.get("/clientes/me/extrato", headers=auth(token_caixa)).status_code == 401


# ---------- configuração ----------

@pytest.mark.parametrize("ambiente", [
    {"APP_ENV": "prod", "OTP_PROVIDER": "console"},
    {"OTP_PROVIDER": "whatsapp"},
    {"OTP_PROVIDER": "sms-qualquer"},
    {"APP_ENV": "producao"},
])
def test_configuracao_de_envio_insegura_ou_incompleta_impede_a_api_de_subir(monkeypatch, ambiente):
    from app import config
    for variavel, valor in ambiente.items():
        monkeypatch.setenv(variavel, valor)
    with pytest.raises(RuntimeError):
        config._load_settings()
