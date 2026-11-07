# Maná — Backend (MVP)

API do programa de fidelidade. FastAPI + SQLAlchemy, SQLite por padrão (troque `DATABASE_URL` pra Postgres quando for pra produção).

## Rodando localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # depois preencha JWT_SECRET (comando de geração no próprio arquivo)
python seed.py          # cria produtos + cliente e caixa de teste
uvicorn app.main:app --reload
```

Docs interativas em `http://127.0.0.1:8000/docs`.

O front precisa ser servido por HTTP (não abra o `index.html` com duplo clique: a origem `file://` é bloqueada pelo CORS). Em outro terminal:

```bash
cd frontend
python -m http.server 5500
```

E acesse `http://localhost:5500`. A porta precisa estar em `CORS_ORIGINS` no `.env`.

## Testes

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Rodam num banco SQLite temporário (não tocam no `mana.db`). `tests/test_seguranca.py` cobre o critério da fase 2: tokens forjados, adulterados, expirados ou sem assinatura são recusados, permissões por perfil, extrato protegido, validação contra XSS armazenado, CORS e configuração insegura.

## Usuários de teste (criados pelo seed)

| Perfil | Telefone | Senha |
|---|---|---|
| Cliente (Ana Souza) | 83999998888 | — (cliente não loga no MVP) |
| Caixa | 83988887777 | senha1234 |

## Endpoints

- `POST /auth/login` — autentica caixa/admin
- `GET /clientes?telefone=` — busca cliente e saldo
- `POST /transacoes` — lança crédito ou débito (atômico, bloqueia saldo negativo)
- `GET /carteira/{id}` — saldo e histórico (caixa/admin, exige token)
- `GET /clientes/me/extrato?telefone=` — saldo e histórico do próprio cliente (app do cliente; sem login até a fase 3)

## Variáveis de ambiente

Ver `.env.example`. Principais: `JWT_SECRET` (obrigatória), `JWT_EXPIRE_MINUTES`, `CORS_ORIGINS`.


- `DATABASE_URL` — padrão `sqlite:///./mana.db`. Para Postgres: `postgresql://user:senha@host:5432/mana`

## Notas

- O login de caixa/admin devolve um **JWT** assinado com `JWT_SECRET` (HS256), válido por `JWT_EXPIRE_MINUTES` (padrão 8h). A API não sobe sem `JWT_SECRET` no `.env`.
- `POST /transacoes` roda o ajuste de saldo e a inserção do histórico como uma única transação de banco (lock na carteira via `with_for_update`), seguindo a regra de ledger débito/crédito do projeto.
