'use strict';

// ── estado global ─────────────────────────────────────────────────────────────

const S = {
  searchES:    null,   // EventSource para busca
  transCtrl:   null,   // AbortController para tradução
  percObraES:  null,   // EventSource para obra completa
  percObras:   [],     // catálogo Perseus carregado
  percRefs:    [],     // referências da obra seleccionada
  percObraURN: '',     // URN da edição seleccionada
  workData:    {},     // {chave: [{corpus,author,work,line_idx,lines,match_offset}]}
  workOrder:   [],     // ordem de chegada das obras
  selWork:     null,   // obra activa no painel de resultados
  savedSel:    '',     // última selecção de texto guardada
};

// ── tabs ──────────────────────────────────────────────────────────────────────

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const id = btn.dataset.tab;
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    btn.classList.add('active');
  });
});

function switchTab(id) {
  document.getElementById(id)?.classList.add('active');
  document.querySelectorAll('.tab-content').forEach(t => {
    if (t.id !== id) t.classList.remove('active');
  });
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === id);
  });
}

// ── status ────────────────────────────────────────────────────────────────────

function setStatus(msg) {
  document.getElementById('status-bar').textContent = msg;
}

// ── busca ─────────────────────────────────────────────────────────────────────

document.getElementById('q')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') startSearch();
});

function startSearch() {
  const q = document.getElementById('q').value.trim();
  if (!q) return;

  S.workData  = {};
  S.workOrder = [];
  S.selWork   = null;
  document.getElementById('works-list').innerHTML = '';
  document.getElementById('results').innerHTML    = '';

  const ignore = document.getElementById('chk-ignore').checked ? '1' : '0';
  const ctx    = document.getElementById('spin-ctx').value;
  const max    = document.getElementById('spin-max').value;
  const corpus = document.querySelector('input[name="corpus"]:checked').value;
  const url    = `/api/buscar?q=${enc(q)}&ignore=${ignore}&ctx=${ctx}&max=${max}&corpus=${corpus}`;

  if (S.searchES) { S.searchES.close(); }
  S.searchES = new EventSource(url);
  setBuscaBusy(true);

  S.searchES.addEventListener('result', e => onResult(JSON.parse(e.data)));
  S.searchES.addEventListener('status', e => setStatus(JSON.parse(e.data).msg));
  S.searchES.addEventListener('done', e => {
    const d = JSON.parse(e.data);
    S.searchES.close(); S.searchES = null;
    setBuscaBusy(false);
    const n = Object.values(S.workData).reduce((s, a) => s + a.length, 0);
    const w = Object.keys(S.workData).length;
    setStatus(`${n} ocorrência(s) em ${w} obra(s)${d.truncated ? ' (truncado)' : ''}.`);
  });
  S.searchES.addEventListener('erro', e => {
    setStatus('Erro: ' + JSON.parse(e.data).msg);
    S.searchES.close(); S.searchES = null;
    setBuscaBusy(false);
  });
  S.searchES.onerror = () => {
    setBuscaBusy(false); S.searchES = null;
  };
}

function stopSearch() {
  if (S.searchES) {
    S.searchES.close(); S.searchES = null;
    setBuscaBusy(false);
    setStatus('Busca interrompida.');
  }
}

function setBuscaBusy(busy) {
  document.getElementById('btn-search').disabled = busy;
  document.getElementById('btn-stop').disabled   = !busy;
}

function onResult(d) {
  const key = `[${d.corpus}] ${d.author} — ${d.work}`;
  if (!S.workData[key]) {
    S.workData[key] = [];
    S.workOrder.push(key);
    const li = document.createElement('li');
    li.textContent  = key;
    li.dataset.key  = key;
    li.title        = key;
    li.addEventListener('click', () => selectWork(key));
    document.getElementById('works-list').appendChild(li);
    if (S.workOrder.length === 1) selectWork(key);  // primeira obra
  }
  S.workData[key].push(d);
  if (S.selWork === key) appendBlock(d);
}

function selectWork(key) {
  S.selWork = key;
  document.querySelectorAll('#works-list li').forEach(li =>
    li.classList.toggle('active', li.dataset.key === key));
  const panel = document.getElementById('results');
  panel.innerHTML = '';
  (S.workData[key] || []).forEach(appendBlock);
}

