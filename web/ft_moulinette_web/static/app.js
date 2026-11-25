'use strict';

const STATUS = {
  fail: { label: 'échec', plural: 'en échec', problem: true },
  missing: { label: 'manquant', plural: 'manquants', problem: true },
  blocked: { label: 'bloqué', plural: 'bloqués', problem: true },
  unavailable: { label: 'indisponible', plural: 'indisponibles', problem: true },
  manual: { label: 'à relire', plural: 'à relire' },
  reviewed: { label: 'relu', plural: 'relus' },
  skip: { label: 'ignoré', plural: 'ignorés' },
  pass: { label: 'réussi', plural: 'réussis' },
};
const ORDER = Object.keys(STATUS);
const RUN_STATE = {
  queued: 'en attente', running: 'en cours', done: 'terminée', error: 'erreur', cancelled: 'annulée',
};
const ACTIVE = new Set(['queued', 'running']);
const FORM_KEY = 'ftm.form';
const TARGETS_KEY = 'ftm.targets';

const state = {
  runs: [],
  selected: null,       // identifiant de l'exécution affichée
  job: null,            // dernière version complète reçue
  renderedKey: null,    // évite de reconstruire le rapport (et de refermer les détails) à chaque sondage
  filters: null,        // statuts visibles ; null = valeur par défaut selon le rapport
  query: '',
  pollTimer: null,
  clockTimer: null,
  scrollToResult: false,
};

const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

