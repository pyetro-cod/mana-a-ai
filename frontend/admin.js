// Área do dono. Usa o mesmo login do painel do caixa (perfil admin).
// Como no app.js: nada vindo da API entra por innerHTML.
const API_BASE = window.API_BASE;
const token = localStorage.getItem('manaCaixaToken');
const perfil = localStorage.getItem('manaCaixaPerfil');

const CAMPOS_REGRAS = [
  'creditos_por_cupom', 'bonus_boas_vindas', 'validade_cupom_dias',
  'dias_expiracao_saldo', 'validade_resgate_minutos', 'max_cupons_por_dia',
];

function el(tag, { className, text, attrs } = {}, children = []){
  const node = document.createElement(tag);
  if(className) node.className = className;
  if(text !== undefined) node.textContent = text;
  if(attrs) Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
  children.forEach(c => node.appendChild(c));
  return node;
}

function avisar(id, texto, ok = true){
  const linha = document.getElementById(id);
  linha.style.color = ok ? 'var(--green)' : 'var(--yellow)';
  linha.textContent = texto;
}

function dataCurta(iso){
  // A API devolve UTC sem fuso: o "Z" faz o navegador converter para o horário local.
  return new Date(iso + 'Z').toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

// Mensagem legível para os erros de validação (422) e os demais.
function mensagemDeErro(data, padrao){
  if(Array.isArray(data.detail)) return 'Valor fora do permitido: confira os campos.';
  return data.detail || padrao;
}

async function api(caminho, { method = 'GET', body } = {}){
  const res = await fetch(`${API_BASE}${caminho}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if(res.status === 401 || res.status === 403){
    mostrarSemAcesso();
    throw new Error('sem acesso');
  }
  const data = await res.json();
  if(!res.ok) throw new Error(mensagemDeErro(data, 'Algo deu errado.'));
  return data;
}

function mostrarSemAcesso(){
  document.getElementById('adminConteudo').style.display = 'none';
  document.getElementById('semAcesso').style.display = 'grid';
}

/* ================= Regras ================= */
async function carregarRegras(){
  const cfg = await api('/admin/configuracao');
  CAMPOS_REGRAS.forEach(campo => { document.getElementById('cfg_' + campo).value = cfg[campo]; });
}

async function salvarRegras(){
  const corpo = {};
  for(const campo of CAMPOS_REGRAS){
    const valor = parseInt(document.getElementById('cfg_' + campo).value, 10);
    if(Number.isNaN(valor)){ avisar('regrasFeedback', 'Preencha todos os campos com números.', false); return; }
    corpo[campo] = valor;
  }
  try{
    await api('/admin/configuracao', { method: 'PUT', body: corpo });
    avisar('regrasFeedback', 'Regras salvas.');
  }catch(e){ avisar('regrasFeedback', e.message, false); }
}

/* ================= Lotes de cupons ================= */
async function carregarLotes(){
  const lotes = await api('/admin/lotes');
  const lista = document.getElementById('listaLotes');
  if(!lotes.length){
    lista.replaceChildren(el('div', { className: 'status-line', text: 'Nenhum cupom gerado ainda.' }));
    return;
  }
  lista.replaceChildren(...lotes.map(lote => {
    const situacao = lote.cancelado ? 'cancelado'
      : new Date(lote.expira_em + 'Z') < new Date() ? 'vencido' : `vale até ${dataCurta(lote.expira_em)}`;
    const info = el('div', {}, [
      el('div', { className: 'client-name', text: `${lote.quantidade} cupons de ${lote.creditos} créditos` }),
      el('div', { className: 'client-phone',
                  text: `Gerado em ${dataCurta(lote.criado_em)} · ${lote.usados} usados · ${situacao}` }),
    ]);
    const acoes = el('div', { className: 'lote-acoes' });
    const imprimir = el('a', { className: 'logout-btn', text: 'Imprimir folha',
                              attrs: { href: `folha-cupons.html?lote=${encodeURIComponent(lote.id)}`, target: '_blank' } });
    acoes.appendChild(imprimir);
    if(!lote.cancelado){
      const cancelar = el('button', { className: 'logout-btn', text: 'Cancelar' });
      cancelar.addEventListener('click', () => cancelarLote(lote));
      acoes.appendChild(cancelar);
    }
    return el('div', { className: 'lote-linha' + (lote.cancelado ? ' apagado' : '') }, [info, acoes]);
  }));
}

async function gerarLote(){
  const quantidade = parseInt(document.getElementById('loteQuantidade').value, 10);
  if(!quantidade || quantidade < 1 || quantidade > 200){
    avisar('loteFeedback', 'Escolha entre 1 e 200 cupons.', false);
    return;
  }
  try{
    const lote = await api('/admin/lotes', { method: 'POST', body: { quantidade } });
    avisar('loteFeedback', `${lote.quantidade} cupons gerados. Clique em "Imprimir folha".`);
    carregarLotes();
  }catch(e){ avisar('loteFeedback', e.message, false); }
}

async function cancelarLote(lote){
  const ok = confirm(`Cancelar este lote? Os ${lote.quantidade - lote.usados} cupons ainda não usados deixam de valer. ` +
                     'Use se a folha foi perdida ou roubada. Não dá para desfazer.');
  if(!ok) return;
  try{
    await api(`/admin/lotes/${encodeURIComponent(lote.id)}/cancelar`, { method: 'POST' });
    avisar('loteFeedback', 'Lote cancelado.');
    carregarLotes();
  }catch(e){ avisar('loteFeedback', e.message, false); }
}

/* ================= Prêmios ================= */
async function carregarPremios(){
  const premios = await api('/admin/premios');
  const lista = document.getElementById('listaPremios');
  if(!premios.length){
    lista.replaceChildren(el('div', { className: 'status-line', text: 'Nenhum prêmio cadastrado. O dono define o catálogo aqui.' }));
    return;
  }
  lista.replaceChildren(...premios.map(p => {
    const nome = el('input', { className: 'nome', attrs: { maxlength: '80' } });
    nome.value = p.nome;
    const custo = el('input', { className: 'valor', attrs: { type: 'number', min: '1' } });
    custo.value = p.custo_creditos;
    const salvar = el('button', { text: 'Salvar' });
    salvar.addEventListener('click', () =>
      editarPremio(p.id, { nome: nome.value.trim(), custo_creditos: parseInt(custo.value, 10) }));
    const alternar = el('button', { className: 'btn-contorno', text: p.ativo ? 'Desativar' : 'Ativar' });
    alternar.addEventListener('click', () => editarPremio(p.id, { ativo: !p.ativo }));
    return el('div', { className: 'admin-produto-row' + (p.ativo ? '' : ' apagado') }, [nome, custo, salvar, alternar]);
  }));
}

async function editarPremio(id, mudancas){
  try{
    const premio = await api(`/admin/premios/${encodeURIComponent(id)}`, { method: 'PUT', body: mudancas });
    avisar('premioFeedback', `"${premio.nome}" atualizado.`);
    carregarPremios();
  }catch(e){ avisar('premioFeedback', e.message, false); }
}

async function adicionarPremio(){
  const nome = document.getElementById('novoPremioNome').value.trim();
  const custo = parseInt(document.getElementById('novoPremioCusto').value, 10);
  if(!nome || !custo || custo < 1){
    avisar('premioFeedback', 'Preencha o nome e o custo em créditos.', false);
    return;
  }
  try{
    const premio = await api('/admin/premios', { method: 'POST', body: { nome, custo_creditos: custo } });
    document.getElementById('novoPremioNome').value = '';
    document.getElementById('novoPremioCusto').value = '';
    avisar('premioFeedback', `"${premio.nome}" adicionado.`);
    carregarPremios();
  }catch(e){ avisar('premioFeedback', e.message, false); }
}

/* ================= Início ================= */
document.getElementById('btnSalvarRegras').addEventListener('click', salvarRegras);
document.getElementById('btnGerarLote').addEventListener('click', gerarLote);
document.getElementById('btnAdicionarPremio').addEventListener('click', adicionarPremio);

if(!token || perfil !== 'admin'){
  mostrarSemAcesso();
}else{
  document.getElementById('adminConteudo').style.display = 'block';
  Promise.all([carregarRegras(), carregarLotes(), carregarPremios()]).catch(e => {
    if(e.message !== 'sem acesso') avisar('regrasFeedback', `Não consegui falar com a API em ${API_BASE}.`, false);
  });
}