function appendBlock(d) {
  const q = document.getElementById('q').value;
  const ignoreCase = document.getElementById('chk-ignore').checked;
  const pat = buildPattern(q, ignoreCase);
  const key = `[${d.corpus}] ${d.author} — ${d.work}`;
  const panel = document.getElementById('results');

  const wrap = document.createElement('div');
  wrap.className = 'result-block';

  const hdr = document.createElement('div');
  hdr.className   = 'result-header';
  hdr.textContent = `${key}  (linha ${d.line_idx + 1})`;
  wrap.appendChild(hdr);

  d.lines.forEach((line, j) => {
    const row = document.createElement('div');
    row.className = 'result-line' + (j === d.match_offset ? ' match-line' : '');
    if (j === d.match_offset) {
      row.innerHTML = '▶ ' + hlLine(line, pat);
    } else {
      row.textContent = '  ' + line;
    }
    wrap.appendChild(row);
  });

  const sep = document.createElement('div');
  sep.className   = 'result-sep';
  sep.textContent = '─'.repeat(60);
  wrap.appendChild(sep);

  panel.appendChild(wrap);
}

// ── regex pattern (mirror do Python) ─────────────────────────────────────────

function buildPattern(term, ignoreCase) {
  try {
    const flags = ignoreCase ? 'gi' : 'g';
    const hasSuf = term.startsWith('-') && term.length > 1;
    const hasPre = term.endsWith('-')   && term.length > 1;
    let core = term;
    if (hasSuf) core = core.slice(1);
    if (hasPre) core = core.slice(0, -1);
    const isRe = /[.^$*+?\[\]\\|()\{\}]/.test(core);
    if (isRe) return new RegExp(term, flags);
    const esc = core.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    let pat;
    if (hasSuf && hasPre) pat = `\\b\\w*${esc}\\w*\\b`;
    else if (hasSuf)      pat = `\\b\\w*${esc}\\b`;
    else if (hasPre)      pat = `\\b${esc}\\w*\\b`;
    else                  pat = `\\b${esc}\\b`;
    return new RegExp(pat, flags);
  } catch { return null; }
}

function hlLine(line, pat) {
  const safe = line.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  if (!pat) return safe;
  return safe.replace(pat, m =>
    `<span class="hl">${m.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</span>`
  );
}

// guarda selecção do painel de resultados
document.getElementById('results')?.addEventListener('mouseup', () => {
  const sel = window.getSelection().toString().trim();
  if (sel) S.savedSel = sel;
});

// ── tradução ──────────────────────────────────────────────────────────────────

function getTextoParaTraduzir() {
  // 1. selecção activa em qualquer painel de resultados
  const sel = window.getSelection().toString().trim();
  if (sel) return sel;
  // 2. última selecção guardada
  return S.savedSel;
}

async function startTranslation(motor) {
  const texto = getTextoParaTraduzir();
  if (!texto) {
    document.getElementById('trans-output').textContent =
      '⚠ Seleccione texto nos resultados primeiro.';
    return;
  }

  const lingua  = document.getElementById('sel-lingua').value;
  const modelo  = motor === 'gemini'
    ? document.getElementById('sel-gemini-modelo').value
    : document.getElementById('sel-ollama-modelo').value;

  if (S.transCtrl) S.transCtrl.abort();
  S.transCtrl = new AbortController();

  const out = document.getElementById('trans-output');
  const label = motor === 'gemini' ? '🌟 Gemini' : motor === 'comentario' ? '📖 Comentário' : '🤖 Ollama';
  out.textContent = `${label}…\n\n`;

  try {
    const resp = await fetch('/api/traduzir', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({texto, lingua, motor, modelo}),
      signal: S.transCtrl.signal,
    });
    await readSSEStream(resp.body, {
      chunk: d => { out.textContent += d.text; out.scrollTop = out.scrollHeight; },
      status: d => setStatus(d.msg),
      erro:   d => { out.textContent = `⚠ ${d.msg}`; },
    });
  } catch (err) {
    if (err.name !== 'AbortError') out.textContent = `⚠ ${err.message}`;
  }
}

function stopTranslation() {
  if (S.transCtrl) {
    S.transCtrl.abort();
    S.transCtrl = null;
    document.getElementById('trans-output').textContent += '\n\n[Interrompido]';
  }
}

// ── dicionário offline (via Ollama translate com modo especial) ───────────────

function lookupDict(modo) {
  // para dicionários offline precisamos de uma rota separada; por agora usa texto seleccionado como contexto
  const palavra = (window.getSelection().toString().trim() || S.savedSel).split(/\s+/)[0];
  if (!palavra) {
    document.getElementById('trans-output').textContent = '⚠ Seleccione uma palavra primeiro.';
    return;
  }
  startTranslationWith(palavra, modo);
}

