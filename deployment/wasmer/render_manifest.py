"""Public configuration only. WASMER_TOKEN stays in the deployment environment."""
import argparse
from pathlib import Path
import re
from urllib.parse import urlsplit


def render(owner, name, package, urls, revision):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", owner) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise ValueError("Use resolved Wasmer account/app slugs")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Pin released source to its full Git revision")
    hosts = []
    for url in urls:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.hostname != parsed.netloc or parsed.path or parsed.query or parsed.fragment or not parsed.hostname.endswith(".wasmer.app"):
            raise ValueError("Use exact Wasmer public/preview HTTPS origins without paths")
        hosts.append(parsed.hostname)
    if not urls or any(char in package for char in '\n\r"'):
        raise ValueError("Provide a validated package and at least one exact origin")
    return Path(__file__).with_name("app.yaml.template").read_text().format(owner=owner, name=name, package=package, hosts=",".join(hosts), origins=",".join(urls), public_url=urls[0], revision=revision)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for field in ("owner", "name", "package", "revision"):
        parser.add_argument("--" + field, required=True)
    parser.add_argument("--origin", action="append", required=True)
    parser.add_argument("--output", type=Path, default=Path("deployment/generated/app.yaml"))
    options = parser.parse_args()
    manifest = render(options.owner, options.name, options.package, options.origin, options.revision)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(manifest, encoding="utf-8")
    print(f"Wrote public configuration to {options.output}; credentials must be provider secrets.")
