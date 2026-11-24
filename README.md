# Maná Comedoria — Programa de créditos

Programa de fidelidade com créditos digitais para o **Maná Comedoria** (antes Manaçaí / Maná Açaí), em João Pessoa. O cliente ganha créditos ao escanear o QR do cupom que recebe na compra e troca os créditos por prêmios no balcão. A pergunta que o MVP precisa responder é se o crédito digital traz o cliente de volta.

## Como funciona

1. **Compra:** o cliente recebe um cupom impresso com QR (50 créditos, configurável).
2. **Escaneia:** entra no app só com o telefone (código de 6 dígitos, sem senha) e o crédito cai na hora. O primeiro cupom dá 100 de bônus de boas-vindas.
3. **Junta:** os créditos vencem após 30 dias sem compra, e cada compra renova o prazo.
4. **Troca:** escolhe um prêmio, recebe um código de 6 dígitos (válido 10 min) e o caixa confirma a entrega.

O dono controla as regras, gera as folhas de cupons (A4, 12 por folha) e mantém o catálogo de prêmios na área de administração.

## Estrutura

```
backend/          API FastAPI + SQLAlchemy + Alembic (ver backend/README.md)
frontend/         App do cliente, balcão (index.html), administração (admin.html)
                  e folha de impressão dos cupons (folha-cupons.html)
business-model/   Modelo de negócio (spec.json -> HTML/PDF via build.py)
```

## Arquitetura (C4)

- **Contexto:** Cliente, Operador de caixa e Dono (admin) usam o Sistema de fidelidade; o código de entrada do cliente chega pelo WhatsApp.
- **Containers:** App do cliente, Balcão e Administração (HTML/JS), API de fidelidade (FastAPI), Banco de dados (Postgres em produção, SQLite local).
- **Componentes da API:** Autenticação (JWT + OTP), Carteira e extrato, Regras (cupom, bônus, expiração), Resgates, Administração, Limites de tentativa.

## Modelo de dados

- `Usuario` (cliente, caixa ou admin) → `Carteira` (1:1, saldo e data da última compra) → `Transacao` (ledger de crédito e débito, com o motivo de cada lançamento).
- `LoteCupom` → `Cupom`: cada cupom tem uso único e validade.
- `Premio` → `Resgate`: o código de troca guarda o status e quem confirmou.
- `Configuracao`: as regras do programa, editáveis pelo admin.

## Rodando localmente

Ver [backend/README.md](backend/README.md): `.env`, `alembic upgrade head`, `python seed.py`, `uvicorn` e o front servido na porta 5500.

## Versões

Ver [CHANGELOG.md](CHANGELOG.md).

## Workflow de git

Este repositório segue Git Flow:

- **Branches:** `main` (estável, com tags de versão) ← `release/*` ← `develop` (integração) ← `feature/*`.
- **Features:** uma feature por branch, com merge via PR.
- **Commits:** padrão Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`).
