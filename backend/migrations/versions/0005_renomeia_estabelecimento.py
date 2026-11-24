"""renomeia o estabelecimento para Maná Comedoria

A loja mudou de marca (Manaçaí -> Maná Comedoria). Só o nome exibido muda: o id
'manacai' é chave interna usada por outras tabelas e continua igual.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-24 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

estabelecimentos = sa.table('estabelecimentos', sa.column('id', sa.String), sa.column('nome', sa.String))


def _renomear(nome: str) -> None:
    op.execute(estabelecimentos.update()
               .where(estabelecimentos.c.id == 'manacai')
               .values(nome=nome))


def upgrade() -> None:
    _renomear('Maná Comedoria')


def downgrade() -> None:
    _renomear('Manaçaí')
