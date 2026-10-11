/* Contracts that affect privacy, opt-in loading, and recovery. Real browser QA
 * verifies inference, focus, layout, and accessibility separately. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor(tag = 'div') { this.tag = tag; this.children = []; this.listeners = {}; this.textContent = ''; this.dataset = {}; this.checked = false; this.disabled = false; this.hidden = true; this.value = ''; }
  set innerHTML(_) { throw Error('Untrusted results must never become HTML'); }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  async fire(name) { return this.listeners[name]?.({ preventDefault() {}, detail: {} }); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this[name] = value; }
  removeAttribute(name) { delete this[name]; }
  focus() { this.focused = true; }
  querySelector() { return { value: 'csrf-fixture' }; }
  requestSubmit() { this.standardSubmissions = (this.standardSubmissions || 0) + 1; }
}
function harness({ gatePassed = false } = {}) {
  const elements = new Map(), selectors = new Map(), workers = [], requests = [], timers = new Map();
  const byId = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  const selector = key => { if (!selectors.has(key)) selectors.set(key, new Element()); return selectors.get(key); };
  byId('room-search').dataset = { semanticEnabled: 'true', gatePassed: String(gatePassed), workerUrl: '/engineering/assets/worker.mjs', searchUrl: '/search/', metricsUrl: '/metrics/' };
  const contract = { dimension: 384, revision: 'pinned', dtype: 'q8' };
  byId('search-contract').textContent = JSON.stringify(contract);
  byId('search-text').value = 'Public discussion query';
  byId('verify-embeddings').disabled = true;
  class Worker {
    constructor(url, options) { this.url = url; this.options = options; this.messages = []; workers.push(this); }
    postMessage(message) { this.messages.push(message); }
    terminate() { this.terminated = true; }
    emit(data) { this.onmessage({ data }); }
  }
  const result = { experimental: false, notice: 'Keyword results', semantic_assessment: { estimated_relevance: null }, timings: { server_ranking_ms: 1 }, results: [{ id: 'discussion-001-a', title: '<img src=x onerror=alert(1)>', text: '<script>public fixture</script>', score: 1, score_kind: 'bm25', confidence: null }] };
  const latency = { count: 0, median_ms: null, p95_ms: null };
  const metrics = { window: { retained: 1, maximum: 40 }, search: { semantic: 0, keyword: 1, low_confidence: 0, assessed: 0, fallbacks: {}, score_distribution: [] }, delivery: { attempts: 0, inbox_effects: 0, duplicate_preventions_in_trace_window: 0, replays_in_trace_window: 0, submissions: 0 }, latency: { server_ranking: latency, browser_embedding: latency, browser_model_load: latency }, artifact: { index_version: 'fixture', healthy: true, documents: 120 } };
  const fetch = async (url, options) => { requests.push({ url, options }); if (state.networkFailed) throw Error('Network unavailable'); return { ok: true, json: async () => url === '/metrics/' ? metrics : result }; };
  const state = { networkFailed: false };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, 'static/engineering/control-room.js'), 'utf8'), {
    document: { getElementById: byId, createElement: tag => new Element(tag), querySelector: selector, querySelectorAll: () => [], body: new Element('body') },
    performance: { now: () => 10, getEntriesByType: () => [] }, Worker, fetch, location: {}, AbortSignal,
    setTimeout: (callback, delay) => { const id = timers.size + 1; timers.set(id, { callback, delay }); return id; }, clearTimeout: id => timers.delete(id),
  });
  async function enable() { byId('experimental-semantic').checked = true; await byId('experimental-semantic').fire('change'); workers.at(-1).emit({ type: 'ready', model_load_ms: 50, observed_transfer_bytes: 1000 }); }
  return { byId, workers, requests, timers, contract, enable, state };
}
test('failed gate sends no embedding and downloads no model', async () => {
  const h = harness();
  assert.equal(h.workers.length, 0);
  await h.byId('search-form').fire('submit');
  const body = JSON.parse(h.requests[0].options.body);
  assert.equal(body.embedding, null);
  assert.equal(body.experimental, false);
  assert.equal(body.fallback, 'evaluation_gate');
  assert.equal(h.requests[0].options.headers['X-CSRFToken'], 'csrf-fixture');
  assert.equal(h.requests[0].options.credentials, 'same-origin');
  assert.equal(h.byId('search-submit').disabled, false);
  assert.equal(h.byId('search-results').children[0].children[0].textContent, '<img src=x onerror=alert(1)>');
});
test('passed gate loads only when Search opens and uses semantic retrieval without opt-in', async () => {
  const h = harness({ gatePassed: true });
  assert.equal(h.workers.length, 0);
  await h.byId('search-form').fire('submit');
  assert.equal(JSON.parse(h.requests[0].options.body).fallback, 'model_loading');
  assert.equal(h.workers.length, 0);
  const loading = h.byId('search-text').fire('focus');
  assert.equal(h.workers.length, 1);
  h.workers[0].emit({ type: 'ready', model_load_ms: 50, observed_transfer_bytes: 1000 });
  await loading;
  const search = h.byId('search-form').fire('submit');
  const message = h.workers[0].messages.at(-1);
  h.workers[0].emit({ type: 'embedding', id: message.id, values: Array(384).fill(0.1), embedding_ms: 12 });
  await search;
  const body = JSON.parse(h.requests.findLast(r => r.url === '/search/').options.body);
  assert.equal(body.experimental, false);
  assert.equal(body.embedding.values.length, 384);
});
test('opt-in creates a module worker and posts a versioned embedding', async () => {
  const h = harness(); await h.enable();
  assert.equal(h.workers.length, 1);
  assert.equal(h.workers[0].options.type, 'module');
  const search = h.byId('search-form').fire('submit');
  const message = h.workers[0].messages.at(-1);
  h.workers[0].emit({ type: 'embedding', id: message.id, values: Array(384).fill(0.1), embedding_ms: 12 });
  await search;
  const body = JSON.parse(h.requests[0].options.body);
  assert.equal(body.embedding.revision, 'pinned');
  assert.equal(body.embedding.values.length, 384);
  assert.equal(body.experimental, true);
  assert.equal(body.browser.embedding_ms, 12);
});
test('worker failure during inference falls back and releases pending UI', async () => {
  const h = harness(); await h.enable();
  const search = h.byId('search-form').fire('submit');
  h.workers[0].emit({ type: 'error', reason: 'model_unavailable' });
  await search;
  assert.equal(JSON.parse(h.requests[0].options.body).fallback, 'model_unavailable');
  assert.equal(h.byId('verify-embeddings').disabled, true);
  assert.equal(h.byId('search-submit').disabled, false);
  assert.equal(h.timers.size, 0);
});
test('controlled outage never runs inference even when the model is ready', async () => {
  const h = harness(); await h.enable(); h.byId('simulate-outage').checked = true;
  await h.byId('search-form').fire('submit');
  assert.equal(h.workers[0].messages.filter(m => m.type === 'embed').length, 0);
  assert.equal(JSON.parse(h.requests[0].options.body).fallback, 'model_unavailable_demo');
});
test('an inference timeout preserves the query and permits keyword recovery', async () => {
  const h = harness(); await h.enable(); const value = h.byId('search-text').value;
  const search = h.byId('search-form').fire('submit');
  [...h.timers.values()].find(timer => timer.delay === 20000).callback();
  await search;
  assert.equal(h.byId('search-text').value, value);
  assert.equal(JSON.parse(h.requests[0].options.body).embedding, null);
  assert.equal(h.workers[0].terminated, true);
});
test('network failure offers an explicit standard form retry, preserving text', async () => {
  const h = harness(); h.state.networkFailed = true; const value = h.byId('search-text').value;
  await h.byId('search-form').fire('submit');
  const recovery = h.byId('search-results').children[0];
  assert.equal(recovery.textContent, 'Use standard keyword form');
  await recovery.fire('click');
  assert.equal(h.byId('search-form').standardSubmissions, 1);
  assert.equal(h.byId('search-text').value, value);
});
test('golden comparison rejects malformed or divergent vectors', async () => {
  const { compareEmbedding } = await import('./static/engineering/embedding-agreement.js');
  const expected = Array(384).fill(0); expected[0] = 1;
  const tolerance = { maximum_absolute_difference: .001, minimum_cosine: .999 };
  assert.equal(compareEmbedding(expected, expected, tolerance).passed, true);
  const divergent = expected.slice(); divergent[1] = .1;
  assert.equal(compareEmbedding(divergent, expected, tolerance).passed, false);
  for (const invalid of [[], Array(384).fill(NaN), Array(384).fill(Infinity)]) assert.equal(compareEmbedding(invalid, expected, tolerance).passed, false);
});
