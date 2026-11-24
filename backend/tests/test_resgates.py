"""Etapa cupons, passo 5: trocar créditos por prêmio (código no app, confirmação no caixa)."""
from datetime import timedelta

import pytest

from app import models
from app.database import SessionLocal

from .conftest import TEL_CLIENTE, auth, entrar_como_cliente

# Ana starts with 50 credits (conftest).


def criar_premio(nome="Açaí 300ml", custo=30, ativo=True):
    db = SessionLocal()
    try:
        premio = models.Premio(estabelecimento_id=models.ESTABELECIMENTO_PADRAO, nome=nome,
                               custo_creditos=custo, ativo=ativo)
        db.add(premio)
        db.commit()
        return premio.id
    finally:
        db.close()


def envelhecer_resgates(minutos):
    db = SessionLocal()
    try:
        for r in db.query(models.Resgate):
            r.criado_em -= timedelta(minutes=minutos)
            r.expira_em -= timedelta(minutes=minutos)
        db.commit()
    finally:
        db.close()


@pytest.fixture
def token_ana(client, codigos_enviados):
    return entrar_como_cliente(client, codigos_enviados, TEL_CLIENTE)


def pedir(client, token, premio_id):
    return client.post("/clientes/me/resgates", json={"premio_id": premio_id}, headers=auth(token))


def saldo(client, token):
    return client.get("/clientes/me/extrato", headers=auth(token)).json()["saldo"]


# ---------- catálogo ----------

def test_cliente_ve_so_premios_ativos_do_mais_barato_ao_mais_caro(client, token_ana):
    criar_premio("Pizza", 300)
    criar_premio("Empada", 20)
    criar_premio("Antigo", 10, ativo=False)
    nomes = [p["nome"] for p in client.get("/clientes/me/premios", headers=auth(token_ana)).json()]
    assert nomes == ["Empada", "Pizza"]


# ---------- fluxo feliz ----------

def test_pedir_reserva_os_creditos_e_caixa_confirma(client, token_ana, token_caixa):
    premio_id = criar_premio(custo=30)
    res = pedir(client, token_ana, premio_id)
    assert res.status_code == 201, res.text
    corpo = res.json()
    assert len(corpo["codigo"]) == 6 and corpo["codigo"].isdigit()
    assert (corpo["premio"], corpo["custo_creditos"], corpo["novo_saldo"]) == ("Açaí 300ml", 30, 20)
    assert saldo(client, token_ana) == 20  # reservado: não dá para gastar duas vezes

    vista = client.get(f"/resgates/{corpo['codigo']}", headers=auth(token_caixa)).json()
    assert (vista["cliente"], vista["premio"], vista["status"]) == ("Ana", "Açaí 300ml", "pendente")

    confirmado = client.post(f"/resgates/{corpo['codigo']}/confirmar", headers=auth(token_caixa))
    assert confirmado.json()["status"] == "confirmado"
    assert saldo(client, token_ana) == 20

    # The same code cannot hand out a second prize.
    assert client.post(f"/resgates/{corpo['codigo']}/confirmar", headers=auth(token_caixa)).status_code == 404


def test_extrato_mostra_o_debito_do_resgate(client, token_ana):
    pedir(client, token_ana, criar_premio(custo=30))
    historico = client.get("/clientes/me/extrato", headers=auth(token_ana)).json()["historico"]
    assert (historico[0]["motivo"], historico[0]["tipo"], historico[0]["valor"]) == ("resgate", "debito", 30)


def test_app_reabre_o_codigo_em_aberto(client, token_ana):
    codigo = pedir(client, token_ana, criar_premio()).json()["codigo"]
    aberto = client.get("/clientes/me/resgates/pendente", headers=auth(token_ana)).json()
    assert aberto["codigo"] == codigo


def test_sem_resgate_em_aberto_devolve_null(client, token_ana):
    assert client.get("/clientes/me/resgates/pendente", headers=auth(token_ana)).json() is None


def test_registra_qual_caixa_confirmou(client, token_ana, token_caixa):
    codigo = pedir(client, token_ana, criar_premio()).json()["codigo"]
    client.post(f"/resgates/{codigo}/confirmar", headers=auth(token_caixa))
    db = SessionLocal()
    try:
        resgate = db.query(models.Resgate).one()
        assert db.get(models.Usuario, resgate.confirmado_por).perfil == "caixa"
        assert resgate.confirmado_em is not None
    finally:
        db.close()


# ---------- recusas ----------

def test_saldo_insuficiente(client, token_ana):
    res = pedir(client, token_ana, criar_premio(custo=51))
    assert (res.status_code, res.json()["detail"]) == (422, "saldo_insuficiente")
    assert saldo(client, token_ana) == 50


@pytest.mark.parametrize("ativo", [False, None])
def test_premio_desativado_ou_inexistente(client, token_ana, ativo):
    premio_id = criar_premio(ativo=False) if ativo is False else "nao-existe"
    res = pedir(client, token_ana, premio_id)
    assert (res.status_code, res.json()["detail"]) == (404, "premio_inexistente")


