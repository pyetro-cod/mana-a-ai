// Onde está a API. Aberto em localhost, usa a API local; publicado, usa a API online.
const API_LOCAL = 'http://127.0.0.1:8000';
const API_HOMOLOGACAO = 'https://manacai-api.vercel.app';

window.API_BASE = ['localhost', '127.0.0.1'].includes(window.location.hostname)
  ? API_LOCAL
  : API_HOMOLOGACAO;
