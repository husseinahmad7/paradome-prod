// Verification runner only. Wasmer's WASIX Python executes the fixed .wasm
// directly; production never shells out to Node or fetches code at runtime.
import { WASI } from 'node:wasi';
import { readFileSync } from 'node:fs';
const wasi = new WASI({ version: 'preview1', args: ['paradome-sanitizer'], env: {}, preopens: {}, returnOnExit: true });
const module = await WebAssembly.compile(readFileSync(process.argv[2]));
const instance = await WebAssembly.instantiate(module, wasi.getImportObject());
process.exitCode = wasi.start(instance) ?? 0;
