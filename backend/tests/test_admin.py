"""Etapa cupons, passo 4: área do admin (regras, lotes de cupons com QR, prêmios)."""
import pytest

from app import models, regras
from app.config import settings
from app.database import SessionLocal

from .conftest import TEL_CLIENTE, auth, entrar_como_cliente

TEL_NOVO = "83955554444"


def gerar(client, token_admin, quantidade=3):
    res = client.post("/admin/lotes", json={"quantidade": quantidade}, headers=auth(token_admin))
    assert res.status_code == 201, res.text
    return res.json()


# ---------- quem pode entrar ----------

ROTAS_ADMIN = [
    ("get", "/admin/configuracao", None),
    ("put", "/admin/configuracao", {"bonus_boas_vindas": 0}),
    ("get", "/admin/lotes", None),
    ("post", "/admin/lotes", {"quantidade": 1}),
    ("get", "/admin/premios", None),
    ("post", "/admin/premios", {"nome": "Açaí 300ml", "custo_creditos": 200}),
]


@pytest.mark.parametrize("metodo,rota,corpo", ROTAS_ADMIN)
def test_caixa_nao_entra_na_area_do_admin(client, token_caixa, metodo, rota, corpo):
    res = getattr(client, metodo)(rota, headers=auth(token_caixa), **({"json": corpo} if corpo else {}))
    assert res.status_code == 403


@pytest.mark.parametrize("metodo,rota,corpo", ROTAS_ADMIN)
def test_sem_token_nao_entra_na_area_do_admin(client, metodo, rota, corpo):
    res = getattr(client, metodo)(rota, **({"json": corpo} if corpo else {}))
    assert res.status_code == 401


def test_cliente_nao_entra_na_area_do_admin(client, codigos_enviados):
    token = entrar_como_cliente(client, codigos_enviados, TEL_CLIENTE)
    assert client.get("/admin/lotes", headers=auth(token)).status_code == 401


# ---------- regras do programa ----------

def test_admin_muda_as_regras_e_elas_valem_na_hora(client, token_admin, codigos_enviados):
    res = client.put("/admin/configuracao", headers=auth(token_admin),
                     json={"creditos_por_cupom": 80, "bonus_boas_vindas": 20})
    assert res.status_code == 200
    assert (res.json()["creditos_por_cupom"], res.json()["dias_expiracao_saldo"]) == (80, 30)

    codigo = gerar(client, token_admin, 1)["cupons"][0]["codigo"]
    token = entrar_como_cliente(client, codigos_enviados, TEL_NOVO, nome="Bia", aceite_termos=True)
    corpo = client.post("/clientes/me/cupons", json={"codigo": codigo}, headers=auth(token)).json()
    assert (corpo["creditos"], corpo["bonus"]) == (80, 20)


@pytest.mark.parametrize("campo,valor", [
    ("creditos_por_cupom", 0), ("creditos_por_cupom", 5000), ("dias_expiracao_saldo", 0),
    ("bonus_boas_vindas", -1), ("max_cupons_por_dia", 50),
])
def test_regra_fora_dos_limites_e_recusada(client, token_admin, campo, valor):
    res = client.put("/admin/configuracao", json={campo: valor}, headers=auth(token_admin))
    assert res.status_code == 422


def test_lote_impresso_mantem_o_valor_mesmo_se_a_regra_mudar(client, token_admin, codigos_enviados):
    codigo = gerar(client, token_admin, 1)["cupons"][0]["codigo"]  # 50 créditos
    client.put("/admin/configuracao", json={"creditos_por_cupom": 10}, headers=auth(token_admin))
    token = entrar_como_cliente(client, codigos_enviados, TEL_NOVO, nome="Bia", aceite_termos=True)
    corpo = client.post("/clientes/me/cupons", json={"codigo": codigo}, headers=auth(token)).json()
    assert corpo["creditos"] == 50


# ---------- lotes de cupons ----------

