from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import admin, auth, clientes, transacoes, carteira, produtos, resgates

# Schema is managed by Alembic migrations: run `alembic upgrade head` before starting the API.

app = FastAPI(title="Manaçaí — API de fidelidade", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type"],
    # Token travels in the Authorization header, not in cookies.
    allow_credentials=False,
    max_age=3600,
)

app.include_router(auth.router)
app.include_router(clientes.router)
app.include_router(transacoes.router)
app.include_router(carteira.router)
app.include_router(produtos.router)
app.include_router(admin.router)
app.include_router(resgates.router)


@app.get("/health")
def health():
    return {"status": "ok"}