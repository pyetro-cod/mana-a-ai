"""Etapa cupons, passo 3: usar cupom, bônus de boas-vindas e expiração do saldo."""
from datetime import datetime, timedelta

import pytest

from app import models, regras
from app.database import SessionLocal

from .conftest import TEL_ADMIN, TEL_CAIXA, TEL_CLIENTE, auth, entrar_como_cliente, usuario_id

TEL_NOVO = "83955554444"


def criar_cupons(*codigos, creditos=50, expira_em_dias=7):
    """Cria um lote com os códigos dados (a geração pelo admin vem no passo 4)."""
    db = SessionLocal()
    try:
        expira = regras.agora() + timedelta(days=expira_em_dias)
        lote = models.LoteCupom(estabelecimento_id=models.ESTABELECIMENTO_PADRAO,
                                quantidade=len(codigos), creditos=creditos,
                                criado_por=usuario_id(TEL_CAIXA), expira_em=expira)
        db.add(lote)
        db.flush()
        db.add_all(models.Cupom(lote_id=lote.id, codigo=c, creditos=creditos, expira_em=expira)
                   for c in codigos)
        db.commit()
    finally:
        db.close()


def mexer_no_banco(funcao):
    db = SessionLocal()
    try:
        funcao(db)
        db.commit()
    finally:
        db.close()


def envelhecer_transacoes_de_cupom(telefone, dias):
    """Simula "ontem" sem esperar: empurra os usos de cupom para o passado."""
    def mover(db):
        carteira = db.query(models.Usuario).filter_by(telefone=telefone).one().carteira
        for t in db.query(models.Transacao).filter_by(carteira_id=carteira.id, motivo="cupom"):
            t.criado_em -= timedelta(days=dias)
    mexer_no_banco(mover)


def definir_ultima_compra(telefone, quando):
    def definir(db):
        db.query(models.Usuario).filter_by(telefone=telefone).one().carteira.ultima_compra_em = quando
    mexer_no_banco(definir)


def usar(client, token, codigo):
    return client.post("/clientes/me/cupons", json={"codigo": codigo}, headers=auth(token))


def extrato(client, token):
    res = client.get("/clientes/me/extrato", headers=auth(token))
    assert res.status_code == 200
    return res.json()


@pytest.fixture
def token_novo(client, codigos_enviados):
    """Cliente recém-cadastrado: saldo 0, nunca ganhou bônus."""
    return entrar_como_cliente(client, codigos_enviados, TEL_NOVO, nome="Bia", aceite_termos=True)


# ---------- cupom e bônus ----------

def test_primeiro_cupom_credita_cupom_mais_bonus(client, token_novo):
    criar_cupons("ABC123XYZ")
    res = usar(client, token_novo, "ABC123XYZ")
    assert res.status_code == 200, res.text
    corpo = res.json()
    assert (corpo["creditos"], corpo["bonus"], corpo["novo_saldo"]) == (50, 100, 150)

    dados = extrato(client, token_novo)
    assert dados["saldo"] == 150
    assert sorted(t["motivo"] for t in dados["historico"]) == ["bonus", "cupom"]


def test_bonus_so_vem_uma_vez(client, token_novo):
    criar_cupons("PRIMEIRO1", "SEGUNDO22")
    usar(client, token_novo, "PRIMEIRO1")
    envelhecer_transacoes_de_cupom(TEL_NOVO, 1)  # já é outro dia
    corpo = usar(client, token_novo, "SEGUNDO22").json()
    assert (corpo["bonus"], corpo["novo_saldo"]) == (0, 200)


def test_codigo_aceita_minusculas_e_espacos(client, token_novo):
    criar_cupons("ABC123XYZ")
    assert usar(client, token_novo, "  abc123xyz ").status_code == 200


def test_cupom_e_de_uso_unico_mesmo_entre_clientes(client, codigos_enviados, token_novo):
    criar_cupons("UNICO1234")
    assert usar(client, token_novo, "UNICO1234").status_code == 200
    token_ana = entrar_como_cliente(client, codigos_enviados, TEL_CLIENTE)
    res = usar(client, token_ana, "UNICO1234")
    assert (res.status_code, res.json()["detail"]) == (409, "cupom_ja_usado")
    assert extrato(client, token_ana)["saldo"] == 50  # nada mudou para a Ana


def test_cupom_inexistente(client, token_novo):
    res = usar(client, token_novo, "NAOEXISTE")
    assert (res.status_code, res.json()["detail"]) == (404, "cupom_inexistente")


def test_cupom_vencido(client, token_novo):
    criar_cupons("VELHO1234", expira_em_dias=-1)
    res = usar(client, token_novo, "VELHO1234")
    assert (res.status_code, res.json()["detail"]) == (410, "cupom_expirado")
    assert extrato(client, token_novo)["saldo"] == 0


def test_um_cupom_por_dia(client, token_novo):
    criar_cupons("HOJE00001", "HOJE00002")
    assert usar(client, token_novo, "HOJE00001").status_code == 200
    res = usar(client, token_novo, "HOJE00002")
    assert (res.status_code, res.json()["detail"]) == (429, "limite_diario")

    # The refused coupon stays free: the customer can use it tomorrow.
    envelhecer_transacoes_de_cupom(TEL_NOVO, 1)
    assert usar(client, token_novo, "HOJE00002").status_code == 200