def test_codigo_desconhecido_no_caixa(client, token_caixa):
    assert client.get("/resgates/123456", headers=auth(token_caixa)).status_code == 404


@pytest.mark.parametrize("codigo", ["12345", "abcdef", "1234567"])
def test_codigo_com_formato_invalido_no_caixa(client, token_caixa, codigo):
    assert client.get(f"/resgates/{codigo}", headers=auth(token_caixa)).status_code == 422


# ---------- prazo, cancelamento e troca ----------

def test_codigo_vencido_devolve_os_creditos(client, token_ana, token_caixa):
    codigo = pedir(client, token_ana, criar_premio(custo=30)).json()["codigo"]
    envelhecer_resgates(11)

    res = client.post(f"/resgates/{codigo}/confirmar", headers=auth(token_caixa))
    assert (res.status_code, res.json()["detail"]) == (410, "resgate_expirado")
    assert saldo(client, token_ana) == 50
    motivos = [t["motivo"] for t in client.get("/clientes/me/extrato", headers=auth(token_ana)).json()["historico"]]
    assert sorted(motivos) == ["estorno_resgate", "resgate"]


def test_codigo_vencido_volta_quando_o_cliente_abre_o_app(client, token_ana):
    pedir(client, token_ana, criar_premio(custo=30))
    envelhecer_resgates(11)
    assert saldo(client, token_ana) == 50  # sem precisar do caixa
    assert saldo(client, token_ana) == 50  # e não estorna duas vezes


def test_cliente_cancela_e_recebe_de_volta(client, token_ana, token_caixa):
    codigo = pedir(client, token_ana, criar_premio(custo=30)).json()["codigo"]
    res = client.post("/clientes/me/resgates/cancelar", headers=auth(token_ana)).json()
    assert (res["devolvido"], res["novo_saldo"]) == (30, 50)
    assert client.post(f"/resgates/{codigo}/confirmar", headers=auth(token_caixa)).status_code == 404
    # Cancelling twice gives nothing back the second time.
    assert client.post("/clientes/me/resgates/cancelar", headers=auth(token_ana)).json()["devolvido"] == 0


def test_trocar_de_premio_substitui_o_codigo_anterior(client, token_ana, token_caixa):
    primeiro = pedir(client, token_ana, criar_premio("Empada", 40)).json()["codigo"]
    # 50 - 40 = 10 left, but the first reservation returns before the new one is checked.
    segundo = pedir(client, token_ana, criar_premio("Açaí", 45))
    assert segundo.status_code == 201
    assert segundo.json()["novo_saldo"] == 5
    if primeiro != segundo.json()["codigo"]:
        assert client.get(f"/resgates/{primeiro}", headers=auth(token_caixa)).status_code == 404


def test_preco_fica_congelado_no_pedido(client, token_ana, token_admin, token_caixa):
    premio_id = criar_premio(custo=30)
    codigo = pedir(client, token_ana, premio_id).json()["codigo"]
    client.put(f"/admin/premios/{premio_id}", json={"custo_creditos": 45}, headers=auth(token_admin))
    assert client.get(f"/resgates/{codigo}", headers=auth(token_caixa)).json()["custo_creditos"] == 30


# ---------- quem pode o quê ----------

def test_cliente_nao_confirma_o_proprio_resgate(client, token_ana):
    codigo = pedir(client, token_ana, criar_premio()).json()["codigo"]
    assert client.post(f"/resgates/{codigo}/confirmar", headers=auth(token_ana)).status_code == 401


def test_caixa_nao_pede_resgate_no_lugar_do_cliente(client, token_caixa):
    assert pedir(client, token_caixa, criar_premio()).status_code == 401


def test_sem_login_nada_feito(client):
    assert client.get("/clientes/me/premios").status_code == 401
    assert client.get("/resgates/123456").status_code == 401


def test_estorno_atrasado_nao_devolve_creditos_de_premio_ja_entregue(client, token_ana, token_caixa):
    """Corrida: o app carregou o resgate como 'pendente', o caixa confirmou, e só então o
    cancelamento chega. A atualização condicional impede prêmio + créditos de volta."""
    from app import regras
    codigo = pedir(client, token_ana, criar_premio(custo=30)).json()["codigo"]
    db = SessionLocal()
    try:
        resgate_velho = db.query(models.Resgate).one()  # lido enquanto ainda estava pendente
        carteira = db.get(models.Carteira, resgate_velho.carteira_id)
        client.post(f"/resgates/{codigo}/confirmar", headers=auth(token_caixa))  # outra sessão

        devolveu = regras.estornar_resgate(db, carteira, resgate_velho, "cancelado", regras.agora())
        db.commit()
        assert devolveu is False
    finally:
        db.close()
    assert saldo(client, token_ana) == 20