async function api(path, options = {}) {
  const init = { method: options.method || 'GET', headers: {} };
  if (options.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  let data = null;
  try { data = await response.json(); } catch { /* corps vide */ }
  if (!response.ok) throw new Error((data && data.error) || `Erreur HTTP ${response.status}`);
  return data;
}

/* --- formulaire -------------------------------------------------------- */

function readForm() {
  return {
    target: $('target').value.trim(),
    project: $('project').value,
    norm: $('norm').checked,
    memory: $('memory').checked,
    build: $('build').checked,
    iterations: Number($('iterations').value),
    seed: Number($('seed').value),
    timeout: Number($('timeout').value),
  };
}

function fillForm(options) {
  if (!options) return;
  if (typeof options.target === 'string') $('target').value = options.target;
  if (options.project) $('project').value = options.project;
  for (const name of ['norm', 'memory', 'build']) {
    if (typeof options[name] === 'boolean') $(name).checked = options[name];
  }
  for (const name of ['iterations', 'seed', 'timeout']) {
    if (Number.isInteger(options[name])) $(name).value = options[name];
  }
}

function storage(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}

function remember(options) {
  try {
    localStorage.setItem(FORM_KEY, JSON.stringify(options));
    const targets = [options.target, ...storage(TARGETS_KEY, []).filter((t) => t !== options.target)].slice(0, 10);
    localStorage.setItem(TARGETS_KEY, JSON.stringify(targets));
  } catch { /* stockage indisponible : sans conséquence */ }
  renderTargets();
}

function renderTargets() {
  $('recent-targets').replaceChildren(...storage(TARGETS_KEY, []).map((t) => el('option', { value: t })));
}

function validateForm(options) {
  if (!options.target) return 'Indique le chemin du projet ou du fichier à tester.';
  if (!options.target.startsWith('/') && !options.target.startsWith('~')) {
    return 'Le chemin doit être absolu (ou commencer par ~).';
  }
  if (!Number.isInteger(options.iterations) || options.iterations < 1) return 'Les itérations doivent être un entier positif.';
  if (!Number.isInteger(options.seed)) return 'La graine doit être un entier.';
  if (!Number.isInteger(options.timeout) || options.timeout < 1) return 'Le délai doit être un entier positif.';
  return null;
}

function showFormError(message) {
  const node = $('form-error');
  node.textContent = message || '';
  node.hidden = !message;
}

async function submitRun(options) {
  const problem = validateForm(options);
  if (problem) return showFormError(problem);
  showFormError(null);
  const button = $('submit');
  button.disabled = true;
  try {
    const job = await api('/api/runs', { method: 'POST', body: options });
    remember(options);
    select(job.id);
    // Sur une colonne, le rapport est sous le formulaire : y aller une fois le panneau construit.
    state.scrollToResult = matchMedia('(max-width: 860px)').matches;
    await refreshRuns();
  } catch (error) {
    showFormError(error.message);
  } finally {
    button.disabled = false;
  }
}

/* --- historique ---------------------------------------------------------- */

function basename(path) {
  const parts = path.replace(/\/+$/, '').split('/');
  return parts[parts.length - 1] || path;
}

function problemCount(summary) {
  return Object.entries(summary || {}).reduce((n, [s, c]) => n + (STATUS[s] && STATUS[s].problem ? c : 0), 0);
}

function runBadge(run) {
  if (run.status === 'done') {
    const problems = problemCount(run.summary);
    return problems
      ? el('span', { class: 'pill bad', text: `${problems} problème${problems > 1 ? 's' : ''}` })
      : el('span', { class: 'pill good', text: 'aucun problème' });
  }
  return el('span', { class: `pill state-${run.status}`, text: RUN_STATE[run.status] || run.status });
}

function renderRuns() {
  $('runs-empty').hidden = state.runs.length > 0;
  $('runs').replaceChildren(...state.runs.map((run) => el('li', {},
    el('button', {
      type: 'button',
      class: `run${run.id === state.selected ? ' selected' : ''}`,
      title: run.options.target,
      onclick: () => select(run.id),
    },
    el('span', { class: 'run-name', text: basename(run.options.target) }),
    el('span', { class: 'run-meta' }, runBadge(run), el('time', { text: formatTime(run.created) }))))));
}

function syncRun(job) {
  // Met l'historique à jour sans attendre le prochain rafraîchissement de la liste.
  const run = state.runs.find((r) => r.id === job.id);
  if (!run || (run.status === job.status && run.summary === job.summary)) return;
  Object.assign(run, { status: job.status, summary: job.summary, module: job.module });
  renderRuns();
}

function renderHistoryNote(history) {
  const node = $('history-note');
  if (!history) return;
  const text = history.error || (history.enabled ? '' : 'Historique non conservé : il sera perdu à l’arrêt du serveur.');
  node.textContent = text;
  node.hidden = !text;
  node.classList.toggle('form-error', Boolean(history.error));
}

async function refreshRuns() {
  try {
    const data = await api('/api/runs');
    state.runs = data.runs;
    renderHistoryNote(data.history);
    renderRuns();
  } catch { /* le serveur a pu s'arrêter ; on réessaiera au prochain sondage */ }
}

/* --- rapport ------------------------------------------------------------- */

function formatTime(seconds) {
  return new Date(seconds * 1000).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
}

function formatDuration(seconds) {
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))} s`;
  return `${Math.floor(seconds / 60)} min ${String(Math.round(seconds % 60)).padStart(2, '0')} s`;
}

function elapsed(job) {
  if (!job.started) return 0;
  return (job.finished || Date.now() / 1000) - job.started;
}

function select(id) {
  state.selected = id;
  state.job = null;
  state.renderedKey = null;
  state.filters = null;
  state.query = '';
  if (location.hash !== `#run=${id}`) history.replaceState(null, '', `#run=${id}`);
  renderRuns();
  poll();
}

async function poll() {
  clearTimeout(state.pollTimer);
  const id = state.selected;
  if (!id) return;
  let job;
  try {
    job = await api(`/api/runs/${id}`);
  } catch (error) {
    if (id !== state.selected) return;
    state.job = null;
    state.renderedKey = null;
    return renderMessage('Rapport indisponible', error.message);
  }
  if (id !== state.selected) return;
  const wasActive = state.job && ACTIVE.has(state.job.status);
  state.job = job;
  syncRun(job);
  renderResult();
  if (ACTIVE.has(job.status)) {
    state.pollTimer = setTimeout(poll, 1000);
    refreshRuns();
  } else if (wasActive) {
    refreshRuns();
  }
}

