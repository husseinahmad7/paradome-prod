# Wasmer rich-text sanitizer

The released executable is built from Ammonia **4.1.4** and the locked Rust
dependencies, using Rust **1.98.1** targeting `wasm32-wasip1`. It preserves the
application's HTML5 allowlist and rejects active content and unsafe URL schemes.
The normal application profile continues to use nh3 0.3.7.

`bin/paradome-sanitizer.wasm` and `manifest.json` come from the successful
`sanitizer` job in [CI run 38126589220](https://github.com/husseinahmad7/paradome-prod/actions/runs/38126589220),
source revision `8e239315c52aff8ad0432ba2bb50a5421cea5a8a`.
The downloaded archive SHA-256 is
`7fbec564219f7b125b3f875602b9101da3415ef8e9a4ef6b2aed12958cb68a9f`.
The executable digest, compiler, source digest and lockfile digest are recorded
in its manifest. CI reproduces that exact manifest before running the fixtures.

To reproduce on Linux, use the pinned toolchain and the two path remappings in
`.github/workflows/ci.yml`, then run `freeze.py` and `verify.py`. The freezer
refuses a different binary or manifest. Verification executes the real WASI
binary under Node's WASI runtime and compares it with native nh3 on all 18 HTML
fixtures; no output is mocked.

Production invokes the fixed executable directly under WASIX Python, checks
its SHA-256, limits input and output, and fails closed on execution errors.
Node is used only for independent fixture verification. Actual Wasmer subprocess
execution remains a deployment gate until the preview passes it.
