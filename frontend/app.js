// Base da API local. Trocar pela URL de produção quando o backend for hospedado.
const API_BASE = 'http://127.0.0.1:8000';

function show(id, btn){
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById('view-' + id).classList.add('active');
  document.querySelectorAll('.switcher button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

function formatData(iso){
  return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
}

/* ================= Caixa: autenticação ================= */
let caixaToken = localStorage.getItem('manaCaixaToken') || null;
let caixaPerfil = localStorage.getItem('manaCaixaPerfil') || null;
let caixaCarteiraId = null;

function atualizarTelaCaixa(){
  const logado = !!caixaToken;
  document.getElementById('caixaLoginBox').style.display = logado ? 'none' : 'grid';
  document.getElementById('caixaPainel').style.display = logado ? 'grid' : 'none';
  document.getElementById('adminProdutos').style.display = (logado && caixaPerfil === 'admin') ? 'block' : 'none';
  if(logado) carregarProdutos();
}

async function loginCaixa(){
  const telefone = document.getElementById('caixaLoginTelefone').value.trim();
  const senha = document.getElementById('caixaLoginSenha').value;
  const status = document.getElementById('caixaLoginStatus');
  status.style.color = 'var(--cream-dim)';
  status.textContent = 'Entrando...';

  try{
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ telefone, senha })
    });
    const data = await res.json();
    if(!res.ok){
      status.style.color = 'var(--yellow)';
      status.textContent = data.detail || 'Não foi possível entrar.';
      return;
    }
    caixaToken = data.token;
    caixaPerfil = data.perfil;
    localStorage.setItem('manaCaixaToken', caixaToken);
    localStorage.setItem('manaCaixaPerfil', caixaPerfil);
    status.textContent = '';
    atualizarTelaCaixa();
  }catch(e){
    status.style.color = 'var(--yellow)';
    status.textContent = `Não consegui falar com a API em ${API_BASE}.`;
  }
}

function logoutCaixa(){
  caixaToken = null;
  caixaPerfil = null;
  caixaCarteiraId = null;
  localStorage.removeItem('manaCaixaToken');
  localStorage.removeItem('manaCaixaPerfil');
  document.getElementById('caixaClienteNome').textContent = '—';
  document.getElementById('caixaClienteTelefone').textContent = 'Busque um cliente pelo telefone';
  document.getElementById('caixaSaldo').textContent = '—';
  atualizarTelaCaixa();
}

function authHeaders(){
  return { Authorization: `Bearer ${caixaToken}` };
}

/* ================= Painel do caixa ================= */
let telefoneBuscado = null;

async function buscarCliente(){
  const telefone = document.getElementById('telefoneInput').value.trim();
  const status = document.getElementById('caixaStatus');
  const cadastroBox = document.getElementById('caixaCadastroBox');
  cadastroBox.style.display = 'none';
  status.style.color = 'var(--cream-dim)';
  status.textContent = 'Buscando...';

  try{
    const res = await fetch(`${API_BASE}/clientes?telefone=${encodeURIComponent(telefone)}`, {
      headers: authHeaders()
    });
    if(res.status === 401){
      status.style.color = 'var(--yellow)';
      status.textContent = 'Sessão expirada, entre novamente.';
      logoutCaixa();
      return;
    }
    if(res.status === 404){
      telefoneBuscado = telefone;
      status.style.color = 'var(--yellow)';
      status.textContent = 'Cliente não encontrado — cadastrar novo?';
      cadastroBox.style.display = 'block';
      return;
    }
    if(!res.ok){
      status.style.color = 'var(--yellow)';
      status.textContent = 'Erro ao buscar cliente.';
      return;
    }
    const cliente = await res.json();
    caixaCarteiraId = cliente.carteira.id;
    document.getElementById('caixaClienteNome').textContent = cliente.nome;
    document.getElementById('caixaClienteTelefone').textContent = cliente.telefone;
    document.getElementById('caixaSaldo').textContent = cliente.carteira.saldo;
    status.textContent = '';
    document.getElementById('lancamentoFeedback').textContent = '';
    carregarHistoricoCaixa(caixaCarteiraId);
  }catch(e){
    status.style.color = 'var(--yellow)';
    status.textContent = `Não consegui falar com a API em ${API_BASE} — ela está rodando?`;
  }
}