def test_gerar_lote_devolve_codigos_unicos_com_qr(client, token_admin):
    lote = gerar(client, token_admin, 20)
    codigos = [c["codigo"] for c in lote["cupons"]]
    assert len(codigos) == len(set(codigos)) == 20
    for cupom in lote["cupons"]:
        assert cupom["qr"].startswith("data:image/svg+xml")
        sem_hifen = cupom["codigo"].replace("-", "")
        assert cupom["url"] == f"{settings.app_public_url}/?cupom={sem_hifen}"
        assert len(sem_hifen) == regras.TAMANHO_CUPOM
        assert set(sem_hifen) <= set(regras.ALFABETO_CUPOM)  # sem 0/O, 1/I/L


def test_codigo_impresso_com_hifen_funciona(client, token_admin, codigos_enviados):
    codigo = gerar(client, token_admin, 1)["cupons"][0]["codigo"]
    assert "-" in codigo
    token = entrar_como_cliente(client, codigos_enviados, TEL_NOVO, nome="Bia", aceite_termos=True)
    res = client.post("/clientes/me/cupons", json={"codigo": codigo.lower()}, headers=auth(token))
    assert res.status_code == 200


@pytest.mark.parametrize("quantidade", [0, 201])
def test_quantidade_do_lote_tem_limite(client, token_admin, quantidade):
    assert client.post("/admin/lotes", json={"quantidade": quantidade},
                       headers=auth(token_admin)).status_code == 422


def test_lista_de_lotes_mostra_quantos_foram_usados(client, token_admin, codigos_enviados):
    lote = gerar(client, token_admin, 3)
    token = entrar_como_cliente(client, codigos_enviados, TEL_NOVO, nome="Bia", aceite_termos=True)
    client.post("/clientes/me/cupons", json={"codigo": lote["cupons"][0]["codigo"]}, headers=auth(token))

    resumo = client.get("/admin/lotes", headers=auth(token_admin)).json()[0]
    assert (resumo["id"], resumo["quantidade"], resumo["usados"]) == (lote["id"], 3, 1)
    detalhe = client.get(f"/admin/lotes/{lote['id']}", headers=auth(token_admin)).json()
    assert sum(c["usado"] for c in detalhe["cupons"]) == 1


def test_lote_cancelado_nao_vale_mais(client, token_admin, codigos_enviados):
    lote = gerar(client, token_admin, 2)
    res = client.post(f"/admin/lotes/{lote['id']}/cancelar", headers=auth(token_admin))
    assert res.json()["cancelado"] is True

    token = entrar_como_cliente(client, codigos_enviados, TEL_NOVO, nome="Bia", aceite_termos=True)
    res = client.post("/clientes/me/cupons", json={"codigo": lote["cupons"][0]["codigo"]}, headers=auth(token))
    assert (res.status_code, res.json()["detail"]) == (410, "cupom_cancelado")


def test_lote_inexistente(client, token_admin):
    assert client.get("/admin/lotes/nao-existe", headers=auth(token_admin)).status_code == 404


def test_lote_guarda_quem_gerou(client, token_admin):
    lote = gerar(client, token_admin, 1)
    db = SessionLocal()
    try:
        criador = db.get(models.Usuario, db.get(models.LoteCupom, lote["id"]).criado_por)
        assert criador.perfil == "admin"
    finally:
        db.close()


# ---------- prêmios ----------

def test_cadastrar_editar_e_desativar_premio(client, token_admin):
    criado = client.post("/admin/premios", json={"nome": "Açaí 300ml", "custo_creditos": 200},
                         headers=auth(token_admin))
    assert criado.status_code == 201
    premio_id = criado.json()["id"]
    assert criado.json()["ativo"] is True

    res = client.put(f"/admin/premios/{premio_id}", json={"custo_creditos": 250, "ativo": False},
                     headers=auth(token_admin))
    assert (res.json()["custo_creditos"], res.json()["ativo"], res.json()["nome"]) == (250, False, "Açaí 300ml")

    lista = client.get("/admin/premios", headers=auth(token_admin)).json()
    assert [p["id"] for p in lista] == [premio_id]  # desativado continua aparecendo para o admin


def test_premio_com_html_no_nome_e_recusado(client, token_admin):
    res = client.post("/admin/premios", json={"nome": "<img src=x onerror=alert(1)>", "custo_creditos": 10},
                      headers=auth(token_admin))
    assert res.status_code == 422


def test_premio_inexistente(client, token_admin):
    assert client.put("/admin/premios/nao-existe", json={"ativo": False},
                      headers=auth(token_admin)).status_code == 404
