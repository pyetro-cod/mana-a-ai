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

/* ================= DOM seguro =================
   Nada vindo da API passa por innerHTML: os elementos são criados aqui e o texto
   entra por textContent, que nunca é interpretado como HTML. */
function el(tag, { className, text, style, attrs } = {}, children = []){
  const node = document.createElement(tag);
  if(className) node.className = className;
  if(text !== undefined) node.textContent = text;
  if(style) Object.assign(node.style, style);
  if(attrs) Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
  children.forEach(c => node.appendChild(c));
  return node;
}

function renderLista(container, nodes, mensagemVazia, classeVazia){
  container.replaceChildren(...(nodes.length
    ? nodes
    : [el('div', { className: classeVazia, text: mensagemVazia, style: { color: 'var(--cream-dim)', fontSize: '13px' } })]));
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

    const botoes = produtos.map(p => {
      const btn = el('div', { className: 'product-btn' }, [
        el('div', { className: 'pname', text: p.nome }),
        el('div', { className: 'pcred', text: `+${p.valor_creditos} crédito${p.valor_creditos > 1 ? 's' : ''}` }),
      ]);
      btn.addEventListener('click', () => lancarTransacao('credito', p.valor_creditos, p.nome));
      return btn;
    });
    renderLista(grid, botoes, 'Nenhum produto cadastrado ainda.');

    if(caixaPerfil === 'admin') renderAdminProdutos(produtos);
  }catch(e){
    grid.replaceChildren(el('div', { text: 'Não consegui carregar os produtos.', style: { color: 'var(--yellow)', fontSize: '13px' } }));
  }
}

function renderAdminProdutos(produtos){
  const lista = document.getElementById('listaProdutosAdmin');
  lista.replaceChildren(...produtos.map(p => {
    const inputNome = el('input', { className: 'nome' });
    inputNome.value = p.nome;
    const inputValor = el('input', { className: 'valor', attrs: { type: 'number', min: '1' } });
    inputValor.value = p.valor_creditos;
    const btn = el('button', { text: 'Salvar' });
    btn.addEventListener('click', () => salvarProduto(p.id, inputNome.value.trim(), parseInt(inputValor.value, 10)));
    return el('div', { className: 'admin-produto-row' }, [inputNome, inputValor, btn]);
  }));
}

