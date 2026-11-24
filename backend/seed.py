"""Popula o banco com dados de exemplo para testar a API localmente.
Rodar depois de criar as tabelas:
    alembic upgrade head
    python seed.py
"""
from passlib.context import CryptContext

from app.database import SessionLocal
from app import models

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

db = SessionLocal()

produtos = [
    ("Empada", 1),
    ("Açaí 500ml", 2),
    ("Açaí 1L", 3),
    ("Pizza", 3),
]

for nome, valor in produtos:
    if not db.query(models.Produto).filter_by(nome=nome).first():
        db.add(models.Produto(nome=nome, valor_creditos=valor))

if not db.query(models.Usuario).filter_by(telefone="83999998888").first():
    cliente = models.Usuario(nome="Ana Souza", telefone="83999998888", perfil="cliente")
    db.add(cliente)
    db.flush()
    db.add(models.Carteira(usuario_id=cliente.id, saldo=128))

if not db.query(models.Usuario).filter_by(telefone="83988887777").first():
    caixa = models.Usuario(
        nome="Caixa Loja 1",
        telefone="83988887777",
        perfil="caixa",
        senha_hash=pwd_context.hash("senha1234"),
    )
    db.add(caixa)

# Dev-only owner account: opens admin.html (rules, coupon sheets, prizes).
if not db.query(models.Usuario).filter_by(telefone="83977776666").first():
    db.add(models.Usuario(
        nome="Dono (admin)",
        telefone="83977776666",
        perfil="admin",
        senha_hash=pwd_context.hash("senha1234"),
    ))

# Real items from the Maná Comedoria menu as rewards. Provisional cost rule for testing:
# 20 credits per R$ 1 of menu price (a 50-credit coupon is worth about R$ 2,50),
# rounded to tens. The owner sets the final catalogue in admin.html.
CREDITOS_POR_REAL = 20
premios = [
    ("Café pequeno", 3.00),
    ("Café grande", 6.00),
    ("Tapioca de coco", 7.90),
    ("Suco de polpa 300ml", 8.90),
    ("Pastel de forno", 9.99),
    ("Frozen de morango 300ml", 12.90),
    ("Coxinha tradicional", 13.90),
    ("Cuscuz com ovo", 15.90),
    ("Açaí 300ml (suco simples)", 21.90),
    ("Pizza brotinho tradicional", 29.99),
]
for nome, preco in premios:
    if not db.query(models.Premio).filter_by(nome=nome).first():
        db.add(models.Premio(
            estabelecimento_id=models.ESTABELECIMENTO_PADRAO,
            nome=nome,
            custo_creditos=round(preco * CREDITOS_POR_REAL / 10) * 10,
        ))

db.commit()
db.close()
print("Seed concluído: produtos, prêmios do cardápio, cliente de teste (83999998888), "
      "caixa (83988887777) e admin (83977776666), ambos com a senha senha1234.")
