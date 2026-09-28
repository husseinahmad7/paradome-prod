---
version: 1
slug: "engineering"
primary_target: "engineering"
related_targets: []
---

# Engineering lab surface

An extension of ParaDome for platform/backend recruiters. The approved plan fixes
the blue/teal identity and the submission → receipt → trace composition. This is
a code-led, functional interface; no generated illustration or new brand system.

## Direction contract

THESIS: Make a delivery failure inspectable, then prove that retrying does not
duplicate its effect. Persisted evidence leads; decoration never stands for data.

OWN-WORLD: Inherit ParaDome's navy navigation, pale blue canvas, white working
surfaces, blue actions, teal success, amber warnings, and visible gold focus rings.
Use the existing system font stack, compact controls, and restrained rounded edges.

STORY: Start a browser-owned run, submit a technical message, lose an acknowledgement,
recover, and replay. Compare source state with the one destination receipt. Explore
hypothetical permissions and the measured, limited English classifier afterward.

FIRST VIEWPORT: A short introduction and start action lead into a horizontal
walkthrough. In a run, a wide source form sits beside the destination inbox;
the execution ledger spans their width below. Mobile preserves that reading order.

FORM: The user-approved workbench composition, fixed by the implementation plan;
no concept seed applies. Signature interaction: each explicit attempt updates the
source, inbox, and trace together. A brief background transition acknowledges the
change; reduced motion removes it and ordinary form navigation stays complete.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

For this established-world extension, preserve incumbent design files; document
the inheritance evidence here. No shipping raster assets are introduced.

## Inheritance and finish record

Recorded 2026-09-27 for the implemented local Engineering Lab. The primary mode
is Operate; architecture explanations and model evidence support the walkthrough.
This is an ordinary extension of the existing visual system. The source remains
the visual authority; this record does not establish a new global design system.
No `DESIGN.md` or `.impeccable/design.json` existed at handoff, and neither is
created by this documentation pass.

### Observed inheritance

`engineering/templates/engineering/base.html` loads
`HusseinAh/static/css/paradome-app.css` before
`engineering/static/engineering/lab.css`. The lab consumes the shared `--pd-*`
properties directly. `HusseinAh/static/css/portfolio.css` remains a separate
incumbent namespace; its values are not replaced by the lab's surface choices.

| Observed part | Source-backed implementation |
| --- | --- |
| Palette | Shared navy navigation (`--pd-ink: #0b1730`), pale canvas (`--pd-canvas: #f3f6fb`), white working surfaces (`--pd-surface: #ffffff`), blue actions (`--pd-blue: #1f57c8`), teal success (`--pd-teal-dark: #075c56` on `--pd-teal-soft: #dff5f1`), and amber warning surfaces (`--pd-amber-soft: #fff2dc`). These remain CSS-source values, not a second token registry. |
| Type | The shared body stack is `Inter, Aptos, "Segoe UI", Roboto, Helvetica, Arial, sans-serif` at 16px with 1.55 line-height. The lab defines its overview heading at `clamp(2.25rem, 4.5vw, 3.6rem)`, run heading at `clamp(2rem, 3.6vw, 2.8rem)`, and ordinary section/item headings at 1.5rem/1.08rem. Code uses a local monospace stack and timing data uses tabular numerals. No font download is added by the lab template. |
| Layout | A 1160px maximum content width uses 48px total outer space, reduced to 32px below 540px. The source/inbox grid uses 1.25:1 columns and the execution timeline spans both; below 840px it becomes one column in the same source, inbox, timeline order. The walkthrough stacks below 540px. These are lab composition choices. |
| Surfaces and controls | Working panels use white, a 1px shared line color, and the shared 14px radius. Buttons use the shared 10px radius; fields use 8px corners. Buttons/fields have a 46px minimum height and navigation/action links use 44px. Panels do not add a shadow recipe; the inherited skip link still uses the shared shadow. |
| Focus | The lab uses a 3px dark-gold outline (`#895700`) with 4px offset on light surfaces and the shared gold (`--pd-focus: #f2ad2e`) in the navy header. Native forms, selects, details, and the skip link remain the underlying controls. |

