// Definido em config.js (API local ou online, conforme onde o app foi aberto).
const API_BASE = window.API_BASE;

function show(id, btn){
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById('view-' + id).classList.add('active');
  document.querySelectorAll('.switcher button').forEach(b => b.classList.remove('active'));
  if(btn) btn.classList.add('active');
}

/* ================= Datas =================
   A API guarda e devolve horários em UTC sem o "Z" no fim. Sem ele, o navegador
   leria como horário local e tudo ficaria 3 horas adiantado em João Pessoa. */
function dataDaApi(iso){
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z');
}

function formatData(iso){
  return dataDaApi(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
}

function formatDataHora(iso){
  return dataDaApi(iso).toLocaleString('pt-BR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
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

function mensagem(linhaId, texto, tom = 'neutro'){
  const linha = document.getElementById(linhaId);
  linha.style.color = { ok: 'var(--green)', erro: 'var(--yellow)', neutro: 'var(--cream-dim)' }[tom];
  linha.textContent = texto;
}

// O que cada lançamento significa, em português de balcão.
const ROTULO_MOTIVO = {
  cupom: 'Cupom',
  bonus: 'Bônus de boas-vindas',
  resgate: 'Troca por prêmio',
  estorno_resgate: 'Troca desfeita (créditos devolvidos)',
  expiracao: 'Créditos vencidos',
  manual: 'Ajuste da loja',
};

function linhaDoExtrato(h, classe){
  const credito = h.tipo === 'credito';
  return el('div', { className: classe }, [
    el('div', {}, [
      el('div', { className: 'tx-name', text: ROTULO_MOTIVO[h.motivo] || (credito ? 'Crédito' : 'Débito') }),
      el('div', { className: 'tx-date', text: formatData(h.criado_em) }),
    ]),
    el('div', { className: `tx-val ${credito ? 'credit' : 'debit'}`, text: `${credito ? '+' : '−'}${h.valor}` }),
  ]);
}

/* ================= Balcão: autenticação ================= */
let caixaToken = localStorage.getItem('manaCaixaToken') || null;
let caixaPerfil = localStorage.getItem('manaCaixaPerfil') || null;
let caixaCarteiraId = null;

function atualizarTelaCaixa(){
  const logado = !!caixaToken;
  const admin = logado && caixaPerfil === 'admin';
  document.getElementById('caixaLoginBox').style.display = logado ? 'none' : 'grid';
  document.getElementById('caixaPainel').style.display = logado ? 'grid' : 'none';
  document.getElementById('adminLink').style.display = admin ? 'inline-block' : 'none';
  document.getElementById('ajusteAdmin').style.display = admin ? 'block' : 'none';
}

async function loginCaixa(){
  const telefone = document.getElementById('caixaLoginTelefone').value.trim();
  const senha = document.getElementById('caixaLoginSenha').value;
  mensagem('caixaLoginStatus', 'Entrando...');

  try{
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ telefone, senha })
    });
    const data = await res.json();
    if(!res.ok){
      const texto = typeof data.detail === 'string' ? data.detail : 'Confira telefone e senha.';
      mensagem('caixaLoginStatus', texto, 'erro');
      return;
    }
    caixaToken = data.token;
    caixaPerfil = data.perfil;
    localStorage.setItem('manaCaixaToken', caixaToken);
    localStorage.setItem('manaCaixaPerfil', caixaPerfil);
    document.getElementById('caixaLoginSenha').value = '';
    mensagem('caixaLoginStatus', '');
    atualizarTelaCaixa();
  }catch(e){
    mensagem('caixaLoginStatus', `Não consegui falar com a API em ${API_BASE}.`, 'erro');
  }
}

function logoutCaixa(){
  caixaToken = null;
  caixaPerfil = null;
  caixaCarteiraId = null;
  localStorage.removeItem('manaCaixaToken');
  localStorage.removeItem('manaCaixaPerfil');
  document.getElementById('caixaClienteNome').textContent = '—';
  document.getElementById('caixaClienteTelefone').textContent = 'Busque pelo telefone';
  document.getElementById('caixaSaldo').textContent = '—';
  document.getElementById('deskTxList').replaceChildren();
  limparResgate();
  atualizarTelaCaixa();
}

