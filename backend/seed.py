"""Popula o banco com dados de exemplo para testar a API localmente.
Rodar com: python seed.py
"""
from passlib.context import CryptContext

from app.database import SessionLocal, engine, Base
from app import models

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

Base.metadata.create_all(bind=engine)
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

db.commit()
db.close()
print("Seed concluído: produtos, cliente de teste (83999998888) e caixa (83988887777 / senha1234).")