The source, destination receipt, and timeline are server-rendered in
`engineering/templates/engineering/_state.html`. The operation template retains
ordinary form submissions while `engineering/static/engineering/lab.js` enhances
updates. These observations describe this surface; they do not promote its
composition, type sizes, or motion into rules for unrelated pages.

### Finish disposition and evidence

The independent finish review's final disposition was **ship for the three
previously scored corrections**. This is not blanket approval of every surface,
the complete application, or a production release.

| Reviewed correction | Recorded result |
| --- | --- |
| Successful update focus | A new submission focuses its saved-operation heading. Delivery focuses the next scenario; recovery/replay focuses the replay button within the fresh operation. Validation and request errors retain intentional status-notice focus. |
| Native select readability | Short scenario labels fit the narrow layout. Full explanations wrap below the select and are associated through `aria-describedby`; selecting a scenario alone performs no action. |
| State-change cue | The updated operation receives a 360ms background-only cue. Real animation start/end events were recorded; reduced motion resolves to `animation-name: none` with zero active animations. |

The retained evidence is `docs/engineering-browser-verification.md` and
`.gstack/engineering-browser-results/final.json`. The final result records no
horizontal overflow for overview, run, recovered, and permissions at 320, 390,
768, and 1440 CSS pixels; zero automated accessibility violations in the four
final checked states; and no uncaught page or console errors. The local recovery
and replay confirmation retained one operation and one receipt, including the
ordinary-form path with JavaScript disabled.

Final screenshots are retained under `.impeccable/review/` as
`overview-{320,390,768,1440}.png`, `run-{320,390,768,1440}.png`,
`recovered-{320,390,768,1440}.png`, `permissions-{320,390,768,1440}.png`,
`focus-lost-ack-390.png`, and `focus-recovered-390.png`. They are review evidence,
not shipping assets. This documentation handoff inspected the source, evidence
report, structured results, and screenshot inventory; it did not repeat the
browser run, detector, or finish review.

The evidence concerns the isolated local preview. It does not establish native
browser-menu zoom, screen-reader behavior, production performance, a live
PythonAnywhere deployment, or published source-link validity. Those limits and
release gates remain in the verification report.

### Preserved boundaries and deferred drift

The existing hero, blue/teal palette, section/navigation order, employment dates,
and pre-existing uncommitted portfolio edits remain preservation constraints.
This handoff changes only the two surface records. It introduces no shipping
raster, so there is no new raster provenance record to supply; the base template
continues to reference the existing site icon.

`PRODUCT.md` still uses its legacy `## Register` metadata. That known drift is
explicitly deferred and is not repaired here. Present system-derived heading
styles and the decorative start-button arrow are observed implementation details,
not newly canonized global design rules or additional findings resolved by the
three-correction finish verdict.

### Focused UX refinement — 2026-09-28

The overview now keeps its three-step story visible while the privacy boundary,
six architecture decisions, and full model evaluation use named native
disclosures. The run starts with source/inbox/timeline jump links, retains the
source → inbox → trace reading order, and shows the ML category and qualified
model score outside optional details. Result and error messages use a
dismissible, non-modal native dialog; ordinary forms and dismissal work without
JavaScript. Reset now confirms that the replacement run is ready.

In the isolated local Edge pass, the 390px overview measured 2,326px high
(previous screenshot: 4,784px) and the submitted run 2,616px (previous:
3,843px). The source panel began 419px below the viewport top. At 320, 390,
768, and 1440px there was no horizontal overflow. Automated WCAG checks
reported zero violations for overview, submitted, and conflict states; keyboard
disclosure, native toast dismissal, no-JavaScript submission/dismissal, and
reset feedback passed. These are local-browser checks, not a native
screen-reader audit or production release claim. The Impeccable detector
returned no findings, with a known limitation: it could not resolve Django
`{% static %}` stylesheet URLs, so browser checks supplied the visual evidence.
