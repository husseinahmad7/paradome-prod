/** Pinned downloads; a checked-in digest lock makes rebuilding fail closed. */
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile, copyFile } from 'node:fs/promises';
import { resolve, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const out = resolve(root, 'engineering/static/engineering/search-assets/minilm-q8-v1');
const revision = '751bff37182d3f1213fa05d7196b954e230abad9';
const files = ['config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', 'onnx/model_quantized.onnx'];
await mkdir(out, { recursive: true });
for (const name of files) {
  const target = resolve(out, 'model', name);
  await mkdir(dirname(target), { recursive: true });
  let present = false;
  try { await readFile(target); present = true; } catch {}
  if (!present) {
    const response = await fetch(`https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/${revision}/${name}`, { signal: AbortSignal.timeout(180000) });
    if (!response.ok) throw new Error(`Pinned model download failed: ${name} (${response.status})`);
    await writeFile(target, Buffer.from(await response.arrayBuffer()));
  }
}
await mkdir(resolve(out, 'runtime'), { recursive: true });
for (const name of ['ort-wasm-simd-threaded.jsep.mjs', 'ort-wasm-simd-threaded.jsep.wasm']) {
  await copyFile(resolve(root, 'node_modules/onnxruntime-web/dist', name), resolve(out, 'runtime', name));
}
await copyFile(resolve(root, 'node_modules/@huggingface/transformers/dist/transformers.min.js'), resolve(out, 'runtime/transformers.min.js'));
const workerSource = (await readFile(resolve(root, 'engineering/static/engineering/search-worker.src.js'), 'utf8')).replace(/\r\n/g, '\n');
await writeFile(resolve(out, 'worker.mjs'), workerSource.replace("from '@huggingface/transformers'", "from './runtime/transformers.min.js'"));
// Offline and browser goldens share the exact ONNX/tokenizer digests.
const assets = {};
for (const name of [...files.map(n => 'model/' + n), 'runtime/ort-wasm-simd-threaded.jsep.mjs', 'runtime/ort-wasm-simd-threaded.jsep.wasm', 'runtime/transformers.min.js', 'worker.mjs']) {
  const bytes = await readFile(resolve(out, name));
  assets[name] = { sha256: createHash('sha256').update(bytes).digest('hex'), bytes: bytes.length };
}
const lockPath = resolve(root, 'ml/search/assets-lock-v1.json');
const manifest = { revision, transformers: '4.3.1', ort: JSON.parse(await readFile(resolve(root, 'node_modules/onnxruntime-web/package.json'), 'utf8')).version, assets };
let old;
try { old = JSON.parse(await readFile(lockPath, 'utf8')); } catch (error) { if (error.code !== 'ENOENT') throw error; }
if (old && JSON.stringify(old) !== JSON.stringify(manifest)) {
  const modelKeys = Object.keys(old.assets).filter(name => name !== 'worker.mjs');
  const workerOnly = process.argv.includes('--refresh-worker') && modelKeys.every(name => JSON.stringify(old.assets[name]) === JSON.stringify(assets[name]));
  const distributionOnly = process.argv.includes('--repackage-runtime') && old.revision === manifest.revision && old.transformers === manifest.transformers && old.ort === manifest.ort && modelKeys.every(name => JSON.stringify(old.assets[name]) === JSON.stringify(assets[name]));
  if (!workerOnly && !distributionOnly) throw new Error('Asset lock mismatch. Review a new artifact version; do not silently rewrite v1.');
}
await writeFile(lockPath, JSON.stringify(manifest, null, 2) + '\n');
if (process.argv.includes('--refresh-worker') || process.argv.includes('--repackage-runtime')) {
  const goldenPath = resolve(root, 'engineering/ml_artifacts/search-golden-v1.json');
  const golden = JSON.parse(await readFile(goldenPath, 'utf8'));
  if (!Object.keys(golden.assets.assets).filter(name => name !== 'worker.mjs').every(name => JSON.stringify(golden.assets.assets[name]) === JSON.stringify(assets[name]))) throw new Error('Golden model/runtime digests changed');
  golden.assets = manifest;
  await writeFile(goldenPath, JSON.stringify(golden, null, 2) + '\n');
}
await writeFile(resolve(out, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`Verified ${Object.keys(assets).length} assets (${Object.values(assets).reduce((s, a) => s + a.bytes, 0)} bytes) in ${relative(root, out)}`);
