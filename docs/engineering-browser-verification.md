# Engineering lab browser verification

Date: 2026-09-27. Target: the isolated local preview at
`http://127.0.0.1:8017/engineering/`, not production.

## Method and evidence

The in-app browser runtime still failed with the Windows deny-read ACL error.
After explicit user approval for headless browsing, Playwright drove the installed
Microsoft Edge in fresh, isolated browser contexts. No personal browser cookies,
production database, or real delivery transport were used. The gstack standalone
browser did not start; these results are from the working direct driver.

The local QA database is ignored. Machine-readable results and reproduction
scripts are under ignored `.gstack/engineering-browser-results/` and
`.gstack/engineering-browser-*.cjs`. Actual screenshots are under ignored
`.impeccable/review/`; these are review evidence, not shipping image assets.

## Executed checks

| Area | Observed result |
| --- | --- |
| Responsive layout | Overview, saved run, recovered run, and permissions fit at 320, 390, 768, and 1440 CSS pixels with no horizontal overflow. |
| Keyboard and focus | Skip link, keyboard run creation and submission worked. Successful submission focuses its saved heading; delivery focuses the next scenario; recovery/replay focuses replay. Errors intentionally focus the status notice. |
| Delivery and replay | Lost acknowledgement delivers one receipt; recovery acknowledges it; replay retains one submission and one receipt. The trace reports duplicate prevention. |
| JavaScript disabled | Ordinary forms completed failure-before-delivery, lost acknowledgement, recovery, replay, and reset. The replaced run returned 404. Recovery/replay was repeated after the final UI fixes. |
| Session isolation | A separate browser context received 404 for another browser's run. |
| Input and conflict errors | Invalid request key returned 400 with a visible field error. A changed payload under the same key returned 409, focused the error notice, and created no extra submission. |
| Loading and network failure | A pending request exposed the busy state; an aborted request displayed safe recovery/replay guidance. |
| Permission explorer | The fixed demo-own-Dome scenario was allowed; the fixed demo-other-Dome scenario was denied. Full policy parity is covered separately by server tests. |
| Reduced motion | Browser emulation matched the preference; the update highlight computed to `animation-name: none` with no active animations. |
| Reflow | A 720-CSS-pixel viewport at device scale factor 2 checked the 1440-physical-pixel, 200%-equivalent layout without overflow. This is not a headed browser-menu zoom test. |

Axe-core 4.13.0 checked WCAG 2 A/AA, 2.1 A/AA, 2.2 AA, and best-practice rules.
Overview, empty/submitted/recovered runs, permissions, and 400/409 error states
reported **zero violations**, including zero serious/critical findings. The final
confirmation repeated overview, recovered, conflict, and permissions checks with
43, 45, 45, and 38 passing rules respectively. Automated results do not replace
screen-reader or manual assistive-technology testing.

The final browser confirmation had no uncaught page errors or console errors.
Expected 400/409 responses and the deliberately aborted request in earlier
checks are not application crashes.

## Review-driven corrections

1. Successful HTMX swaps no longer jump to a global notice thousands of pixels
   above the next mobile action. Focus is restored inside the fresh operation.
2. Scenario choices use short labels that fit the 320-pixel layout. Their complete
   explanations wrap below the native select.
3. Changed operations receive a 360 ms background-only update cue. Real browser
   animation start/end events were observed; reduced motion disables the cue.

Six dependency-free JavaScript regression tests cover the event contract,
including fresh-versus-detached swap targets and separate error/success focus.
Five Django rendered-form tests passed after these changes.

## Measured transfer

With the browser cache disabled, network `encodedDataLength` totals were:

- Lab overview: **101,837 bytes** (below the 300 KB target).
- Existing homepage: **97,186 bytes** (below the 500 KB budget), including the
  feature-gated Engineering Lab link.

These are local development-server cold transfers, not estimates from source
file sizes and not PythonAnywhere measurements. No new font or raster downloads
were introduced. Production static compression, LCP, and inference latency must
be checked after release; this run does not claim production performance.

## Scope limits

- No native browser-menu zoom or screen-reader session was performed.
- Live PythonAnywhere deployment and published source-link verification remain
  release gates, not browser-test passes.
- A first test harness expected the wrong skip-link hash, tried a new request
  key when checking conflicts, and expected an alert instead of the implemented
  focused live status. Corrected tests passed; those harness failures were not
  treated as application defects.
