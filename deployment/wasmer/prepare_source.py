"""Create the full-app Wasmer dependency overlay without touching any checkout.

Anybuild resolves root requirements.txt before copying the source. A separate
release branch selects requirements-wasmer.txt; all other source files are the
exact supplied primary revision. Previous overlay commits remain in history.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def git(*args, input=None, env=None):
    return subprocess.check_output(["git", *args], cwd=ROOT, input=input, env=env).decode().strip()


def prepare(revision, branch):
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or not re.fullmatch(r"hussein/[a-z0-9-]+", branch):
        raise ValueError("Supply a full source SHA and a hussein/ release branch")
    if git("rev-parse", revision + "^{commit}") != revision:
        raise ValueError("Source revision must resolve locally")
    if git("status", "--porcelain", "--untracked-files=normal"):
        raise RuntimeError("Commit reviewed source changes before preparing a release overlay")
    reference = "refs/heads/" + branch
    result = subprocess.run(["git", "rev-parse", "--verify", reference], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    previous = result.stdout.decode().strip() if result.returncode == 0 else None
    cache = ROOT / ".cache/wasmer"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="release-index-", dir=cache) as directory:
        environment = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index")}
        git("read-tree", revision, env=environment)
        blob = git("hash-object", "-w", "--stdin", input=b"# Full Wasmer application runtime profile.\n-r requirements-wasmer.txt\n")
        git("update-index", "--add", "--cacheinfo", "100644", blob, "requirements.txt", env=environment)
        tree = git("write-tree", env=environment)
        if previous and git("rev-parse", previous + "^{tree}") == tree:
            release = previous
        else:
            parents = ["-p", revision]
            if previous and previous != revision:
                parents += ["-p", previous]
            message = ("Select the full Wasmer PostgreSQL runtime\n\nPrimary source: " + revision + "\n").encode()
            release = git("commit-tree", tree, *parents, input=message)
            git("update-ref", reference, release, previous or "0" * 40)
    metadata = {"source_revision": revision, "deployment_revision": release, "branch": branch,
                "overlay": "requirements.txt selects requirements-wasmer.txt; full application preserved"}
    (cache / "source.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument("--branch", default="hussein/wasmer-demo")
    options = parser.parse_args()
    prepare(options.revision, options.branch)
