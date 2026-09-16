# Maná — Backend (MVP)

API do programa de fidelidade. FastAPI + SQLAlchemy, SQLite por padrão (troque `DATABASE_URL` pra Postgres quando for pra produção).

## Rodando localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python seed.py          # cria produtos + cliente e caixa de teste
uvicorn app.main:app --reload
```

Docs interativas em `http://127.0.0.1:8000/docs`.

## Usuários de teste (criados pelo seed)

| Perfil | Telefone | Senha |
|---|---|---|
| Cliente (Ana Souza) | 83999998888 | — (cliente não loga no MVP) |
| Caixa | 83988887777 | senha1234 |

## Endpoints

- `POST /auth/login` — autentica caixa/admin
- `GET /clientes?telefone=` — busca cliente e saldo
- `POST /transacoes` — lança crédito ou débito (atômico, bloqueia saldo negativo)
- `GET /carteira/{id}` — saldo e histórico

## Variáveis de ambiente

- `DATABASE_URL` — padrão `sqlite:///./mana.db`. Para Postgres: `postgresql://user:senha@host:5432/mana`

## Notas

- O token de login é um **stub** pra facilitar teste local — trocar por JWT assinado antes de produção.
- `POST /transacoes` roda o ajuste de saldo e a inserção do histórico como uma única transação de banco (lock na carteira via `with_for_update`), seguindo a regra de ledger débito/crédito do projeto.