async function salvarProduto(id, nome, valor){
  const feedback = document.getElementById('adminFeedback');

  try{
    const res = await fetch(`${API_BASE}/produtos/${encodeURIComponent(id)}`, {
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
  const container = document.getElementById('deskTxList');
  try{
    const res = await fetch(`${API_BASE}/carteira/${encodeURIComponent(carteiraId)}`, { headers: authHeaders() });
    if(res.status === 401){ logoutCaixa(); return; }
    if(!res.ok) return;
    const extrato = await res.json();
    renderLista(container, extrato.historico.map(h => {
      const credito = h.tipo === 'credito';
      return el('div', { className: 'desk-tx' }, [
        el('span', { text: `${credito ? 'Crédito' : 'Débito'} · ${formatData(h.criado_em)}` }),
        el('span', { text: `${credito ? '+' : '−'}${h.valor}`, style: { color: credito ? 'var(--green)' : 'var(--yellow)', fontWeight: '700' } }),
      ]);
    }), 'Sem lançamentos ainda.');
  }catch(e){ /* já sinalizamos erro de conexão na busca */ }
}

/* ================= App do cliente ================= */
// Login por código de uso único: telefone → código → (primeira vez) nome + aceite.
// O token do cliente identifica a carteira; o telefone nunca mais vai na URL.
let clienteToken = localStorage.getItem('manaClienteToken') || null;
let telefoneLogin = null;
localStorage.removeItem('manaClienteTelefone'); // legacy phone-only login

function statusCliente(texto, cor = 'var(--cream-dim)'){
  const status = document.getElementById('clienteLoginStatus');
  status.style.color = cor;
  status.textContent = texto;
}

function mostrarPassoCliente(passo){
  ['passoTelefone', 'passoCodigo', 'passoCadastro'].forEach(id => {
    document.getElementById(id).style.display = id === passo ? 'block' : 'none';
  });
}

function atualizarTelaCliente(){
  const logado = !!clienteToken;
  document.getElementById('clienteLoginBox').style.display = logado ? 'none' : 'block';
  document.getElementById('clientePainel').style.display = logado ? 'block' : 'none';
  document.getElementById('clienteAvatar').textContent = '?';
  if(logado) carregarSaldoCliente();
  else mostrarPassoCliente('passoTelefone');
}

async function pedirCodigo(){
  const telefone = telefoneLogin || document.getElementById('clienteLoginTelefone').value.trim();
  if(!/^\d{10,11}$/.test(telefone)){
    statusCliente('Digite DDD + número, só dígitos (ex.: 83999998888).', 'var(--yellow)');
    return;
  }
  statusCliente('Enviando código...');
  try{
    const res = await fetch(`${API_BASE}/auth/cliente/codigo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ telefone })
    });
    const data = await res.json();
    if(!res.ok){
      statusCliente(data.detail || 'Não foi possível enviar o código.', 'var(--yellow)');
      return;
    }
    telefoneLogin = telefone;
    document.getElementById('codigoTitulo').textContent = `Digite o código enviado para ${telefone}`;
    document.getElementById('clienteCodigo').value = '';
    mostrarPassoCliente('passoCodigo');
    statusCliente('Código enviado. Ele vale por 10 minutos.', 'var(--green)');
  }catch(e){
    statusCliente(`Não consegui falar com a API em ${API_BASE}.`, 'var(--yellow)');
  }
}

function voltarParaTelefone(){
  telefoneLogin = null;
  mostrarPassoCliente('passoTelefone');
  statusCliente('');
}

async function entrarComCodigo(extras = {}){
  const codigo = document.getElementById('clienteCodigo').value.trim();
  if(!/^\d{6}$/.test(codigo)){
    mostrarPassoCliente('passoCodigo');
    statusCliente('O código tem 6 dígitos.', 'var(--yellow)');
    return;
  }
  statusCliente('Conferindo...');
  try{
    const res = await fetch(`${API_BASE}/auth/cliente/entrar`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ telefone: telefoneLogin, codigo, ...extras })
    });
    const data = await res.json();
    if(res.status === 409 && data.detail === 'cadastro_necessario'){
      mostrarPassoCliente('passoCadastro');
      statusCliente('');
      return;
    }
    if(!res.ok){
      const msg = typeof data.detail === 'string' ? data.detail : 'Confira os dados e tente de novo.';
      statusCliente(msg, 'var(--yellow)');
      return;
    }
    clienteToken = data.token;
    localStorage.setItem('manaClienteToken', clienteToken);
    telefoneLogin = null;
    statusCliente('');
    atualizarTelaCliente();
  }catch(e){
    statusCliente(`Não consegui falar com a API em ${API_BASE}.`, 'var(--yellow)');
  }
}

function confirmarCodigo(){
  entrarComCodigo();
}

function concluirCadastro(){
  const nome = document.getElementById('clienteNome').value.trim();
  const aceite = document.getElementById('clienteAceite').checked;
  if(nome.length < 2){
    statusCliente('Digite seu nome.', 'var(--yellow)');
    return;
  }
  if(!aceite){
    statusCliente('Para criar a conta, é preciso aceitar o uso dos dados.', 'var(--yellow)');
    return;
  }
  entrarComCodigo({ nome, aceite_termos: true });
}

function logoutCliente(){
  clienteToken = null;
  localStorage.removeItem('manaClienteToken');
  atualizarTelaCliente();
}

async function carregarSaldoCliente(){
  const headers = { Authorization: `Bearer ${clienteToken}` };
  try{
    const resCliente = await fetch(`${API_BASE}/clientes/me`, { headers });
    if(resCliente.status === 401){ logoutCliente(); return; }
    if(!resCliente.ok) throw new Error('cliente indisponível');
    const cliente = await resCliente.json();
    document.getElementById('clienteSaldoNum').textContent = cliente.carteira.saldo;
    document.getElementById('clienteAvatar').textContent = cliente.nome.trim().charAt(0).toUpperCase() || '?';

    const resExtrato = await fetch(`${API_BASE}/clientes/me/extrato`, { headers });
    if(resExtrato.status === 401){ logoutCliente(); return; }
    if(!resExtrato.ok) throw new Error('extrato indisponível');
    const extrato = await resExtrato.json();
    const ultimo = extrato.historico[0];
    document.getElementById('clienteHeroFoot').textContent = ultimo
      ? `${ultimo.tipo === 'credito' ? '+' : '−'}${ultimo.valor} em ${formatData(ultimo.criado_em)}`
      : 'Nenhum lançamento ainda';

    const list = document.getElementById('clienteTxList');
    renderLista(list, extrato.historico.map(h => {
      const credito = h.tipo === 'credito';
      return el('div', { className: 'tx' }, [
        el('div', {}, [
          el('div', { className: 'tx-name', text: credito ? 'Crédito' : 'Débito' }),
          el('div', { className: 'tx-date', text: formatData(h.criado_em) }),
        ]),
        el('div', { className: `tx-val ${credito ? 'credit' : 'debit'}`, text: `${credito ? '+' : '−'}${h.valor}` }),
      ]);
    }), 'Nenhum lançamento ainda.', 'tx');
  }catch(e){
    document.getElementById('clienteHeroFoot').textContent = `API offline em ${API_BASE}`;
    document.getElementById('clienteSaldoNum').textContent = '—';
  }
}

/* ================= Inicialização ================= */
atualizarTelaCaixa();
atualizarTelaCliente();