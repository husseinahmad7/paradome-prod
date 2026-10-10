"""Bind the release binary to its compiler, locked dependencies and policy."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

directory = Path(__file__).resolve().parent
source = directory / 'target/wasm32-wasip1/release/paradome-sanitizer.wasm'
target = directory / 'bin/paradome-sanitizer.wasm'
target.parent.mkdir(exist_ok=True)
def digest(path, canonical=False):
    content = path.read_bytes()
    return hashlib.sha256(content.replace(b'\r\n', b'\n') if canonical else content).hexdigest()
manifest = {'version': 'sanitizer-wasi-v1', 'policy': 'prose-v1', 'ammonia': '4.1.4',
            'sha256': digest(source), 'bytes': source.stat().st_size,
            'compiler': subprocess.check_output(['rustc', '--version']).decode().strip(),
            'target': 'wasm32-wasip1', 'source_sha256': digest(directory / 'src/main.rs', True),
            'lock_sha256': digest(directory / 'Cargo.lock', True)}
manifest_path = directory / 'manifest.json'
if manifest_path.exists():
    existing = json.loads(manifest_path.read_bytes())
    if manifest != existing:
        raise SystemExit('Sanitizer build does not reproduce the committed manifest; do not replace it silently')
else:
    manifest_path.write_bytes((json.dumps(manifest, indent=2) + '\n').encode())
shutil.copyfile(source, target)
print(json.dumps(manifest))