function renderMessage(title, text) {
  $('result').replaceChildren(el('div', { class: 'placeholder' },
    el('p', { class: 'placeholder-title', text: title }), el('p', { text })));
}

function defaultFilters(summary) {
  const problems = ORDER.filter((s) => STATUS[s].problem && summary[s]);
  // Comme le rapport texte compact : les problèmes d'abord, tout si rien n'échoue.
  return new Set(problems.length ? [...problems, 'manual'] : ORDER);
}

function renderResult() {
  const job = state.job;
  // Pendant l'exécution, reconstruire seulement quand de nouveaux résultats arrivent.
  const count = job.status === 'running' && job.progress ? job.progress.count : '';
  const key = `${job.id}:${job.status}:${count}`;
  if (key === state.renderedKey) return updateClock();
  state.renderedKey = key;
  clearInterval(state.clockTimer);

  const header = el('div', { class: 'result-head' },
    el('div', { class: 'result-title' },
      el('h2', { class: 'path', text: job.options.target, title: job.options.target }),
      el('div', { class: 'result-meta' },
        job.module && el('span', { class: 'tag', text: job.module }),
        el('span', { class: `pill state-${job.status}`, text: RUN_STATE[job.status] || job.status }),
        el('span', { id: 'clock', class: 'muted' }))),
    el('div', { class: 'actions' },
      ACTIVE.has(job.status)
        ? el('button', { type: 'button', class: 'secondary', onclick: () => cancelRun(job.id), text: 'Annuler' })
        : el('button', { type: 'button', class: 'secondary', onclick: () => rerun(job), text: 'Relancer' }),
      el('button', { type: 'button', class: 'secondary', onclick: () => fillForm(job.options), text: 'Reprendre les réglages' }),
      !ACTIVE.has(job.status) && el('button', {
        type: 'button', class: 'secondary danger', onclick: () => removeRun(job.id), text: 'Supprimer',
      })));

  const command = el('div', { class: 'command' },
    el('code', { text: job.command }),
    el('button', { type: 'button', class: 'link', onclick: (e) => copy(job.command, e.currentTarget), text: 'Copier' }));

  const body = [];
  if (job.status === 'queued') body.push(waiting('En attente : une autre exécution est en cours.'));
  else if (job.status === 'running') body.push(...runningView(job));
  else if (job.status === 'cancelled') body.push(el('div', { class: 'banner neutral', text: 'Exécution annulée.' }));
  else if (job.status === 'error') {
    body.push(el('div', { class: 'banner bad' },
      el('strong', { text: 'Le moteur n’a pas produit de rapport. ' }), el('span', { class: 'pre', text: job.error || '' })));
  } else if (job.report) {
    body.push(...reportView(job.report));
  }

  $('result').replaceChildren(header, command, ...body);
  if (job.status === 'done' && job.report) renderRows(job.report);
  if (state.scrollToResult) {
    state.scrollToResult = false;
    $('result').scrollIntoView({ block: 'start' });
  }
  if (job.status === 'running' && job.partial && job.partial.length) renderGroups($('rows'), job.partial);
  updateClock();
  if (ACTIVE.has(job.status)) state.clockTimer = setInterval(updateClock, 1000);
}

function updateClock() {
  const node = $('clock');
  const job = state.job;
  if (!node || !job) return;
  if (job.status === 'queued') node.textContent = `créée à ${formatTime(job.created)}`;
  else node.textContent = `${ACTIVE.has(job.status) ? 'depuis' : 'durée'} ${formatDuration(elapsed(job))}`;
}

function waiting(text) {
  return el('div', { class: 'banner neutral waiting' }, el('span', { class: 'spinner', 'aria-hidden': 'true' }), text);
}

