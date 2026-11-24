# Changelog

Versões do programa de créditos do Manaçaí. Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões no padrão [SemVer](https://semver.org/lang/pt-BR/).

## [0.3.0] — 2026-11-24

O crédito passa a ser automático: o cliente se cadastra sozinho, escaneia o QR do cupom e troca créditos por prêmios. O caixa só confirma a entrega.

### Adicionado
- **Login do cliente por código:**
  - código de 6 dígitos enviado ao telefone, guardado só como HMAC;
  - vale 10 minutos, com no máximo 5 tentativas e limite de 1 por minuto e 5 por hora;
  - autocadastro com nome e aceite dos termos (LGPD), sessão de 30 dias.
- **Cupons com QR:**
  - o crédito cai na hora, e o primeiro cupom dá bônus de boas-vindas;
  - o cupom vale uma vez, tem validade e limite de 1 por dia no fuso de João Pessoa;
  - o QR abre o app e credita, mesmo antes do login.
- **Expiração do saldo:** vence após 30 dias sem compra, e cada compra renova o prazo. O app mostra a data, e o vencimento aparece no extrato.
- **Troca por prêmio:**
  - o cliente gera um código de 6 dígitos e os créditos ficam reservados na hora;
  - o caixa confere e confirma a entrega;
  - código vencido ou cancelado devolve os créditos.
- **Área do dono** (`admin.html`): regras do programa, geração de lotes de cupons com folha A4 para imprimir (12 por folha), cancelamento de lote e catálogo de prêmios.
- **Extrato** com o motivo de cada lançamento (cupom, bônus, troca, estorno, expiração, ajuste).
- **Atalho de desenvolvimento** `OTP_MOSTRAR_NO_APP`: mostra o código de entrada na tela. A API recusa subir com ele fora de dev.

### Alterado
- **Balcão:** passa a conferir e confirmar trocas. O lançamento manual de crédito fica só com o admin e registra quem lançou.
- **Produtos:** os botões de pontos por produto saíram das telas (a API foi mantida).
- **Banco:** migrações com Alembic (`0001`–`0004`); pronto para Postgres (psycopg 3) e configuração por variáveis de ambiente.

### Segurança
- Token JWT assinado (HS256) com expiração no lugar do token simples; o perfil é conferido no banco a cada requisição.
- CORS restrito às origens configuradas.
- XSS eliminado no front; nome e telefone são validados na API.
- Limites de tentativas erradas:
  - login do painel: 5 em 15 minutos por telefone;
  - código de cupom inventado: 10 por hora por cliente.
- Confirmação de troca, estorno e uso de cupom por atualização condicional: sem crédito em dobro em requisições simultâneas.

### Corrigido
- Datas da API exibidas 3 horas adiantadas no app.
- Telefone e senha de teste pré-preenchidos na tela de login do balcão.

### Testes
- 156 testes automáticos (pytest), incluindo um teste que falha se um modelo mudar sem migração. A suíte roda em menos de 1 minuto.

## [0.2.0] — 2026-10-22

### Adicionado
- **Painel do caixa** integrado à API: busca de cliente, cadastro de cliente novo, lançamento de crédito por produto e resgate.
- **Catálogo de produtos** gerenciado pelo admin.
- **Identidade visual do Manaçaí** (paleta e logo) no app e no modelo de negócio.
- **Modelo de negócio** para acompanhamento do projeto (`business-model/`).

## [0.1.0] — 2026-09-16

### Adicionado
- Primeira versão: API FastAPI de fidelidade (clientes, carteira, transações) e mockup do app do cliente e do painel do caixa.

[0.3.0]: https://github.com/pyetro-cod/mana-a-ai/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/pyetro-cod/mana-a-ai/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/pyetro-cod/mana-a-ai/releases/tag/v0.1.0