async function cadastrarCliente(){
  const nome = document.getElementById('cadastroNomeInput').value.trim();
  const status = document.getElementById('caixaStatus');

  if(!nome){
    status.style.color = 'var(--yellow)';
    status.textContent = 'Digite o nome do cliente.';
    return;
  }

  try{
    const res = await fetch(`${API_BASE}/clientes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ nome, telefone: telefoneBuscado })
    });
    if(res.status === 401){
      logoutCaixa();
      return;
    }
    const data = await res.json();
    if(!res.ok){
      status.style.color = 'var(--yellow)';
      status.textContent = data.detail || 'Erro ao cadastrar cliente.';
      return;
    }
    document.getElementById('caixaCadastroBox').style.display = 'none';
    document.getElementById('cadastroNomeInput').value = '';
    caixaCarteiraId = data.carteira.id;
    document.getElementById('caixaClienteNome').textContent = data.nome;
    document.getElementById('caixaClienteTelefone').textContent = data.telefone;
    document.getElementById('caixaSaldo').textContent = data.carteira.saldo;
    status.style.color = 'var(--green)';
    status.textContent = 'Cliente cadastrado com sucesso.';
    carregarHistoricoCaixa(caixaCarteiraId);
  }catch(e){
    status.style.color = 'var(--yellow)';
    status.textContent = 'Não consegui falar com a API.';
  }
}

async function lancarTransacao(tipo, valor, rotulo){
  const feedback = document.getElementById('lancamentoFeedback');
  if(!caixaCarteiraId){
    feedback.style.color = 'var(--yellow)';
    feedback.textContent = 'Busque um cliente antes de lançar.';
    return;
  }
  if(!valor || valor <= 0){
    feedback.style.color = 'var(--yellow)';
    feedback.textContent = 'Informe uma quantidade válida.';
    return;
  }

  try{
    const res = await fetch(`${API_BASE}/transacoes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ carteira_id: caixaCarteiraId, tipo, valor })
    });
    if(res.status === 401){
      feedback.style.color = 'var(--yellow)';
      feedback.textContent = 'Sessão expirada, entre novamente.';
      logoutCaixa();
      return;
    }
    const data = await res.json();
    if(!res.ok){
      feedback.style.color = 'var(--yellow)';
      feedback.textContent = data.detail || 'Erro ao lançar.';
      return;
    }
    document.getElementById('caixaSaldo').textContent = data.novo_saldo;
    const sinal = tipo === 'credito' ? '+' : '−';
    feedback.style.color = tipo === 'credito' ? 'var(--green)' : 'var(--yellow)';
    feedback.textContent = `${sinal}${valor} (${rotulo}). Novo saldo: ${data.novo_saldo}.`;
    carregarHistoricoCaixa(caixaCarteiraId);
  }catch(e){
    feedback.style.color = 'var(--yellow)';
    feedback.textContent = 'Não consegui falar com a API.';
  }
}

function resgatarCreditos(){
  const valor = parseInt(document.getElementById('resgateValorInput').value, 10);
  lancarTransacao('debito', valor, 'Resgate');
  document.getElementById('resgateValorInput').value = '';
}

