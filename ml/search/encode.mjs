/** No production ML dependency: encode the fixed public benchmark offline. */
import { pipeline, env } from '@huggingface/transformers';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { performance } from 'node:perf_hooks';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const version = process.argv[2] || 'v1';
if (!['v1', 'v2'].includes(version)) throw new Error('Use a named frozen experiment: v1 or v2');
env.allowRemoteModels = false;
env.allowLocalModels = true;
env.useFSCache = false;
const model = resolve(root, 'engineering/static/engineering/search-assets/minilm-q8-v1/model');
const loadStarted = performance.now();
const encoder = await pipeline('feature-extraction', model, { dtype: 'q8', device: 'cpu' });
const modelLoadMs = performance.now() - loadStarted;
const documents = JSON.parse(await readFile(resolve(root, `ml/search/data/corpus-${version}.json`), 'utf8')).documents;
const queries = JSON.parse(await readFile(resolve(root, `ml/search/data/queries-${version}.json`), 'utf8')).queries;
const encode = async text => {
  const started = performance.now();
  const output = await encoder(text, { pooling: 'mean', normalize: true });
  if (output.data.length !== 384) throw new Error('Unexpected encoder dimension');
  return { vector: Array.from(output.data, v => Number(v.toFixed(8))), duration_ms: performance.now() - started };
};
const encodedDocs = [], encodedQueries = [];
for (const [i, doc] of documents.entries()) {
  encodedDocs.push({ id: doc.id, ...await encode(doc.title + '\n' + doc.text) });
  if ((i + 1) % 30 === 0) console.log(`Encoded ${i + 1}/120 documents`);
}
for (const [i, query] of queries.entries()) {
  encodedQueries.push({ id: query.id, ...await encode(query.text) });
  if ((i + 1) % 45 === 0) console.log(`Encoded ${i + 1}/180 queries`);
}
const goldenTexts = ['The recipient got my message but the sender never heard back. How can I safely send it again?', 'The export button fails after choosing dates.', 'Quantum ion spectroscopy is outside this public corpus.'];
const goldens = [];
for (const text of goldenTexts) goldens.push({ text, ...await encode(text) });
await writeFile(resolve(root, `ml/search/encoded-${version}.json`), JSON.stringify({ runtime: 'Transformers.js 4.3.1 / ONNX Runtime Node CPU, q8 artifact', model_load_ms: modelLoadMs, documents: encodedDocs, queries: encodedQueries, goldens }) + '\n');
console.log('Encoded benchmark; test outcomes have not been inspected or used.');
await encoder.dispose();
