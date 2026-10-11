import { env, AutoModel, BertTokenizer, FeatureExtractionPipeline } from '@huggingface/transformers';

let encoder, loading, base, manifest, tokenizerJSON, tokenizerConfig, loadMs = null;
env.allowRemoteModels = false;
env.allowLocalModels = true;
env.useBrowserCache = true;
env.useFSCache = false;
env.useWasmCache = false; // Native HTTP cache; avoid runtime blob imports under CSP.
env.backends.onnx.wasm.numThreads = 1;
env.backends.onnx.wasm.proxy = false;
const verify = async () => {
  manifest = await (await fetch(new URL('manifest.json', base))).json();
  if (manifest.revision !== '751bff37182d3f1213fa05d7196b954e230abad9' || manifest.transformers !== '4.3.1') throw new Error('Artifact mismatch');
  // Verify the exact q8 artifact/tokenizer before inference. Browser HTTP caching
  // avoids an additional transfer when the runtime reads these same URLs.
  for (const name of ['model/onnx/model_quantized.onnx', 'model/tokenizer.json', 'model/tokenizer_config.json']) {
    const response = await fetch(new URL(name, base));
    if (!response.ok) throw new Error('Model asset unavailable');
    const bytes = await response.arrayBuffer();
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), v => v.toString(16).padStart(2, '0')).join('');
    if (digest !== manifest.assets[name].sha256) throw new Error('Model checksum mismatch');
    if (name === 'model/tokenizer.json') tokenizerJSON = JSON.parse(new TextDecoder().decode(bytes));
    if (name === 'model/tokenizer_config.json') tokenizerConfig = JSON.parse(new TextDecoder().decode(bytes));
  }
};
async function load() {
  if (!loading) loading = (async () => {
    const started = performance.now();
    base = new URL('./', import.meta.url);
    env.localModelPath = base.href;
    env.backends.onnx.wasm.wasmPaths = { mjs: new URL('runtime/ort-wasm-simd-threaded.jsep.mjs', base).href, wasm: new URL('runtime/ort-wasm-simd-threaded.jsep.wasm', base).href };
    await verify();
    // v4 pipeline discovery skips HTTP local-model metadata with remote access
    // disabled. Construct the public pipeline explicitly, keeping all loads local.
    if (!['BertTokenizer', 'BertTokenizerFast'].includes(tokenizerConfig.tokenizer_class)) throw new Error('Tokenizer mismatch');
    const tokenizer = new BertTokenizer(tokenizerJSON, tokenizerConfig);
    const model = await AutoModel.from_pretrained('model', { dtype: 'q8', device: 'wasm', local_files_only: true });
    encoder = new FeatureExtractionPipeline({ task: 'feature-extraction', tokenizer, model });
    await encoder('Public discussion.', { pooling: 'mean', normalize: true });
    loadMs = performance.now() - started;
    const transfers = performance.getEntriesByType('resource').reduce((sum, entry) => sum + entry.transferSize, 0);
    self.postMessage({ type: 'ready', model_load_ms: loadMs, observed_transfer_bytes: transfers });
  })();
  return loading;
}
self.onmessage = async ({ data }) => {
  try {
    await load();
    if (data.type === 'load') return;
    if (data.type === 'embed' && typeof data.text === 'string' && data.text.length <= 240) {
      const started = performance.now();
      const output = await encoder(data.text, { pooling: 'mean', normalize: true });
      self.postMessage({ type: 'embedding', id: data.id, values: Array.from(output.data), embedding_ms: performance.now() - started, model_load_ms: loadMs });
    }
  } catch {
    self.postMessage({ type: 'error', id: data.id, reason: 'model_unavailable' });
  }
};