/* ================= Produtos (dinâmico) ================= */
async function carregarProdutos(){
  const grid = document.getElementById('produtoGrid');
  try{
    const res = await fetch(`${API_BASE}/produtos`, { headers: authHeaders() });
    if(res.status === 401){ logoutCaixa(); return; }
    if(!res.ok) throw new Error('erro ao carregar produtos');
    const produtos = await res.json();

    grid.innerHTML = produtos.length
      ? produtos.map(p => `
          <div class="product-btn" onclick="lancarTransacao('credito', ${p.valor_creditos}, '${p.nome.replace(/'/g, "\\'")}')">
            <div class="pname">${p.nome}</div>
            <div class="pcred">+${p.valor_creditos} crédito${p.valor_creditos > 1 ? 's' : ''}</div>
          </div>
        `).join('')
      : '<div style="color:var(--cream-dim); font-size:13px;">Nenhum produto cadastrado ainda.</div>';

    if(caixaPerfil === 'admin') renderAdminProdutos(produtos);
  }catch(e){
    grid.innerHTML = '<div style="color:var(--yellow); font-size:13px;">Não consegui carregar os produtos.</div>';
  }
}

function renderAdminProdutos(produtos){
  const lista = document.getElementById('listaProdutosAdmin');
  lista.innerHTML = produtos.map(p => `
    <div class="admin-produto-row">
      <input class="nome" id="admNome-${p.id}" value="${p.nome}">
      <input class="valor" type="number" min="1" id="admValor-${p.id}" value="${p.valor_creditos}">
      <button onclick="salvarProduto('${p.id}')">Salvar</button>
    </div>
  `).join('');
}

