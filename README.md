# Maná — Sistema de fidelidade

Plataforma de créditos/fidelidade para o estabelecimento Maná (ex-Maná Açaí), em João Pessoa. MVP: caixa lança créditos manualmente, cliente consulta saldo pelo PWA.

## Estrutura

```
backend/    API FastAPI (auth, clientes, transações, carteira) — ver backend/README.md
frontend/   Mockup de UX (PWA cliente + painel do caixa)
```

## Arquitetura (C4)

- **Contexto**: Cliente, Operador de caixa e Administrador interagem com o Sistema de fidelidade.
- **Containers**: PWA cliente, Painel do caixa, API de fidelidade (FastAPI), Banco de dados (Postgres em produção / SQLite local).
- **Componentes da API**: Autenticação, Carteira, Motor de créditos, Produtos.

## Modelo de dados

`Usuario` (perfil: cliente/caixa/admin) → `Carteira` (1:1, saldo) → `Transacao` (ledger de débito/crédito, referencia `Produto` opcionalmente).

## Escopo do MVP

- Caixa busca cliente por telefone e lança crédito/débito manualmente.
- Cliente consulta saldo e histórico pelo PWA.
- Sem QR code, sem catálogo completo, sem rede multiestabelecimento — isso fica pra fases seguintes, depois de validar se o crédito digital realmente traz o cliente de volta.

## Workflow de git

Este repositório segue Git Flow: `main` (estável) ← `develop` (integração) ← `feature/*` (uma feature por branch, merge via PR, commits no padrão Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`).