def test_cupom_recusado_nao_muda_nada(client, token_novo):
    criar_cupons("VELHO1234", expira_em_dias=-1)
    usar(client, token_novo, "VELHO1234")
    db = SessionLocal()
    try:
        assert db.query(models.Cupom).filter_by(codigo="VELHO1234").one().usado_em is None
        assert db.query(models.Transacao).count() == 0
    finally:
        db.close()


@pytest.mark.parametrize("codigo", ["<script>", "AB", "x" * 40, "ABC 123"])
def test_codigo_com_formato_invalido(client, token_novo, codigo):
    assert usar(client, token_novo, codigo).status_code == 422


def test_cupom_exige_login_de_cliente(client, token_caixa):
    criar_cupons("ABC123XYZ")
    assert client.post("/clientes/me/cupons", json={"codigo": "ABC123XYZ"}).status_code == 401
    assert usar(client, token_caixa, "ABC123XYZ").status_code == 401


# ---------- expiração do saldo ----------

def test_saldo_mostra_quando_vence(client, token_novo):
    criar_cupons("ABC123XYZ")
    usar(client, token_novo, "ABC123XYZ")
    vence = datetime.fromisoformat(extrato(client, token_novo)["vence_em"])
    faltam = vence - regras.agora()
    assert timedelta(days=29, hours=23) < faltam <= timedelta(days=30)


def test_saldo_expira_depois_de_30_dias_sem_compra(client, codigos_enviados):
    token = entrar_como_cliente(client, codigos_enviados, TEL_CLIENTE)  # Ana, saldo 50
    definir_ultima_compra(TEL_CLIENTE, regras.agora() - timedelta(days=31))

    dados = extrato(client, token)
    assert dados["saldo"] == 0
    assert dados["vence_em"] is None
    expiracao = dados["historico"][0]
    assert (expiracao["motivo"], expiracao["tipo"], expiracao["valor"]) == ("expiracao", "debito", 50)

    # Reading again does not expire twice.
    assert len(extrato(client, token)["historico"]) == 1


def test_saldo_dentro_do_prazo_nao_expira(client, codigos_enviados):
    token = entrar_como_cliente(client, codigos_enviados, TEL_CLIENTE)
    definir_ultima_compra(TEL_CLIENTE, regras.agora() - timedelta(days=29))
    assert extrato(client, token)["saldo"] == 50


def test_compra_renova_o_prazo_do_saldo_inteiro(client, codigos_enviados):
    token = entrar_como_cliente(client, codigos_enviados, TEL_CLIENTE)
    definir_ultima_compra(TEL_CLIENTE, regras.agora() - timedelta(days=29))
    criar_cupons("RENOVA123")
    usar(client, token, "RENOVA123")
    # 29 days later the old 50 would have expired; the purchase pushed the deadline.
    definir_ultima_compra(TEL_CLIENTE, regras.agora() - timedelta(days=29))
    assert extrato(client, token)["saldo"] == 50 + 50 + 100


def test_saldo_vencido_nao_e_ressuscitado_pelo_cupom_novo(client, codigos_enviados):
    token = entrar_como_cliente(client, codigos_enviados, TEL_CLIENTE)
    definir_ultima_compra(TEL_CLIENTE, regras.agora() - timedelta(days=40))
    criar_cupons("VOLTEI123")
    corpo = usar(client, token, "VOLTEI123").json()
    assert corpo["expirado"] == 50
    assert corpo["novo_saldo"] == 50 + 100  # só o cupom + bônus; os 50 antigos venceram


def test_carteira_antiga_sem_data_comeca_a_contar_agora(client, codigos_enviados):
    token = entrar_como_cliente(client, codigos_enviados, TEL_CLIENTE)  # ultima_compra_em = None
    dados = extrato(client, token)
    assert dados["saldo"] == 50
    assert dados["vence_em"] is not None


def test_perfil_tambem_mostra_saldo_ja_expirado(client, codigos_enviados):
    token = entrar_como_cliente(client, codigos_enviados, TEL_CLIENTE)
    definir_ultima_compra(TEL_CLIENTE, regras.agora() - timedelta(days=31))
    assert client.get("/clientes/me", headers=auth(token)).json()["carteira"]["saldo"] == 0


def test_admin_nao_debita_saldo_vencido(client, token_admin):
    definir_ultima_compra(TEL_CLIENTE, regras.agora() - timedelta(days=31))
    carteira_id = client.get("/clientes", params={"telefone": TEL_CLIENTE},
                             headers=auth(token_admin)).json()["carteira"]["id"]
    res = client.post("/transacoes", headers=auth(token_admin),
                      json={"carteira_id": carteira_id, "tipo": "debito", "valor": 50})
    assert res.status_code == 422


def test_lancamento_manual_registra_o_operador(client, token_admin):
    carteira_id = client.get("/clientes", params={"telefone": TEL_CLIENTE},
                             headers=auth(token_admin)).json()["carteira"]["id"]
    client.post("/transacoes", headers=auth(token_admin),
                json={"carteira_id": carteira_id, "tipo": "credito", "valor": 10})
    db = SessionLocal()
    try:
        transacao = db.query(models.Transacao).one()
        assert (transacao.motivo, transacao.operador_id) == ("manual", usuario_id(TEL_ADMIN))
    finally:
        db.close()


# ---------- dia da loja ----------

def test_dia_vira_a_meia_noite_de_joao_pessoa_nao_de_greenwich():
    # 02:30 UTC = 23:30 do dia anterior em João Pessoa.
    momento = datetime(2026, 11, 8, 2, 30)
    assert regras.inicio_do_dia_na_loja(momento) == datetime(2026, 11, 7, 3, 0)
