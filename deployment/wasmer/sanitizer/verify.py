"""Compare the actual WASI binary with the current nh3/Ammonia policy."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import nh3

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from posts.sanitizers import (ALLOWED_TAGS, ALLOWED_ATTRIBUTES, ALLOWED_URL_SCHEMES, CLEAN_CONTENT_TAGS)

directory = Path(__file__).resolve().parent
binary = Path(sys.argv[1]) if len(sys.argv) > 1 else directory / 'bin/paradome-sanitizer.wasm'
manifest_path = Path(sys.argv[2]) if len(sys.argv) > 2 else directory / 'manifest.json'
manifest = json.loads(manifest_path.read_bytes())
assert hashlib.sha256(binary.read_bytes()).hexdigest() == manifest['sha256'], 'Binary digest mismatch'
fixtures = json.loads((directory / 'fixtures.json').read_bytes())
for fixture in fixtures:
    expected = nh3.clean(fixture['html'], tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES,
                        url_schemes=ALLOWED_URL_SCHEMES, clean_content_tags=CLEAN_CONTENT_TAGS,
                        link_rel='noopener noreferrer nofollow ugc', strip_comments=True)
    result = subprocess.run(['node', str(directory / 'run-wasi.mjs'), str(binary)],
                            input=fixture['html'].encode(), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=30, check=True)
    assert result.stdout.decode() == expected, 'Sanitizer agreement failed: ' + fixture['id']
print(json.dumps({'fixtures': len(fixtures), 'agreement': 'passed', 'nh3': nh3.__version__,
                  'ammonia': manifest['ammonia'], 'binary_sha256': manifest['sha256']}))