function summaryChips(summary) {
  return el('div', { class: 'chips static', 'aria-label': 'Résultats reçus' },
    ...ORDER.filter((s) => summary[s]).map((status) => el('span', { class: `chip status-${status}`, 'aria-pressed': 'true' },
      el('span', { class: 'count', text: summary[status] }), ' ',
      summary[status] > 1 ? STATUS[status].plural : STATUS[status].label)));
}

function runningView(job) {
  const progress = job.progress;
  if (!progress) {
    return [waiting('Compilation et tests en cours… Un projet complet prend souvent plus d’une minute.')];
  }
  const done = progress.count;
  const view = [waiting(done
    ? `Compilation et tests en cours… ${done} contrôle${done > 1 ? 's' : ''} effectué${done > 1 ? 's' : ''}.`
    : 'Préparation de la copie du projet et compilation…')];
  if (done) view.push(summaryChips(progress.summary));
  if (job.partial && job.partial.length) {
    view.push(el('p', { class: 'sub live', text: 'Problèmes déjà détectés — le rapport complet suivra' }),
      el('div', { id: 'rows', class: 'rows' }));
  }
  return view;
}

function reportView(report) {
  const summary = report.summary || {};
  if (!state.filters) state.filters = defaultFilters(summary);
  const problems = problemCount(summary);
  const verdict = problems
    ? el('div', { class: 'banner bad' },
      el('strong', { text: `${problems} problème${problems > 1 ? 's' : ''} à corriger.` }),
      ' La CLI renverrait le code de sortie 1.')
    : el('div', { class: 'banner good' },
      el('strong', { text: 'Aucun problème signalé par les contrôles exécutés.' }),
      ' Les contrôles ignorés et la relecture humaine restent à ta charge.');

  const chips = el('div', { class: 'chips', role: 'group', 'aria-label': 'Filtrer par statut' },
    ...ORDER.filter((s) => summary[s]).map((status) => el('button', {
      type: 'button',
      class: `chip status-${status}`,
      'aria-pressed': String(state.filters.has(status)),
      onclick: (event) => {
        if (state.filters.has(status)) state.filters.delete(status); else state.filters.add(status);
        event.currentTarget.setAttribute('aria-pressed', String(state.filters.has(status)));
        renderRows(report);
      },
    }, el('span', { class: 'count', text: summary[status] }), ' ', summary[status] > 1 ? STATUS[status].plural : STATUS[status].label)),
    el('button', {
      type: 'button', class: 'link', text: 'Tout afficher',
      onclick: () => { state.filters = new Set(ORDER); state.renderedKey = null; renderResult(); },
    }));

  const search = el('input', {
    type: 'search', class: 'search', placeholder: 'Filtrer par fichier, contrôle ou message…', value: state.query,
    'aria-label': 'Rechercher dans les résultats',
    oninput: (event) => { state.query = event.target.value; renderRows(report); },
  });

  return [verdict, el('div', { class: 'toolbar' }, chips, search), el('div', { id: 'rows', class: 'rows' })];
}

function matches(row, query) {
  if (!query) return true;
  const haystack = [row.relative, row.file, row.check, row.label, row.message, row.raw_message].join('\n').toLowerCase();
  return query.toLowerCase().split(/\s+/).filter(Boolean).every((word) => haystack.includes(word));
}

function renderRows(report) {
  // Appelé juste après le remplacement du panneau : attendre que #rows soit dans le document.
  const container = $('rows');
  if (!container) return requestAnimationFrame(() => renderRows(report));
  const rows = report.results.filter((row) => state.filters.has(row.status) && matches(row, state.query));
  if (!rows.length) {
    return container.replaceChildren(el('p', { class: 'empty', text: 'Aucun résultat ne correspond aux filtres.' }));
  }
  renderGroups(container, rows);
}

