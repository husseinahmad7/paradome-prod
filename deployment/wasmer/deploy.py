"""Wasmer registry API deployment; credentials remain in process/provider secrets.

Run preflight first. A preview is a new independent app unless --app-id is given.
No paid plan, custom domain, SMTP or realtime subscription is created here.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]


def token():
    value = os.environ.get("WASMER_TOKEN")
    if not value and os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value = winreg.QueryValueEx(key, "WASMER_TOKEN")[0]
    if not value:
        raise RuntimeError("Set WASMER_TOKEN in the deployment environment")
    return value


def graphql(query, variables=None):
    request = Request("https://registry.wasmer.io/graphql", data=json.dumps({"query": query, "variables": variables or {}}).encode(), headers={"Authorization": "Bearer " + token(), "Content-Type": "application/json", "User-Agent": "ParaDome-full-demo-release"})
    with urlopen(request, timeout=60) as response:
        result = json.load(response)
    if result.get("errors"):
        # Do not echo server messages that might reflect a submitted secret.
        raise RuntimeError("Wasmer rejected the request; inspect its dashboard for diagnostics")
    return result["data"]


def demo_key(name, existing=False):
    configured = os.environ.get("WASMER_DEMO_SECRET_KEY")
    if configured:
        return configured
    if os.name != "nt":
        if existing:
            raise RuntimeError("Supply the existing demo secret through the deployment environment")
        return secrets.token_urlsafe(48)
    # Windows backup is encrypted with the signed-in user's DPAPI identity.
    # No plaintext credential is written to a file or included in a command.
    relative = f".cache/wasmer/{name}.secret.dpapi"
    target = ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    def protect(data, decrypt=False):
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        source, output = Blob(len(data), buffer), Blob()
        library = ctypes.WinDLL("crypt32", use_last_error=True)
        function = library.CryptUnprotectData if decrypt else library.CryptProtectData
        function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        function.restype = wintypes.BOOL
        if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return ctypes.string_at(output.data, output.size)
        finally:
            kernel = ctypes.WinDLL("kernel32")
            kernel.LocalFree.argtypes = [ctypes.c_void_p]
            kernel.LocalFree.restype = ctypes.c_void_p
            kernel.LocalFree(output.data)
    if target.exists():
        return protect(target.read_bytes(), decrypt=True).decode()
    if existing:
        raise RuntimeError("No existing secret backup is available; refuse to rotate the key")
    value = secrets.token_urlsafe(48)
    target.write_bytes(protect(value.encode()))
    return value


def preflight():
    data = graphql('{ viewer { username usageReport { metrics { displayName usedPercent nearingLimits } } } }')["viewer"]
    if not data or not data["usageReport"]:
        raise RuntimeError("Cannot verify authenticated account allowances")
    if any(row["nearingLimits"] or row["usedPercent"] >= 90 for row in data["usageReport"]["metrics"]):
        raise RuntimeError("An account allowance is near its limit; do not deploy automatically")
    print(json.dumps(data, indent=2))
    return data["username"]


def preview(options):
    if preflight() != options.owner:
        raise RuntimeError("Token owner differs from the confirmed demo namespace")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", options.name) or not re.fullmatch(r"[0-9a-f]{40}", options.revision):
        raise ValueError("Use an exact app name and full released Git revision")
    origin = options.origin or f"https://{options.name}.wasmer.app"
    from render_manifest import render
    # Validate exact origins and public configuration without saving any secret.
    render(options.owner, options.name, ".", [origin], options.revision)
    def env(name, value, sensitive=False):
        return {"name": name, "value": value, "sensitive": sensitive, "build": not sensitive, "runtime": True}
    variables = {"input": {
        "repoUrl": "https://github.com/husseinahmad7/paradome-prod",
        "branch": options.branch, "appName": options.name, "owner": options.owner,
        "presetName": "django", "region": "fr-roub1", "enableDatabase": True,
        "dbEngine": "POSTGRES", "waitForScreenshotGeneration": False,
        # Keep Anybuild's install steps: they bind-mount dependency inputs only
        # for the step that needs them and resolve target-runtime wheels.
        "buildCmd": "python deployment/wasmer/build.py",
        "startCmd": "python -m uvicorn paradome.wasmer_wsgi:app --interface wsgi --host 0.0.0.0 --port 8080",
        "afterDeployCmd": "python manage.py prepare_wasmer_demo",
        "envVars": [env("ANYBUILD_PYTHON_EXTRA_DEPENDENCIES", json.dumps(["psycopg[binary]==3.3.4", "uvicorn==0.54.0"])),
                    env("DJANGO_SETTINGS_MODULE", "paradome.settings.wasmer"),
                    env("DJANGO_SECRET_KEY", demo_key(options.name, bool(options.app_id)), True),
                    env("DJANGO_ALLOWED_HOSTS", origin.removeprefix("https://")),
                    env("DJANGO_CSRF_TRUSTED_ORIGINS", origin), env("PUBLIC_SITE_URL", origin),
                    env("PRIVATE_MEDIA_ROOT", "/data/private-media"), env("ENGINEERING_LAB_ENABLED", "true"),
                    env("ENGINEERING_CONTROL_ROOM_ENABLED", "true" if options.features else "false"),
                    env("ENGINEERING_SEMANTIC_ENABLED", "true" if options.features else "false"),
                    env("ENGINEERING_SOURCE_REVISION", options.revision)],
    }}
    if options.app_id:
        # Existing secrets must be supplied explicitly; never rotate a live key
        # while trying to promote a feature-flag change.
        variables["input"].update(appId=options.app_id, allowExistingApp=True)
    result = graphql('mutation($input: DeployViaAutobuildInput!) { deployViaAutobuild(input:$input) { success buildId } }', variables)["deployViaAutobuild"]
    output = ROOT / "deployment/generated/release.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({**result, "app_name": options.name, "owner": options.owner, "source_revision": options.revision, "features": options.features, "expected_origin": origin}, indent=2) + "\n")
    print(json.dumps(result))
    print("Preview build dispatched. Verify it before publishing the demo link.")


def activate(options):
    """Restore a package AND app-scoped flags without reading or rotating secrets."""
    if not options.app_id or not options.version_id or not re.fullmatch(r"[0-9a-f]{40}", options.revision or ""):
        raise ValueError("Activation requires an app ID, retained version ID, and full source revision")
    if preflight() != options.owner:
        raise RuntimeError("Token owner differs from the confirmed demo namespace")
    target = graphql('query($id:ID!){node(id:$id){... on DeployAppVersion{id app{id}}}}', {"id": options.version_id})["node"]
    if not target or target["app"]["id"] != options.app_id:
        raise RuntimeError("Retained version does not belong to the requested app")
    values = {"ENGINEERING_CONTROL_ROOM_ENABLED": "true" if options.features else "false",
              "ENGINEERING_SEMANTIC_ENABLED": "true" if options.features else "false",
              "ENGINEERING_SOURCE_REVISION": options.revision}
    app = graphql('query($id:ID!,$names:[String!]){node(id:$id){... on DeployApp{id envVars(names:$names,first:3){edges{node{id name}}}}}}', {"id": options.app_id, "names": list(values)})["node"]
    existing = {edge["node"]["name"]: edge["node"]["id"] for edge in app["envVars"]["edges"]}
    if set(existing) != set(values):
        raise RuntimeError("Expected release flags are missing; refuse a partial configuration change")
    # Update existing IDs, preserving sensitivity/build/runtime attributes and
    # every other variable. Never retrieve values or resubmit the Django key.
    updated = graphql('mutation($input:UpdateEnvVarsInput!){updateEnvVars(input:$input){success}}', {"input": {"appId": options.app_id, "envVars": [{"id": existing[name], "value": value} for name, value in values.items()]}})["updateEnvVars"]
    if not updated["success"]:
        raise RuntimeError("Release flags were not updated; no version was activated")
    selected = graphql('mutation($input:MarkAppVersionAsActiveInput!){markAppVersionAsActive(input:$input){app{id activeVersion{id}}}}', {"input": {"appVersion": options.version_id}})["markAppVersionAsActive"]["app"]
    if selected["id"] != options.app_id or selected["activeVersion"]["id"] != options.version_id:
        raise RuntimeError("Version selection did not match the requested app")
    # Wasmer environment variables belong to the app. Redeployment applies the
    # restored flags and creates fresh runtime instances of the retained package.
    result = graphql('mutation($input:RedeployActiveAppVersionInput!){redeployActiveAppVersion(input:$input){app{id activeVersion{id}}}}', {"input": {"appId": options.app_id}})["redeployActiveAppVersion"]["app"]
    record = {"app_id": result["id"], "activated_from": options.version_id,
              "active_version": result["activeVersion"]["id"], "source_revision": options.revision,
              "features": options.features}
    output = ROOT / "deployment/generated/activation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))
    print("Activation dispatched. Verify health, feature flags, and the same session before publishing.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["preflight", "preview", "status", "activate"])
    parser.add_argument("--owner", default="h7osanna_xyc")
    parser.add_argument("--name", default="paradome-control-room-pg-preview")
    parser.add_argument("--branch", default="hussein/wasmer-demo")
    parser.add_argument("--revision")
    parser.add_argument("--origin")
    parser.add_argument("--app-id")
    parser.add_argument("--features", action="store_true")
    parser.add_argument("--build-id")
    parser.add_argument("--version-id")
    args = parser.parse_args()
    if args.action == "preflight":
        preflight()
    elif args.action == "preview":
        preview(args)
    elif args.action == "activate":
        activate(args)
    else:
        result = graphql('query($id: UUID!) { autobuildDeploymentStatus(buildId:$id) { status appVersion { id url } } }', {"id": args.build_id})
        print(json.dumps(result))
