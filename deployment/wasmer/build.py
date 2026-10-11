"""Run inside the provider's Python build after installing all requirements.

Fetch hash-locked runtime assets and assemble the local worker source.
Deployment migrations are a separate job with provider-injected DB credentials.
"""
import os
from pathlib import Path
import subprocess
import sys
from assets import assemble

root = Path(__file__).resolve().parents[2]
os.environ["DJANGO_SETTINGS_MODULE"] = "paradome.settings.build"
asset_root = root / "engineering/static/engineering/search-assets/minilm-q8-v1"
assemble(root)
subprocess.run([sys.executable, root / "manage.py", "check"], cwd=root, check=True)
subprocess.run([sys.executable, root / "manage.py", "collectstatic", "--noinput", "--ignore=engineering/search-assets/*"], cwd=root, check=True)
print("Package source, static_files and original search-assets; never .env, .cache, node_modules, uploads or local databases.")