async function startTranslationWith(texto, motor) {
  if (S.transCtrl) S.transCtrl.abort();
  S.transCtrl = new AbortController();

  const lingua = document.getElementById('sel-lingua').value;
  const out    = document.getElementById('trans-output');
  out.textContent = `⏳ ${motor}…\n\n`;

  try {
    const resp = await fetch('/api/traduzir', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({texto, lingua, motor, modelo: null}),
      signal: S.transCtrl.signal,
    });
    await readSSEStream(resp.body, {
      chunk: d => { out.textContent += d.text; out.scrollTop = out.scrollHeight; },
      erro:  d => { out.textContent = `⚠ ${d.msg}`; },
    });
  } catch (err) {
    if (err.name !== 'AbortError') out.textContent = `⚠ ${err.message}`;
  }
}

// ── Gemini key dialog ─────────────────────────────────────────────────────────

function showGeminiKeyDialog() {
  document.getElementById('gemini-key-input').value = '';
  document.getElementById('gemini-dialog').style.display = 'flex';
  document.getElementById('gemini-key-input').focus();
}
function closeGeminiKeyDialog() {
  document.getElementById('gemini-dialog').style.display = 'none';
}
async function saveGeminiKey() {
  const chave = document.getElementById('gemini-key-input').value.trim();
  if (!chave) return;
  const resp = await fetch('/api/gemini_chave', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({chave}),
  });
  const d = await resp.json();
  setStatus(d.ok ? '✓ Chave API Gemini guardada.' : `⚠ ${d.msg}`);
  closeGeminiKeyDialog();
}
document.getElementById('gemini-key-input')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') saveGeminiKey();
  if (e.key === 'Escape') closeGeminiKeyDialog();
});

// ── Perseus / Textos Online ───────────────────────────────────────────────────

function percLoadCatalog(forcar = false) {
  const lingua = document.getElementById('perc-lingua').value;
  const list   = document.getElementById('perc-works');
  list.innerHTML = '<li class="loading">A carregar…</li>';
  document.getElementById('perc-cat-status').textContent = '⏳ A carregar catálogo…';

  fetch(`/api/perseus/catalogo?lingua=${lingua}&forcar=${forcar ? 1 : 0}`)
    .then(r => r.json())
    .then(obras => {
      if (obras.erro) throw new Error(obras.erro);
      S.percObras = obras;
      percFilter('');
      document.getElementById('perc-cat-status').textContent = `✓ ${obras.length} edições disponíveis.`;
    })
    .catch(err => {
      document.getElementById('perc-cat-status').textContent = `⚠ Erro: ${err.message}`;
    });
}

function percFilter(q) {
  const list  = document.getElementById('perc-works');
  list.innerHTML = '';
  (S.percObras || [])
    .filter(o => !q || o.display.toLowerCase().includes(q.toLowerCase()))
    .forEach(o => {
      const li = document.createElement('li');
      li.textContent = o.display;
      li.title = o.display;
      li.addEventListener('click', () => percSelectWork(o));
      list.appendChild(li);
    });
}

document.getElementById('perc-filter')?.addEventListener('input', e => percFilter(e.target.value));

function percSelectWork(obra) {
  S.percObraURN = obra.edicao_urn;
  // highlight
  document.querySelectorAll('.perc-works-list li').forEach(li =>
    li.classList.toggle('active', li.textContent === obra.display));

  document.getElementById('perc-obra-sel').innerHTML =
    `<b>${esc(obra.display)}</b><br><small>${esc(obra.edicao_urn)}</small>`;

  const refsEl = document.getElementById('perc-refs');
  refsEl.innerHTML = '<option>(a carregar…)</option>';
  setPercBtn('btn-perc-obra', false);
  document.getElementById('perc-pass-status').textContent = 'A carregar referências…';

  fetch(`/api/perseus/refs?urn=${enc(obra.edicao_urn)}`)
    .then(r => r.json())
    .then(refs => {
      if (refs.erro) throw new Error(refs.erro);
      S.percRefs = refs;
      refsEl.innerHTML = '';
      refs.forEach(urn => {
        const opt = document.createElement('option');
        opt.value       = urn;
        opt.textContent = urn.split(':').pop();
        refsEl.appendChild(opt);
      });
      const has = refs.length > 0;
      setPercBtn('btn-perc-obra', has);
      document.getElementById('perc-pass-status').textContent =
        has ? `✓ ${refs.length} referências.` : 'Sem referências.';
      if (has) percLoadPassagem(refs[0]);  // carrega a primeira passagem automaticamente
    })
    .catch(err => {
      document.getElementById('perc-pass-status').textContent = `⚠ Refs: ${err.message}`;
    });
}

