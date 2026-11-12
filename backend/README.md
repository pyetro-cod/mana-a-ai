# Maná — Backend (MVP)

API do programa de fidelidade. FastAPI + SQLAlchemy, SQLite por padrão (troque `DATABASE_URL` pra Postgres quando for pra produção).

## Rodando localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # depois preencha JWT_SECRET (comando de geração no próprio arquivo)
alembic upgrade head    # cria/atualiza as tabelas (migrações)
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

## Banco de dados e migrações

As tabelas são criadas e alteradas pelo **Alembic** (pasta `migrations/`), nunca pelo código da API.

```bash
alembic upgrade head                                    # aplica as migrações pendentes
alembic revision --autogenerate --rev-id 0002 -m "..."  # depois de mudar um modelo
alembic current                                         # versão em que o banco está
```

Banco criado antes do Alembic (com `create_all`): marque a versão inicial uma vez com `alembic stamp 0001` e depois use `alembic upgrade head`. `tests/test_migracoes.py` falha se um modelo mudar sem migração correspondente.

## Testes

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Rodam num banco SQLite temporário (não tocam no `mana.db`). `tests/test_login_cliente.py` cobre a fase 3 (login por código, autocadastro, limites e expiração). `tests/test_seguranca.py` cobre o critério da fase 2: tokens forjados, adulterados, expirados ou sem assinatura são recusados, permissões por perfil, extrato protegido, validação contra XSS armazenado, CORS e configuração insegura.

## Usuários de teste (criados pelo seed)

| Perfil | Telefone | Senha |
|---|---|---|
| Cliente (Ana Souza) | 83999998888 | — (entra por código no app) |
| Caixa | 83988887777 | senha1234 |
| Admin (dono) | 83977776666 | senha1234 — abre `admin.html` |

Senhas só para desenvolvimento: troque antes de qualquer ambiente público.

## Endpoints

- `POST /auth/login` — autentica caixa/admin
- `GET /clientes?telefone=` — busca cliente e saldo
- `POST /transacoes` — lança crédito ou débito (atômico, bloqueia saldo negativo)
- `GET /carteira/{id}` — saldo e histórico (caixa/admin, exige token)
- `POST /auth/cliente/codigo` — envia código de 6 dígitos ao telefone do cliente (10 min, 1/min e 5/h por telefone)
- `POST /auth/cliente/entrar` — confere o código; telefone novo exige `nome` + `aceite_termos` (autocadastro); devolve JWT de cliente (30 dias)
- `GET /clientes/me` e `GET /clientes/me/extrato` — dados, saldo, `vence_em` e histórico do cliente logado (token de cliente)
- `POST /clientes/me/cupons` — usa um cupom (QR): credita, dá o bônus no 1º e renova o prazo do saldo. Recusas: 404 inexistente, 409 já usado, 410 vencido/cancelado, 429 limite do dia

- `GET /clientes/me/premios` — prêmios ativos
- `POST /clientes/me/resgates` — reserva os créditos e devolve o código de 6 dígitos (vale `validade_resgate_minutos`); pedir outro substitui o anterior. `GET /clientes/me/resgates/pendente` reabre o código; `POST /clientes/me/resgates/cancelar` devolve os créditos
- `GET /resgates/{codigo}` e `POST /resgates/{codigo}/confirmar` — caixa/admin conferem e confirmam a entrega. Código vencido: 410 e os créditos voltam ao cliente

### Área do admin (`/admin/*`, só perfil admin)

- `GET`/`PUT /admin/configuracao` — regras do programa (créditos por cupom, bônus, validades, expiração do saldo, cupons por dia)
- `GET`/`POST /admin/lotes` — lista e gera lotes de cupons (1 a 200); `GET /admin/lotes/{id}` devolve os QRs para a folha de impressão; `POST /admin/lotes/{id}/cancelar` invalida uma folha perdida
- `GET`/`POST /admin/premios`, `PUT /admin/premios/{id}` — catálogo de prêmios (desativar em vez de excluir)

O QR aponta para `APP_PUBLIC_URL/?cupom=CODIGO`.

### Código de acesso em desenvolvimento

Com `OTP_PROVIDER=console` (padrão em dev), o código aparece no terminal onde a API está rodando:

```
[DEV] código de acesso para 83999998888: 123456 (válido por 10 min)
```

Em produção (`APP_ENV=prod`) isso é bloqueado: é preciso `OTP_PROVIDER=whatsapp` com uma conta comercial verificada na Meta e um template de autenticação aprovado.

## Variáveis de ambiente

Ver `.env.example`. Principais: `JWT_SECRET` (obrigatória), `JWT_EXPIRE_MINUTES`, `CORS_ORIGINS`, `APP_PUBLIC_URL` (endereço do app gravado no QR dos cupons; `https://` fora de localhost).


- `DATABASE_URL` — padrão `sqlite:///./mana.db`. Para Postgres: `postgresql://user:senha@host:5432/mana`

## Notas

- O login de caixa/admin devolve um **JWT** assinado com `JWT_SECRET` (HS256), válido por `JWT_EXPIRE_MINUTES` (padrão 8h). A API não sobe sem `JWT_SECRET` no `.env`.
- `POST /transacoes` roda o ajuste de saldo e a inserção do histórico como uma única transação de banco (lock na carteira via `with_for_update`), seguindo a regra de ledger débito/crédito do projeto.