// fetch do balcão: põe o token e trata sessão vencida num lugar só.
async function apiCaixa(caminho, { method = 'GET', body } = {}){
  const res = await fetch(`${API_BASE}${caminho}`, {
    method,
    headers: { Authorization: `Bearer ${caixaToken}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if(res.status === 401){
    logoutCaixa();
    mensagem('caixaLoginStatus', 'Sessão expirada, entre novamente.', 'erro');
    throw new Error('sessao');
  }
  return { res, data: await res.json() };
}

/* ================= Balcão: confirmar troca ================= */
let codigoConferido = null;

function limparResgate(){
  codigoConferido = null;
  document.getElementById('resgateCodigoInput').value = '';
  document.getElementById('resgateCard').style.display = 'none';
  document.getElementById('resgateAcoes').style.display = 'none';
}

const RECUSA_RESGATE = {
  resgate_inexistente: 'Código não encontrado. Confira com o cliente (ou já foi usado/cancelado).',
  resgate_expirado: 'Código vencido. Os créditos já voltaram para o cliente: peça um código novo no app.',
};

async function conferirResgate(){
  const codigo = document.getElementById('resgateCodigoInput').value.trim();
  if(!/^\d{6}$/.test(codigo)){
    mensagem('resgateStatus', 'O código tem 6 dígitos.', 'erro');
    return;
  }
  mensagem('resgateStatus', 'Conferindo...');
  try{
    const { res, data } = await apiCaixa(`/resgates/${codigo}`);
    if(!res.ok){
      limparResgate();
      mensagem('resgateStatus', RECUSA_RESGATE[data.detail] || 'Não foi possível conferir.', 'erro');
      return;
    }
    codigoConferido = codigo;
    document.getElementById('confereCliente').textContent = data.cliente;
    document.getElementById('conferePremio').textContent = data.premio;
    document.getElementById('confereCusto').textContent = data.custo_creditos;
    document.getElementById('resgateCard').style.display = 'flex';
    document.getElementById('resgateAcoes').style.display = 'block';
    mensagem('resgateStatus', 'Confira o nome com o cliente antes de entregar.', 'ok');
  }catch(e){
    if(e.message !== 'sessao') mensagem('resgateStatus', `Não consegui falar com a API em ${API_BASE}.`, 'erro');
  }
}

async function confirmarResgate(){
  if(!codigoConferido) return;
  try{
    const { res, data } = await apiCaixa(`/resgates/${codigoConferido}/confirmar`, { method: 'POST' });
    limparResgate();
    if(!res.ok){
      mensagem('resgateStatus', RECUSA_RESGATE[data.detail] || 'Não foi possível confirmar.', 'erro');
      return;
    }
    mensagem('resgateStatus', `Pronto: ${data.premio} entregue para ${data.cliente}.`, 'ok');
  }catch(e){
    if(e.message !== 'sessao') mensagem('resgateStatus', 'Não consegui falar com a API.', 'erro');
  }
}

/* ================= Balcão: consultar cliente ================= */
async function buscarCliente(){
  const telefone = document.getElementById('telefoneInput').value.trim();
  if(!/^\d{10,11}$/.test(telefone)){
    mensagem('caixaStatus', 'Digite DDD + número, só dígitos.', 'erro');
    return;
  }
  mensagem('caixaStatus', 'Buscando...');
  try{
    const { res, data } = await apiCaixa(`/clientes?telefone=${encodeURIComponent(telefone)}`);
    if(res.status === 404){
      mensagem('caixaStatus', 'Sem cadastro. O cliente se cadastra sozinho no app ao usar o 1º cupom.', 'erro');
      return;
    }
    if(!res.ok){
      mensagem('caixaStatus', 'Erro ao buscar cliente.', 'erro');
      return;
    }
    caixaCarteiraId = data.carteira.id;
    document.getElementById('caixaClienteNome').textContent = data.nome;
    document.getElementById('caixaClienteTelefone').textContent = data.telefone;
    mensagem('caixaStatus', '');
    mensagem('lancamentoFeedback', '');
    carregarHistoricoCaixa();
  }catch(e){
    if(e.message !== 'sessao') mensagem('caixaStatus', `Não consegui falar com a API em ${API_BASE}.`, 'erro');
  }
}

async function carregarHistoricoCaixa(){
  try{
    const { res, data } = await apiCaixa(`/carteira/${encodeURIComponent(caixaCarteiraId)}`);
    if(!res.ok) return;
    // The statement applies expiry first, so this is the balance that is really valid.
    document.getElementById('caixaSaldo').textContent = data.saldo;
    renderLista(document.getElementById('deskTxList'),
                data.historico.map(h => linhaDoExtrato(h, 'desk-tx')), 'Sem lançamentos ainda.');
  }catch(e){ /* erro de conexão já aparece na busca */ }
}

async function ajusteManual(tipo){
  const valor = parseInt(document.getElementById('ajusteValor').value, 10);
  if(!caixaCarteiraId){ mensagem('lancamentoFeedback', 'Busque um cliente antes.', 'erro'); return; }
  if(!valor || valor <= 0){ mensagem('lancamentoFeedback', 'Informe uma quantidade válida.', 'erro'); return; }
  const verbo = tipo === 'credito' ? 'creditar' : 'debitar';
  if(!confirm(`Confirma ${verbo} ${valor} créditos? Fica registrado no seu usuário.`)) return;
  try{
    const { res, data } = await apiCaixa('/transacoes', {
      method: 'POST', body: { carteira_id: caixaCarteiraId, tipo, valor },
    });
    if(!res.ok){
      mensagem('lancamentoFeedback', typeof data.detail === 'string' ? data.detail : 'Erro ao lançar.', 'erro');
      return;
    }
    document.getElementById('ajusteValor').value = '';
    mensagem('lancamentoFeedback', `Feito. Novo saldo: ${data.novo_saldo}.`, 'ok');
    carregarHistoricoCaixa();
  }catch(e){
    if(e.message !== 'sessao') mensagem('lancamentoFeedback', 'Não consegui falar com a API.', 'erro');
  }
}

/* ================= App do cliente: login ================= */
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
  if(logado){
    carregarCliente().then(usarCupomGuardado);
  }else{
    pararContagem();
    mostrarPassoCliente('passoTelefone');
    if(cupomGuardado()) statusCliente('Entre com seu telefone para receber os créditos do cupom.', 'var(--yellow)');
  }
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
      statusCliente(typeof data.detail === 'string' ? data.detail : 'Não foi possível enviar o código.', 'var(--yellow)');
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

// fetch do cliente: põe o token e desloga se ele venceu.
async function apiCliente(caminho, { method = 'GET', body } = {}){
  const res = await fetch(`${API_BASE}${caminho}`, {
    method,
    headers: { Authorization: `Bearer ${clienteToken}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if(res.status === 401){
    logoutCliente();
    throw new Error('sessao');
  }
  return { res, data: await res.json() };
}

/* ================= App do cliente: saldo, prêmios e extrato ================= */
let saldoAtual = 0;

function textoVencimento(venceEm){
  if(!venceEm) return 'Use um cupom para ganhar créditos';
  const dias = Math.ceil((dataDaApi(venceEm) - new Date()) / 86400000);
  const data = dataDaApi(venceEm).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
  if(dias <= 1) return `Seus créditos vencem hoje (${data}). Compre para renovar!`;
  return `Vencem em ${dias} dias (${data}). Cada compra renova o prazo.`;
}

async function carregarCliente(){
  try{
    const [{ data: cliente }, { data: extrato }, { data: premios }, { data: pendente }] = await Promise.all([
      apiCliente('/clientes/me'),
      apiCliente('/clientes/me/extrato'),
      apiCliente('/clientes/me/premios'),
      apiCliente('/clientes/me/resgates/pendente'),
    ]);
    // The statement and the profile run the same expiry/refund rules; use the statement's balance.
    saldoAtual = extrato.saldo;
    const primeiroNome = cliente.nome.trim().split(/\s+/)[0];
    document.getElementById('clienteSaudacao').textContent = `Olá, ${primeiroNome}! Seus créditos`;
    document.getElementById('clienteAvatar').textContent = primeiroNome.charAt(0).toUpperCase() || '?';
    document.getElementById('clienteSaldoNum').textContent = extrato.saldo;
    const foot = document.getElementById('clienteHeroFoot');
    foot.textContent = textoVencimento(extrato.vence_em);
    foot.classList.toggle('alerta', !!extrato.vence_em && dataDaApi(extrato.vence_em) - new Date() < 5 * 86400000);

    renderLista(document.getElementById('clienteTxList'),
                extrato.historico.map(h => linhaDoExtrato(h, 'tx')), 'Nenhum lançamento ainda.', 'tx');
    renderPremios(premios);
    mostrarResgate(pendente);
  }catch(e){
    if(e.message === 'sessao') return;
    document.getElementById('clienteHeroFoot').textContent = `API offline em ${API_BASE}`;
    document.getElementById('clienteSaldoNum').textContent = '—';
  }
}

function renderPremios(premios){
  const nodes = premios.map(p => {
    const falta = p.custo_creditos - saldoAtual;
    const botao = el('button', { className: 'premio-btn', text: falta > 0 ? `faltam ${falta}` : 'Trocar' });
    botao.disabled = falta > 0;
    botao.addEventListener('click', () => pedirResgate(p));
    return el('div', { className: 'premio' + (falta > 0 ? ' longe' : '') }, [
      el('div', {}, [
        el('div', { className: 'tx-name', text: p.nome }),
        el('div', { className: 'tx-date', text: `${p.custo_creditos} créditos` }),
      ]),
      botao,
    ]);
  });
  renderLista(document.getElementById('clientePremios'), nodes, 'A loja ainda vai divulgar os prêmios.');
}

/* ================= App do cliente: usar cupom ================= */
// O QR impresso abre o app com ?cupom=CODIGO. O código fica guardado na aba até o
// cliente entrar, e sai da barra de endereço para não ser reaproveitado ao recarregar.
function cupomGuardado(){
  return sessionStorage.getItem('manaCupomPendente');
}

function capturarCupomDaUrl(){
  const params = new URLSearchParams(location.search);
  const codigo = params.get('cupom');
  if(!codigo) return;
  sessionStorage.setItem('manaCupomPendente', codigo);
  params.delete('cupom');
  const resto = params.toString();
  history.replaceState(null, '', location.pathname + (resto ? `?${resto}` : '') + location.hash);
  show('cliente', document.querySelector('.switcher button'));
}

function usarCupomGuardado(){
  const codigo = cupomGuardado();
  if(!codigo || !clienteToken) return;
  sessionStorage.removeItem('manaCupomPendente');
  document.getElementById('cupomCodigo').value = codigo;
  usarCupom();
}

const RECUSA_CUPOM = {
  cupom_inexistente: 'Código não encontrado. Confira as letras e números do cupom.',
  cupom_ja_usado: 'Este cupom já foi usado.',
  cupom_expirado: 'Este cupom passou da validade.',
  cupom_cancelado: 'Este cupom foi cancelado pela loja.',
  limite_diario: 'Você já usou um cupom hoje. Guarde este para amanhã!',
  muitas_tentativas: 'Muitos códigos errados. Aguarde um pouco e tente de novo.',
};

async function usarCupom(){
  const campo = document.getElementById('cupomCodigo');
  const codigo = campo.value.trim();
  if(codigo.replace(/[\s-]/g, '').length < 6){
    mensagem('cupomStatus', 'Digite o código impresso no cupom.', 'erro');
    return;
  }
  mensagem('cupomStatus', 'Validando cupom...');
  try{
    const { res, data } = await apiCliente('/clientes/me/cupons', { method: 'POST', body: { codigo } });
    if(!res.ok){
      const texto = RECUSA_CUPOM[data.detail] || 'Código inválido. Confira e tente de novo.';
      mensagem('cupomStatus', texto, 'erro');
      return;
    }
    campo.value = '';
    let texto = `+${data.creditos} créditos!`;
    if(data.bonus) texto += ` E +${data.bonus} de bônus de boas-vindas!`;
    if(data.expirado) texto += ` (${data.expirado} antigos já tinham vencido.)`;
    mensagem('cupomStatus', texto, 'ok');
    carregarCliente();
  }catch(e){
    if(e.message !== 'sessao') mensagem('cupomStatus', 'Não consegui falar com a API.', 'erro');
  }
}

/* ================= App do cliente: trocar por prêmio ================= */
let contagem = null;

function pararContagem(){
  if(contagem) clearInterval(contagem);
  contagem = null;
}

function mostrarResgate(resgate){
  pararContagem();
  const box = document.getElementById('resgateBox');
  if(!resgate){ box.style.display = 'none'; return; }
  box.style.display = 'block';
  document.getElementById('resgateCodigo').textContent = `${resgate.codigo.slice(0, 3)} ${resgate.codigo.slice(3)}`;
  document.getElementById('resgatePremio').textContent = `${resgate.premio} · ${resgate.custo_creditos} créditos`;
  const fim = dataDaApi(resgate.expira_em);
  const tick = () => {
    const resta = Math.max(0, Math.round((fim - new Date()) / 1000));
    const mm = String(Math.floor(resta / 60)).padStart(2, '0');
    const ss = String(resta % 60).padStart(2, '0');
    document.getElementById('resgateTempo').textContent = `Vale por mais ${mm}:${ss}`;
    if(resta === 0){
      // Expired: the API refunds on the next read, so reloading shows the credits back.
      pararContagem();
      carregarCliente();
    }
  };
  tick();
  contagem = setInterval(tick, 1000);
  box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

const RECUSA_RESGATE_CLIENTE = {
  saldo_insuficiente: 'Créditos insuficientes para este prêmio.',
  premio_inexistente: 'Este prêmio não está mais disponível.',
};

async function pedirResgate(premio){
  if(!confirm(`Trocar ${premio.custo_creditos} créditos por "${premio.nome}"? Você mostra o código no caixa.`)) return;
  mensagem('premioStatus', 'Gerando código...');
  try{
    const { res, data } = await apiCliente('/clientes/me/resgates', { method: 'POST', body: { premio_id: premio.id } });
    if(!res.ok){
      mensagem('premioStatus', RECUSA_RESGATE_CLIENTE[data.detail] || 'Não foi possível trocar agora.', 'erro');
      return;
    }
    mensagem('premioStatus', '');
    carregarCliente();
  }catch(e){
    if(e.message !== 'sessao') mensagem('premioStatus', 'Não consegui falar com a API.', 'erro');
  }
}

async function cancelarResgate(){
  if(!confirm('Desistir da troca? Os créditos voltam para você.')) return;
  try{
    await apiCliente('/clientes/me/resgates/cancelar', { method: 'POST' });
    carregarCliente();
  }catch(e){ /* sessão vencida já desloga */ }
}

/* ================= Inicialização ================= */
document.getElementById('btnUsarCupom').addEventListener('click', usarCupom);
document.getElementById('cupomCodigo').addEventListener('keydown', e => { if(e.key === 'Enter') usarCupom(); });
document.getElementById('btnCancelarResgate').addEventListener('click', cancelarResgate);
document.getElementById('btnConferirResgate').addEventListener('click', conferirResgate);
document.getElementById('resgateCodigoInput').addEventListener('keydown', e => { if(e.key === 'Enter') conferirResgate(); });
document.getElementById('btnConfirmarResgate').addEventListener('click', confirmarResgate);
document.getElementById('btnLimparResgate').addEventListener('click', () => { limparResgate(); mensagem('resgateStatus', ''); });
document.getElementById('btnAjusteCredito').addEventListener('click', () => ajusteManual('credito'));
document.getElementById('btnAjusteDebito').addEventListener('click', () => ajusteManual('debito'));

capturarCupomDaUrl();
atualizarTelaCaixa();
atualizarTelaCliente();
