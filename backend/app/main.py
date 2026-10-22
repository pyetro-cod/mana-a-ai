from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import engine
from .routers import auth, clientes, transacoes, carteira, produtos

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Maná — API de fidelidade", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restringir em produção
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(clientes.router)
app.include_router(transacoes.router)
app.include_router(carteira.router)
app.include_router(produtos.router)


@app.get("/health")
def health():
    return {"status": "ok"}