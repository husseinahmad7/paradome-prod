# Wasmer independent demo — PostgreSQL compatibility work

Checked 2026-10-10. The authenticated deployment environment used the supplied
Windows user-level `WASMER_TOKEN` for namespace `h7osanna_xyc`. The intended new
app was `paradome-control-room-preview`; the existing Teledome app was preserved.
The preview has **no released application version or verified public URL**.

## Observed blockers in the original MySQL attempts

Wasmer Git autobuild used Anybuild 0.33.0, Python 3.13, and the `wasix_wasm32`
target. Its normal pipeline resolves binary target wheels from PyPI and
`https://python-registry.wasix.org/simple` before packaging the full application.

| Dependency | Application pin | Wasmer registry availability |
| --- | --- | --- |
| mysqlclient | 2.2.8 | 2.2.7+wasix.1, .2, .3 |
| nh3 | 0.3.7 | 0.3.2+wasix.1, .2 |
| Pillow | 12.3.0 | 12.3.0+wasix.1, .2, .3 |

The third build reached target dependency resolution and failed with no matching
distribution for mysqlclient 2.2.8. A separate non-mutating pip target-resolution
probe also failed for nh3 0.3.7. Registry listings confirmed the available wheels.

The sanitizer stays at its current version. nh3 0.3.7 updates Ammonia through
4.1.4; Ammonia's intervening changelog includes mutation-XSS and SVG fixes.
Using the older vendor build would require verifying its source and backports,
not simply relaxing the pin. See [nh3's release](https://github.com/messense/nh3/releases/tag/v0.3.7)
and [Ammonia's changelog](https://github.com/rust-ammonia/ammonia/blob/master/CHANGELOG.md).
The missing target wheels must be supplied or reproducibly built and verified
before the full deployment can proceed.

## Build evidence

| Build ID | Source | Result |
| --- | --- | --- |
| c7ef353a-67d8-42de-9a2f-6f407b2df57e | c1753f397974007045eea89d528f71bbf39fa4a3 | Custom install step could not access requirements-wasmer.txt |
| 0c168fa2-6e9d-4fba-a646-9036ceaa11bd | 63d520ea2a80d77649f22b8d2c5b632db1c019e6 | Custom first install step could not access requirements.txt |
| 8ab0e35a-a975-443b-abd6-7684e968b80a | 8f6fb959f5f6c44f78749c83258c1554c7e26a91 | Standard target resolver: mysqlclient 2.2.8 unavailable; status FAILED, appVersion null |

Provider source confirmed that dependency inputs are bind-mounted only into the
steps that require them. The deployment helper now keeps the default install
pipeline and adds exact server/database pins through
`ANYBUILD_PYTHON_EXTRA_DEPENDENCIES`. See
[Anybuild's Python provider](https://github.com/wasmerio/anybuild/blob/main/crates/anybuild/resources/starlib/tools/python.bzl).
This fixes the install-layer configuration; it does not fix missing wheels.

Account preflight showed no near-limit flags before each build. No paid service,
custom domain, SMTP, or Pusher credential was configured. Deployment tokens are
never application settings or source files. The demo Django secret is stored as
a provider secret; the local recovery backup uses Windows DPAPI in ignored cache.

## Implemented deployment profile

- `paradome.settings.wasmer` requires a production secret, exact HTTPS hosts and
  origins, Wasmer's injected `DB_USERNAME`, managed PostgreSQL behavior,
  active DB TLS, secure sessions, and a private persistent path under `/data`.
- The root `app.yaml` requests managed PostgreSQL, `fr-roub1`, a `/data` private-media
  volume, HTTPS, and CDN support. It is an initial compatibility preview manifest.
- `deployment/wasmer/build.py` uses the same nine model/runtime asset hashes as
  the Node builder and collects static assets with a secret-free build profile.
  A local fresh-download check reproduced the Node runtime/worker digests.
- `wasmer_compatibility` checks native imports, sanitization, image encoding,
  DB access/TLS, and a private-volume round trip in the real runtime.
- `prepare_wasmer_demo` migrates, creates the shared cache table, runs the runtime
  probe, and seeds the independent `paradome-wasmer-guest` sandbox if missing.

## PostgreSQL continuation — 2026-10-10

The user authorized a database change for the independent demo. Wasmer's current
[configuration documentation](https://docs.wasmer.io/edge/configuration/) and
authenticated API both support `POSTGRES`; current target wheels include
`psycopg-binary==3.3.4`. The new preview name is
`paradome-control-room-pg-preview`. An existing database's engine cannot be
changed in place, so no existing Teledome database is altered or deleted.

The Wasmer settings, manifest, runtime TLS check and driver requirements now
select PostgreSQL. CI runs the complete suite and row-lock/concurrency tests
against both MySQL and PostgreSQL. The conventional production profile retains
MySQL and nh3 0.3.7.

The sanitizer candidate compiles Ammonia 4.1.4 with the existing narrow HTML5
allowlist into a WASI executable. Its fixed path, SHA-256 manifest, bounded
stdin, timeout and fail-closed errors replace the unavailable nh3 native binding
only in Wasmer. Rich text is not disabled or passed through unsanitized. Native
nh3 versus actual WASI agreement and real WASIX subprocess execution are gates;
the code's existence does not establish that these checks passed.

`prepare_source.py` creates a full-application release branch using an isolated
Git index. Only root `requirements.txt` selects the Wasmer profile; all other
source stays at the supplied primary revision. Anybuild's normal dependency
steps can then bind all recursively referenced requirement files. This avoids
the previously broken custom first install step and preserves every checkout.

The PostgreSQL preview is still a compatibility candidate. No new verified
public URL, restart-persistence check or rollback result is claimed yet.
- `maintain_demo_sandbox` uses a database lease and one reset per UTC day, with
  bounded cleanup of expired runs, sessions, and rate-limit buckets.
- The public manifest template includes preparation and midnight-UTC jobs.
  Their package command mapping and actual execution remain unverified; they
  have not been enabled in the initial preview manifest.
- Contact uses email links and chat uses explicit refresh. Session pages send
  `no-store`; model assets use immutable caching, ETag, HEAD, and 304 responses.

## Retry and release

From an activated environment, after resolving the target-wheel blocker:

```sh
python deployment/wasmer/deploy.py preflight
python deployment/wasmer/deploy.py preview --revision <full-pushed-git-sha>
python deployment/wasmer/deploy.py status --build-id <returned-build-id>
```

The preview keeps the new control room and semantic flags off for baseline
compatibility verification. `--features` enables them in a later version;
`--app-id` targets the verified independent app while retaining its secret.
The helper reads `WASMER_TOKEN` from the process environment, or Windows User
environment when needed. It validates the namespace and free allowance headroom.

Before enabling jobs or promoting the demo, verify dependency installation,
native sanitization/codecs, managed MySQL/migrations, sessions/static, protected
media authorization, private-volume persistence across restart, bounded cleanup,
and health. Confirm the generated package's Python command and `/app` mapping,
then render the public manifest with exact hosts/origins and the immutable source
revision. Credentials belong in provider secrets.

Retain the baseline version and rehearse restoring it with the additions disabled
while retaining the additive search/lease tables. Verify health and the same
session/private-media records after restoration. No baseline application version
exists yet, so rollback, persistence, cleanup jobs, and promotion have not been
rehearsed. Publish the portfolio demo link only after all these gates and the
remaining [browser verification](control-room-verification.md) pass.
