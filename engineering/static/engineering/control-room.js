(function () {
  'use strict';
  const room = document.getElementById('room-search');
  if (!room) return;
  const byId = id => document.getElementById(id);
  const form = byId('search-form'), input = byId('search-text'), submit = byId('search-submit');
  const contract = JSON.parse(byId('search-contract').textContent);
  const example = 'A double click creates two tickets. How do I make repeated requests return the first one?';
  let worker = null, modelState = 'idle', modelLoadMs = null, workerTransferBytes = null, loadTimer, serial = 0, normalSubmit = false;
  const pending = new Map();
  const featureEnabled = room.dataset.semanticEnabled === 'true';
  const gatePassed = room.dataset.gatePassed === 'true';
  const semanticAllowed = () => featureEnabled && (gatePassed || byId('experimental-semantic').checked);
  const initialResources = new Set(performance.getEntriesByType('resource').map(r => r.name));
  function text(tag, value, className) {
    const node = document.createElement(tag);
    node.textContent = value;
    if (className) node.className = className;
    return node;
  }
  function modelStatus(message) {
    byId('model-status').textContent = message;
    const state = document.querySelector('[data-boundary-model]');
    if (state) state.textContent = modelState;
  }
  function failWorker() {
    clearTimeout(loadTimer);
    if (worker) worker.terminate();
    worker = null; modelState = 'failed';
    pending.forEach(p => { clearTimeout(p.timer); p.reject(new Error('model_unavailable')); });
    pending.clear();
    byId('load-model').disabled = !semanticAllowed();
    byId('verify-embeddings').disabled = true;
    modelStatus('The model is unavailable. Keyword search works immediately; retry model loading when ready.');
  }
  function loadModel() {
    if (!semanticAllowed() || modelState === 'loading' || modelState === 'ready' || byId('simulate-outage').checked) return;
    modelState = 'loading';
    byId('load-model').disabled = true;
    modelStatus('Loading the self-hosted model and runtime. Keyword search is usable while they load.');
    try {
      worker = new Worker(room.dataset.workerUrl, { type: 'module' });
      worker.onerror = failWorker;
      worker.onmessage = ({ data }) => {
        if (data.type === 'progress') modelStatus(`Loading model: ${data.progress}%. Keyword search is ready.`);
        if (data.type === 'ready') {
          clearTimeout(loadTimer); modelState = 'ready'; modelLoadMs = data.model_load_ms;
          workerTransferBytes = data.observed_transfer_bytes;
          byId('load-model').disabled = true;
          byId('verify-embeddings').disabled = false;
          modelStatus('Browser model ready. Your next search uses evaluated semantic retrieval, with a confidence fallback.');
          transferMetrics();
        }
        if (data.type === 'error') { failWorker(); return; }
        if (data.type === 'embedding' && pending.has(data.id)) {
          const p = pending.get(data.id); clearTimeout(p.timer); pending.delete(data.id); p.resolve(data);
        }
      };
      loadTimer = setTimeout(failWorker, 90000);
      worker.postMessage({ type: 'load' });
    } catch { failWorker(); }
  }
  function embed(value) {
    return new Promise((resolve, reject) => {
      const id = ++serial;
      const timer = setTimeout(() => { pending.delete(id); reject(new Error('model_unavailable')); failWorker(); }, 20000);
      pending.set(id, { resolve, reject, timer });
      worker.postMessage({ type: 'embed', id, text: value });
    });
  }
  function renderResults(result, elapsed, embeddingMs) {
    byId('search-status').textContent = (result.experimental ? 'Experimental semantic path; the frozen default gate is not met. ' : '') + result.notice;
    const assessment = result.semantic_assessment;
    const detail = assessment.estimated_relevance !== null ? ` Semantic candidate similarity ${assessment.top_similarity.toFixed(3)}; estimated top-result relevance ${(assessment.estimated_relevance * 100).toFixed(1)}%, threshold ${(assessment.threshold * 100).toFixed(1)}%.` : '';
    byId('search-timing').textContent = `Server ranking ${result.timings.server_ranking_ms.toFixed(2)} ms · browser embedding ${embeddingMs === null ? 'not used' : embeddingMs.toFixed(1) + ' ms'} · request round trip ${elapsed.toFixed(1)} ms.${detail}`;
    const list = byId('search-results'); list.replaceChildren();
    for (const resultItem of result.results) {
      const li = document.createElement('li');
      li.append(text('h4', resultItem.title));
      if (resultItem.retrieval_reason === 'related_thread') li.append(text('p', 'Related thread · included through a published discussion link', 'lab-note'));
      li.append(text('p', `${resultItem.score_kind === 'cosine' ? 'Similarity' : 'BM25 keyword score'}: ${resultItem.score.toFixed(3)}${resultItem.confidence === null ? '' : ' · Estimated top-result relevance: ' + (resultItem.confidence * 100).toFixed(1) + '%'}`, 'room-result-score'));
      const details = document.createElement('details');
      details.append(text('summary', 'Inspect discussion'), text('p', resultItem.text), text('p', `Fictional discussion · ${resultItem.id}`, 'lab-note'));
      const use = text('button', 'Use this discussion', 'lab-button is-secondary'); use.type = 'button';
      use.addEventListener('click', () => {
        byId('id_text').value = resultItem.text;
        byId('guide-status').textContent = 'Discussion selected. Submit it below, then choose Lost acknowledgement and attempt delivery.';
        location.hash = 'room-delivery'; byId('id_text').focus();
      });
      details.append(use); li.append(details); list.append(li);
    }
    if (!result.results.length) list.append(text('li', 'No keyword matches. Try another technical problem covered by the public corpus.'));
  }
  form.addEventListener('submit', async event => {
    if (normalSubmit) return;
    event.preventDefault();
    if (submit.disabled) return;
    submit.disabled = true; form.setAttribute('aria-busy', 'true');
    byId('search-status').textContent = 'Searching the public discussions…';
    let embedding = null, embeddingMs = null;
    let fallback = byId('simulate-outage').checked ? 'model_unavailable_demo' : byId('keyword-only').checked ? 'keyword_requested' : !featureEnabled ? 'semantic_disabled' : !semanticAllowed() ? 'evaluation_gate' : modelState === 'failed' ? 'model_unavailable' : 'model_loading';
    try {
      if (semanticAllowed() && !byId('simulate-outage').checked && !byId('keyword-only').checked && modelState === 'ready') {
        try {
          const encoded = await embed(input.value.trim());
          embedding = { ...contract, values: encoded.values }; embeddingMs = encoded.embedding_ms;
        } catch { fallback = 'model_unavailable'; }
      }
      const started = performance.now();
      const response = await fetch(room.dataset.searchUrl, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value },
        body: JSON.stringify({ text: input.value, embedding, fallback, experimental: !gatePassed && byId('experimental-semantic').checked, browser: { embedding_ms: embeddingMs, model_load_ms: embedding ? modelLoadMs : null } }), signal: AbortSignal.timeout(20000) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Search could not finish. Try again or use the standard form.');
      renderResults(result, performance.now() - started, embeddingMs);
      await refreshMetrics();
    } catch (error) {
      byId('search-status').textContent = error.message || 'Search could not finish. Your text is preserved.';
      const recover = text('button', 'Use standard keyword form', 'lab-button is-secondary'); recover.type = 'button';
      recover.addEventListener('click', () => { normalSubmit = true; form.requestSubmit(); });
      byId('search-results').replaceChildren(recover);
    } finally { submit.disabled = false; form.removeAttribute('aria-busy'); }
  });
  const fmt = value => value === null ? 'No samples' : value.toFixed(2) + ' ms';
  async function refreshMetrics() {
    try {
      const response = await fetch(room.dataset.metricsUrl, { headers: { Accept: 'application/json' }, credentials: 'same-origin', signal: AbortSignal.timeout(10000) });
      if (!response.ok) throw new Error();
      const m = await response.json(), container = byId('metrics-content'); container.replaceChildren();
      const dl = document.createElement('dl'); dl.className = 'room-metric-list';
      const entries = [['Search observations', `${m.window.retained} / ${m.window.maximum}`], ['Semantic / keyword searches', `${m.search.semantic} / ${m.search.keyword}`], ['Delivery attempts / inbox effects', `${m.delivery.attempts} / ${m.delivery.inbox_effects}`], ['Duplicate effects prevented (trace window)', m.delivery.duplicate_preventions_in_trace_window], ['Original submission replays (trace window)', m.delivery.replays_in_trace_window], ['Low-confidence assessments', `${m.search.low_confidence} / ${m.search.assessed}`]];
      for (const [name, value] of entries) { const row = document.createElement('div'); row.append(text('dt', name), text('dd', value)); dl.append(row); }
      container.append(dl, text('p', 'Newest forty search observations and eighty delivery trace stages. Browser timings are client-reported; server ranking excludes embedding and network travel.', 'lab-note'));
      const table = document.createElement('table'); table.className = 'room-table'; table.append(text('caption', 'Measured latency · current run'));
      const head = document.createElement('thead'), header = document.createElement('tr');
      for (const name of ['Boundary', 'Samples', 'Median', 'p95']) { const th = text('th', name); th.scope = 'col'; header.append(th); } head.append(header); table.append(head);
      const body = document.createElement('tbody');
      for (const [name, data] of [['Server ranking', m.latency.server_ranking], ['Browser embedding', m.latency.browser_embedding], ['Browser model load', m.latency.browser_model_load]]) { const row = document.createElement('tr'), th = text('th', name); th.scope = 'row'; row.append(th, text('td', data.count), text('td', fmt(data.median_ms)), text('td', fmt(data.p95_ms))); body.append(row); } table.append(body);
      const wrap = document.createElement('div'); wrap.className = 'room-table-wrap'; wrap.append(table); container.append(wrap);
      const details = document.createElement('details'); details.open = true; details.append(text('summary', 'Fallback reasons and score distribution'));
      const reasons = document.createElement('ul');
      for (const [reason, count] of Object.entries(m.search.fallbacks)) reasons.append(text('li', `${reason}: ${count}`));
      if (!reasons.children.length) reasons.append(text('li', 'No fallback observations yet.'));
      const bins = document.createElement('ul'); for (const bin of m.search.score_distribution) bins.append(text('li', `Cosine ${bin.label}: ${bin.count}`));
      details.append(reasons, bins); container.append(details, text('p', `Artifact: ${m.artifact.index_version} · ${m.artifact.healthy ? 'healthy' : m.artifact.reason} · ${m.artifact.documents} public discussions.`));
      for (const [selector, count] of [['[data-architecture-submissions]', m.delivery.submissions], ['[data-architecture-attempts]', m.delivery.attempts], ['[data-architecture-effects]', m.delivery.inbox_effects]]) document.querySelector(selector).textContent = count;
      if (m.delivery.replays_in_trace_window && m.delivery.duplicate_preventions_in_trace_window) byId('guide-status').textContent = 'Recovery and replay verified in this run. Inspect the architecture to connect each boundary with its source and tests.';
      else if (m.delivery.duplicate_preventions_in_trace_window) byId('guide-status').textContent = 'Recovery prevented a duplicate inbox effect. Replay the saved submission to check the original request key.';
      else if (m.delivery.inbox_effects && m.delivery.attempts) byId('guide-status').textContent = 'The destination has an effect. If its acknowledgement was lost, select Deliver / recover for the same operation.';
      else if (m.delivery.submissions) byId('guide-status').textContent = 'Source and outbox recorded. Choose Lost acknowledgement, then attempt delivery.';
      byId('metrics-status').textContent = 'Measurements refreshed from your run.';
      transferMetrics();
    } catch { byId('metrics-status').textContent = 'Measurements could not refresh. Reload this run or retry.'; }
  }
  function transferMetrics() {
    const resources = performance.getEntriesByType('resource');
    const page = performance.getEntriesByType('navigation')[0];
    const initial = (page ? page.transferSize : 0) + resources.filter(r => initialResources.has(r.name) && !r.name.includes('/engineering/assets/')).reduce((s,r) => s + r.transferSize, 0);
    const lazy = resources.filter(r => r.name.includes('/engineering/assets/')).reduce((s,r) => s + r.transferSize, 0);
    const modelTransfer = workerTransferBytes === null ? 'not loaded' : `${(workerTransferBytes / 1024).toFixed(1)} KiB`;
    byId('transfer-metrics').textContent = `Observed transfer: ${(initial / 1024).toFixed(1)} KiB initial page; ${(lazy / 1024).toFixed(1)} KiB lazy worker script; ${modelTransfer} worker model/runtime requests. Browser Resource Timing includes response overhead; cache hits can transfer zero bytes. Model load timing includes a warm-up inference.`;
  }
  document.querySelector('[data-model-controls]').hidden = false;
  document.querySelector('[data-search-example]').hidden = false;
  byId('refresh-metrics').hidden = false;
  byId('verify-embeddings').hidden = false;
  byId('verify-embeddings').addEventListener('click', async () => {
    const button = byId('verify-embeddings'), output = byId('embedding-agreement-status'), config = byId('embedding-agreement-config');
    button.disabled = true; output.textContent = 'Comparing three public golden sentences with the offline q8 encoder…';
    try {
      const response = await fetch(config.dataset.goldenUrl, { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error();
      const goldens = await response.json(), { compareEmbedding, compareRanking } = await import(config.dataset.moduleUrl);
      const checks = [], rankings = [];
      for (const golden of goldens.goldens) {
        const actual = await embed(golden.text);
        checks.push(compareEmbedding(actual.values, golden.vector, goldens.tolerance));
        rankings.push(compareRanking(actual.values, golden.vector, goldens.reference_index));
      }
      output.textContent = `${checks.every(c => c.passed) && rankings.every(r => r.passed) ? 'Passed' : 'Failed'} ${checks.filter(c => c.passed).length} / ${checks.length} golden vectors · maximum absolute difference ${Math.max(...checks.map(c => c.maximum_absolute_difference)).toExponential(3)} · minimum cosine ${Math.min(...checks.map(c => c.cosine)).toFixed(6)} · top answer agrees ${rankings.filter(r => r.top_result_agrees).length} / 3; top-five overlap ${rankings.reduce((sum, r) => sum + r.overlap, 0)} / 15. Tolerances: component error ≤ ${goldens.tolerance.maximum_absolute_difference}, cosine ≥ ${goldens.tolerance.minimum_cosine}. Same q8 artifact; offline Node CPU versus browser WASM.`;
    } catch { output.textContent = 'Embedding agreement could not be checked. Load the model and retry; do not claim browser agreement from the offline report alone.'; }
    finally { button.disabled = modelState !== 'ready'; }
  });
  byId('load-model').addEventListener('click', loadModel);
  byId('refresh-metrics').addEventListener('click', refreshMetrics);
  document.querySelector('[data-search-example]').addEventListener('click', () => { input.value = example; input.focus(); loadModel(); });
  document.querySelector('.room-nav a[href="#room-search"]').addEventListener('click', loadModel);
  input.addEventListener('focus', loadModel, { once: true });
  byId('simulate-outage').addEventListener('change', () => modelStatus(byId('simulate-outage').checked ? 'Simulated outage enabled. The next search will use a labelled keyword fallback.' : modelState === 'ready' ? 'Browser model ready.' : 'Keyword search is ready. Load the model when ready.'));
  document.querySelectorAll('.room-diagram a').forEach(link => link.addEventListener('click', () => { const details = byId(link.hash.slice(1)); details.open = true; details.querySelector('summary').focus(); }));
  document.body.addEventListener('htmx:afterSwap', event => { if (event.detail.target && event.detail.target.id === 'lab-state') refreshMetrics(); });
  byId('experimental-semantic').addEventListener('change', () => { byId('load-model').disabled = !semanticAllowed(); if (semanticAllowed()) loadModel(); else modelStatus('Keyword search is the default. Experimental semantic retrieval is off.'); });
  if (!semanticAllowed()) { byId('load-model').disabled = true; modelStatus(featureEnabled ? 'Keyword is the default. Enable the clearly labelled experiment to load and inspect the frozen semantic model.' : 'Semantic retrieval is disabled for this release. Keyword search is immediately available.'); }
  transferMetrics();
}());