async function salvarProduto(id){
  const feedback = document.getElementById('adminFeedback');
  const nome = document.getElementById(`admNome-${id}`).value.trim();
  const valor = parseInt(document.getElementById(`admValor-${id}`).value, 10);

  try{
    const res = await fetch(`${API_BASE}/produtos/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ nome, valor_creditos: valor })
    });
    const data = await res.json();
    if(!res.ok){
      feedback.style.color = 'var(--yellow)';
      feedback.textContent = data.detail || 'Erro ao salvar produto.';
      return;
    }
    feedback.style.color = 'var(--green)';
    feedback.textContent = `"${data.nome}" atualizado.`;
    carregarProdutos();
  }catch(e){
    feedback.style.color = 'var(--yellow)';
    feedback.textContent = 'Não consegui falar com a API.';
  }
}

async function adicionarProduto(){
  const feedback = document.getElementById('adminFeedback');
  const nome = document.getElementById('novoProdutoNome').value.trim();
  const valor = parseInt(document.getElementById('novoProdutoValor').value, 10);

  if(!nome || !valor || valor <= 0){
    feedback.style.color = 'var(--yellow)';
    feedback.textContent = 'Preencha nome e quantidade de créditos.';
    return;
  }

  try{
    const res = await fetch(`${API_BASE}/produtos`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ nome, valor_creditos: valor })
    });
    const data = await res.json();
    if(!res.ok){
      feedback.style.color = 'var(--yellow)';
      feedback.textContent = data.detail || 'Erro ao criar produto.';
      return;
    }
    document.getElementById('novoProdutoNome').value = '';
    document.getElementById('novoProdutoValor').value = '';
    feedback.style.color = 'var(--green)';
    feedback.textContent = `"${data.nome}" adicionado.`;
    carregarProdutos();
  }catch(e){
    feedback.style.color = 'var(--yellow)';
    feedback.textContent = 'Não consegui falar com a API.';
  }
}

async function carregarHistoricoCaixa(carteiraId){
  // GET /carteira/{id} não exige token — é a mesma rota usada pela auto-identificação do cliente.
  const container = document.getElementById('deskTxList');
  try{
    const res = await fetch(`${API_BASE}/carteira/${carteiraId}`);
    if(!res.ok) return;
    const extrato = await res.json();
    container.innerHTML = extrato.historico.length
      ? extrato.historico.map(h => `
          <div class="desk-tx">
            <span>${h.tipo === 'credito' ? 'Crédito' : 'Débito'} · ${formatData(h.criado_em)}</span>
            <span style="color:${h.tipo === 'credito' ? 'var(--green)' : 'var(--yellow)'}; font-weight:700">${h.tipo === 'credito' ? '+' : '−'}${h.valor}</span>
          </div>
        `).join('')
      : '<div style="color:var(--cream-dim); font-size:13px;">Sem lançamentos ainda.</div>';
  }catch(e){ /* já sinalizamos erro de conexão na busca */ }
}

/* ================= App do cliente ================= */
// Sem senha ainda (depende da decisão de QR/login que ficou em aberto):
// "entrar" aqui é auto-identificação por telefone via GET /clientes/me.
let clienteTelefone = localStorage.getItem('manaClienteTelefone') || null;

function atualizarTelaCliente(){
  const logado = !!clienteTelefone;
  document.getElementById('clienteLoginBox').style.display = logado ? 'none' : 'block';
  document.getElementById('clientePainel').style.display = logado ? 'block' : 'none';
  document.getElementById('clienteAvatar').textContent = logado ? clienteTelefone.slice(-2) : '?';
  if(logado) carregarSaldoCliente();
}

async function entrarCliente(){
  const telefone = document.getElementById('clienteLoginTelefone').value.trim();
  const status = document.getElementById('clienteLoginStatus');
  status.style.color = 'var(--cream-dim)';
  status.textContent = 'Entrando...';

  try{
    const res = await fetch(`${API_BASE}/clientes/me?telefone=${encodeURIComponent(telefone)}`);
    if(!res.ok){
      status.style.color = 'var(--yellow)';
      status.textContent = res.status === 404 ? 'Telefone não encontrado.' : 'Erro ao entrar.';
      return;
    }
    clienteTelefone = telefone;
    localStorage.setItem('manaClienteTelefone', telefone);
    status.textContent = '';
    atualizarTelaCliente();
  }catch(e){
    status.style.color = 'var(--yellow)';
    status.textContent = `Não consegui falar com a API em ${API_BASE}.`;
  }
}

function logoutCliente(){
  clienteTelefone = null;
  localStorage.removeItem('manaClienteTelefone');
  atualizarTelaCliente();
}

async function carregarSaldoCliente(){
  try{
    const resCliente = await fetch(`${API_BASE}/clientes/me?telefone=${encodeURIComponent(clienteTelefone)}`);
    if(!resCliente.ok) throw new Error('cliente não encontrado');
    const cliente = await resCliente.json();
    document.getElementById('clienteSaldoNum').textContent = cliente.carteira.saldo;

    const resExtrato = await fetch(`${API_BASE}/carteira/${cliente.carteira.id}`);
    const extrato = await resExtrato.json();
    const ultimo = extrato.historico[0];
    document.getElementById('clienteHeroFoot').textContent = ultimo
      ? `${ultimo.tipo === 'credito' ? '+' : '−'}${ultimo.valor} em ${formatData(ultimo.criado_em)}`
      : 'Nenhum lançamento ainda';

    const list = document.getElementById('clienteTxList');
    list.innerHTML = extrato.historico.length
      ? extrato.historico.map(h => `
          <div class="tx">
            <div><div class="tx-name">${h.tipo === 'credito' ? 'Crédito' : 'Débito'}</div><div class="tx-date">${formatData(h.criado_em)}</div></div>
            <div class="tx-val ${h.tipo === 'credito' ? 'credit' : 'debit'}">${h.tipo === 'credito' ? '+' : '−'}${h.valor}</div>
          </div>
        `).join('')
      : '<div class="tx"><div class="tx-name" style="color:var(--cream-dim)">Nenhum lançamento ainda.</div></div>';
  }catch(e){
    document.getElementById('clienteHeroFoot').textContent = `API offline em ${API_BASE}`;
    document.getElementById('clienteSaldoNum').textContent = '—';
  }
}

/* ================= Inicialização ================= */
atualizarTelaCaixa();
atualizarTelaCliente();