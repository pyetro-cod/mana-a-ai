"""As migrações do Alembic precisam criar exatamente o esquema dos modelos.

Se alguém alterar um modelo e esquecer de gerar a migração, este teste falha."""
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.database import Base, engine

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def test_migracoes_criam_o_esquema_dos_modelos():
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent / "migrations"))
    command.upgrade(cfg, "head")
    command.check(cfg)  # raises if the models differ from what the migrations built


def test_migracoes_cadastram_a_loja_com_o_nome_atual():
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent / "migrations"))
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        nome = conn.exec_driver_sql("SELECT nome FROM estabelecimentos WHERE id = 'manacai'").scalar_one()
    assert nome == "Maná Comedoria"

    command.downgrade(cfg, "0004")  # the rename is reversible
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT nome FROM estabelecimentos").scalar_one() == "Manaçaí"
    command.upgrade(cfg, "head")
