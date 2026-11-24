// Folha A4 com os QRs de um lote. Os QRs vêm prontos da API (imagem SVG em data URI).
const POR_FOLHA = 12;

function el(tag, { className, text, attrs } = {}, children = []){
  const node = document.createElement(tag);
  if(className) node.className = className;
  if(text !== undefined) node.textContent = text;
  if(attrs) Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
  children.forEach(c => node.appendChild(c));
  return node;
}

function aviso(texto){
  document.getElementById('resumo').textContent = texto;
}

function cartao(cupom, lote){
  const validade = new Date(lote.expira_em + 'Z').toLocaleDateString('pt-BR');
  const qr = el('img', { className: 'qr', attrs: { alt: `QR do cupom ${cupom.codigo}` } });
  qr.src = cupom.qr;  // data:image/svg+xml: an <img> never runs scripts inside an SVG
  return el('div', { className: 'cupom' + (cupom.usado ? ' usado' : '') }, [
    el('div', { className: 'cupom-topo' }, [
      el('img', { attrs: { src: 'logo.jpg', alt: '' } }),
      el('span', { text: 'Manaçaí' }),
    ]),
    el('div', { className: 'cupom-valor' }, [
      document.createTextNode('Escaneie e ganhe '),
      el('b', { text: String(lote.creditos) }),
      document.createTextNode(' créditos'),
    ]),
    qr,
    el('div', { className: 'cupom-codigo', text: cupom.codigo }),
    el('div', { className: 'cupom-rodape',
                text: `Use até ${validade}. Vale uma vez. 1º cupom: +bônus de boas-vindas.` }),
  ]);
}

async function carregar(){
  const loteId = new URLSearchParams(location.search).get('lote');
  const token = localStorage.getItem('manaCaixaToken');
  if(!loteId){ aviso('Abra esta página pela área de administração.'); return; }
  if(!token){ aviso('Entre como admin no painel do caixa primeiro.'); return; }

  let res;
  try{
    res = await fetch(`${window.API_BASE}/admin/lotes/${encodeURIComponent(loteId)}`,
                      { headers: { Authorization: `Bearer ${token}` } });
  }catch(e){
    aviso(`Não consegui falar com a API em ${window.API_BASE}.`);
    return;
  }
  if(res.status === 401 || res.status === 403){ aviso('Só o admin pode imprimir cupons.'); return; }
  if(!res.ok){ aviso('Lote não encontrado.'); return; }
  const lote = await res.json();

  if(lote.cancelado){
    aviso('Este lote foi cancelado: os cupons não valem mais. Não imprima.');
    return;
  }

  const container = document.getElementById('folhas');
  for(let i = 0; i < lote.cupons.length; i += POR_FOLHA){
    const folha = el('div', { className: 'folha' },
                     lote.cupons.slice(i, i + POR_FOLHA).map(c => cartao(c, lote)));
    container.appendChild(folha);
  }
  const paginas = Math.ceil(lote.cupons.length / POR_FOLHA);
  const usados = lote.cupons.filter(c => c.usado).length;
  aviso(`${lote.cupons.length} cupons · ${paginas} folha${paginas > 1 ? 's' : ''} A4` +
        (usados ? ` · ${usados} já usados (apagados)` : ''));
  const botao = document.getElementById('btnImprimir');
  botao.style.display = 'inline-block';
  botao.addEventListener('click', () => window.print());
}

carregar();
