"""Assemble exact browser assets in a Python-only provider build."""
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


def assemble(root):
    lock = json.loads((root / "ml/search/assets-lock-v1.json").read_text())
    destination = root / "engineering/static/engineering/search-assets/minilm-q8-v1"
    for name, expected in lock["assets"].items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file() and target.stat().st_size == expected["bytes"] and hashlib.sha256(target.read_bytes()).hexdigest() == expected["sha256"]:
            continue
        temporary = target.with_suffix(target.suffix + ".download")
        if name == "worker.mjs":
            source = (root / "engineering/static/engineering/search-worker.src.js").read_text()
            temporary.write_text(source.replace("from '@huggingface/transformers'", "from './runtime/transformers.min.js'"), encoding="utf-8", newline="\n")
        else:
            if name.startswith("model/"):
                url = f'https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/{lock["revision"]}/{name[6:]}'
            elif name == "runtime/transformers.min.js":
                url = f'https://cdn.jsdelivr.net/npm/@huggingface/transformers@{lock["transformers"]}/dist/transformers.min.js'
            elif name.startswith("runtime/"):
                url = f'https://cdn.jsdelivr.net/npm/onnxruntime-web@{lock["ort"]}/dist/{name[8:]}'
            else:
                raise ValueError("Unexpected artifact path")
            request = Request(url, headers={"User-Agent": "ParaDome-pinned-build", "Accept-Encoding": "identity"})
            size = 0
            with urlopen(request, timeout=180) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > expected["bytes"]:
                        raise ValueError(f"Oversized artifact: {name}")
                    output.write(chunk)
        if temporary.stat().st_size != expected["bytes"] or hashlib.sha256(temporary.read_bytes()).hexdigest() != expected["sha256"]:
            raise ValueError(f"Artifact digest mismatch: {name}")
        temporary.replace(target)
    (destination / "manifest.json").write_text(json.dumps(lock, indent=2) + "\n")
    print(f'Verified all {len(lock["assets"])} pinned assets for self-hosted browser inference.')