function percLoadPassagem(urnOverride) {
  const urn = urnOverride || document.getElementById('perc-refs').value;
  if (!urn) return;
  const txt = document.getElementById('perc-texto');
  txt.textContent = '⏳ A carregar…';
  document.getElementById('perc-pass-status').textContent = 'A buscar…';

  fetch(`/api/perseus/passagem?urn=${enc(urn)}`)
    .then(r => r.json())
    .then(d => {
      if (d.erro) throw new Error(d.erro);
      txt.textContent = d.texto || '';
      const words = (d.texto || '').trim().split(/\s+/).filter(Boolean).length;
      document.getElementById('perc-pass-status').textContent = `✓ ${words} palavras.`;
      const has = !!d.texto;
      setPercBtn('btn-perc-traduzir', has);
      setPercBtn('btn-perc-copiar', has);
    })
    .catch(err => {
      txt.textContent = `⚠ Erro: ${err.message}`;
    });
}

function percObraCompleta() {
  if (!S.percObraURN) return;
  if (S.percObraES) { S.percObraES.close(); }

  const txt = document.getElementById('perc-texto');
  const n   = S.percRefs.length;
  txt.textContent = `⏳ A descarregar obra completa… 0/${n}`;
  setPercBtn('btn-perc-obra', false);

  S.percObraES = new EventSource(`/api/perseus/obra?urn=${enc(S.percObraURN)}`);

  S.percObraES.addEventListener('progress', e => {
    const d = JSON.parse(e.data);
    document.getElementById('perc-pass-status').textContent = `⏳ ${d.atual}/${d.total}…`;
  });
  S.percObraES.addEventListener('done', e => {
    const d = JSON.parse(e.data);
    txt.textContent = d.texto;
    setPercBtn('btn-perc-obra', true);
    setPercBtn('btn-perc-traduzir', true);
    setPercBtn('btn-perc-copiar', true);
    const words = d.texto.trim().split(/\s+/).filter(Boolean).length;
    document.getElementById('perc-pass-status').textContent = `✓ Obra completa — ${words} palavras.`;
    S.percObraES.close(); S.percObraES = null;
  });
  S.percObraES.addEventListener('erro', e => {
    txt.textContent = `⚠ ${JSON.parse(e.data).msg}`;
    setPercBtn('btn-perc-obra', true);
    S.percObraES.close(); S.percObraES = null;
  });
}

function percGetTexto() {
  const sel = window.getSelection().toString().trim();
  if (sel) return sel;
  return document.getElementById('perc-texto').textContent.trim();
}

async function percTraduzir() {
  const texto = percGetTexto();
  if (!texto) return;

  const lingua  = document.getElementById('perc-lingua').value === 'grc' ? 'grc' : 'la';
  const modelo  = document.getElementById('sel-gemini-modelo').value;
  const outEl   = document.getElementById('perc-trans-output');
  outEl.style.display = 'block';
  outEl.textContent   = '🌟 Gemini…\n\n';

  if (S.transCtrl) S.transCtrl.abort();
  S.transCtrl = new AbortController();

  try {
    const resp = await fetch('/api/traduzir', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({texto, lingua, motor: 'gemini', modelo}),
      signal: S.transCtrl.signal,
    });
    await readSSEStream(resp.body, {
      chunk: d => { outEl.textContent += d.text; outEl.scrollTop = outEl.scrollHeight; },
      erro:  d => { outEl.textContent = `⚠ ${d.msg}`; },
    });
  } catch (err) {
    if (err.name !== 'AbortError') outEl.textContent = `⚠ ${err.message}`;
  }
}


function percCopiar() {
  const texto = document.getElementById('perc-texto').textContent;
  navigator.clipboard.writeText(texto).then(() => {
    document.getElementById('perc-pass-status').textContent = '✓ Copiado.';
  });
}

function setPercBtn(id, enabled) {
  const el = document.getElementById(id);
  if (el) el.disabled = !enabled;
}

// ── utilitários ───────────────────────────────────────────────────────────────

function enc(s) { return encodeURIComponent(s); }
function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/**
 * Lê um stream SSE de um ReadableStream e chama os handlers correspondentes.
 * handlers: { [eventName]: (data) => void }
 */
async function readSSEStream(body, handlers) {
  const reader  = body.getReader();
  const decoder = new TextDecoder();
  let buf = '';

  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    buf += decoder.decode(value, {stream: true});

    const parts = buf.split('\n\n');
    buf = parts.pop();  // último bloco potencialmente incompleto

    for (const block of parts) {
      let eventType = 'message', dataStr = '';
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) eventType = line.slice(7).trim();
        if (line.startsWith('data: '))  dataStr   = line.slice(6);
      }
      if (!dataStr) continue;
      try {
        const data = JSON.parse(dataStr);
        handlers[eventType]?.(data);
      } catch { /* ignore malformed */ }
    }
  }
}

// ── init ──────────────────────────────────────────────────────────────────────

// carrega catálogo Perseus ao primeiro clique na aba
document.querySelector('[data-tab="tab-online"]')?.addEventListener('click', () => {
  if (!S.percObras.length) percLoadCatalog();
}, {once: true});