function renderGroups(container, rows) {
  const groups = new Map();
  for (const row of rows) {
    const file = row.relative || row.file;
    if (!groups.has(file)) groups.set(file, []);
    groups.get(file).push(row);
  }
  const rank = (row) => ORDER.indexOf(row.status);
  const sections = [...groups.entries()]
    .sort(([a, ra], [b, rb]) => Math.min(...ra.map(rank)) - Math.min(...rb.map(rank)) || a.localeCompare(b))
    .map(([file, items]) => el('section', { class: 'file' },
      el('h3', { title: items[0].file }, el('span', { class: 'path', text: file }),
        el('span', { class: 'muted', text: `${items.length} résultat${items.length > 1 ? 's' : ''}` })),
      ...items.sort((a, b) => rank(a) - rank(b) || a.line - b.line).map(rowView)));
  container.replaceChildren(...sections);
}

function rowView(row) {
  const details = [];
  if (row.raw_message) details.push(el('p', { class: 'sub', text: 'Diagnostic brut' }), el('pre', { text: row.raw_message }));
  if (row.diagnostics && row.diagnostics.length > 1) {
    details.push(el('p', { class: 'sub', text: 'Emplacements' }), el('ul', { class: 'locations' },
      ...row.diagnostics.map((d) => el('li', { class: 'mono', text: `${d.file}:${d.line}:${d.column}` }))));
  }
  const location = row.line > 1 || row.column > 1 ? `ligne ${row.line}, col. ${row.column}` : null;
  return el('article', { class: `row status-${row.status}` },
    el('div', { class: 'row-head' },
      el('span', { class: `badge status-${row.status}`, text: STATUS[row.status] ? STATUS[row.status].label : row.status }),
      el('span', { class: 'row-label', text: row.label || row.check }),
      row.label && row.label !== row.check ? el('code', { class: 'muted', text: row.check }) : null,
      location && el('span', { class: 'muted location', text: location })),
    el('pre', { class: 'message', text: row.message }),
    details.length ? el('details', {}, el('summary', { text: 'Détails' }), ...details) : null);
}

async function cancelRun(id) {
  try { await api(`/api/runs/${id}`, { method: 'DELETE' }); } catch (error) { showFormError(error.message); }
  poll();
}

const EMPTY_TITLE = 'Aucun rapport sélectionné';
const EMPTY_TEXT = 'Indique le chemin de ta libft ou de ton ft_printf, puis lance la moulinette.';

async function removeRun(id) {
  if (!confirm('Supprimer cette exécution de l’historique ?')) return;
  try {
    await api(`/api/history/${id}`, { method: 'DELETE' });
  } catch (error) {
    return showFormError(error.message);
  }
  await refreshRuns();
  if (state.runs.length) return select(state.runs[0].id);
  clearTimeout(state.pollTimer);
  clearInterval(state.clockTimer);
  Object.assign(state, { selected: null, job: null, renderedKey: null });
  history.replaceState(null, '', location.pathname);
  renderRuns();
  renderMessage(EMPTY_TITLE, EMPTY_TEXT);
}

function rerun(job) {
  fillForm(job.options);
  submitRun(job.options);
}

async function copy(text, button) {
  try {
    await navigator.clipboard.writeText(text);
    button.textContent = 'Copié';
  } catch {
    button.textContent = 'Copie impossible';
  }
  setTimeout(() => { button.textContent = 'Copier'; }, 1500);
}

/* --- démarrage ----------------------------------------------------------- */

document.addEventListener('DOMContentLoaded', async () => {
  fillForm(storage(FORM_KEY, null));
  renderTargets();
  $('run-form').addEventListener('submit', (event) => {
    event.preventDefault();
    submitRun(readForm());
  });
  await refreshRuns();
  const fromHash = /^#run=([0-9a-f]{12})$/.exec(location.hash);
  if (fromHash) select(fromHash[1]);
  else if (state.runs.length) select(state.runs[0].id);
  // Rafraîchit l'historique si d'autres onglets ont lancé des exécutions.
  setInterval(() => { if (!document.hidden) refreshRuns(); }, 5000);
});
