# Studio North month-end dashboard

Open `dashboard.html` in a browser. It is self-contained and works without a
server, external scripts, credentials, or network access. Choose an as-of month,
step forward/back, or play the 24-month observed history. It opens at December 2025 with July 2024 and July 2025 selected for comparison (July 2025 has six observed receipts and six forecast receipts) so the original forecast is visible. The Show observed + forecast button returns to that view. Use Choose joining cohorts to tick multiple cohorts; each gets a stable color on the same trajectory graph. Solid lines show observed results and dashed lines show available forecasts. Three time-series graphs show LTV before CAC, historical CAC and payback by joining cohort; segment mix is available in a separate disclosure. The charts update with the as-of month and keep unobserved values as gaps. The original report PDF
is never edited.

## FAQ 4 policy

This implements the expressly permitted observed-history/latest-forecast fallback
in the pinned release's `docs/companion-slides.md`, FAQ 4 and its notes:

- Each month is rebuilt from dated source records before aggregation.
- Every cohort's retention, revenue, contribution, acquisition-time four-segment
  mix, historical average CAC, observed discounted prefix, and observed payback
  are shown only after the relevant information becomes available.
- A fully observed 12-receipt contribution LTV can be shown in earlier months.
  An incomplete horizon has no historical forecast; its LTV remains blank.
- Saved original model forecasts appear **only at December 2025**. No parameters
  estimated from later observations are presented as earlier forecasts.
- True historical forecasts would require a separate cutoff-specific refit for
  each month. No such refits were performed for this extension. The dashboard
  does not claim otherwise.
- Latest-month reconciliation and an independent physical source-truncation
  check are recorded in `validation.json`.

The earlier-month cutoff is the next month's midnight UTC. Operational records
are strictly earlier; a test finishing exactly at the boundary is available at
that instant, consistent with the report's January 1, 2026 cutoff.

## Definitions

First qualifying positive payment defines acquisition, acquisition month is age
zero, and retention uses paid scheduled subscription periods with original
acquired-customer denominators. Net revenue deducts discounts and refunds;
contribution also deducts recorded variable costs. Cohort LTV is contribution per
original customer over 12 receipts, discounted at 1% monthly with acquisition
receipt discounted at t=1. Net LTV subtracts historical average CAC once. Observed
payback is the first undiscounted cumulative-contribution crossing of historical
CAC, reported as one-based receipt months. The table flags the value basis.

Current iCAC uses the latest completed 31-day acquisition-only test in each cell.
The December recommendation joins those test results to July 2025 operational
value, under the report's additional-customer value-transfer assumption. Earlier
historical recommendation dates cannot be established without as-of forecast
refits. December is the first **evaluable** joint recommendation here, not proof
that no earlier evidence supported it.

Operating contribution is not whole-company profit/cash flow. Fixed costs and
the separate research sample's spending and contribution are outside the
operating ledger. Parameter bands omit renewal noise and future cost/regime risk.

## Rebuild

Use the preserved source release, full SHA:
`0e40ce3cd0b788a3914ca4eb9f90d58ae1b62903` from
<https://github.com/longxiutian/customer-economics-lab>.

Use the lab's frozen Python 3.12 environment, which supplies DuckDB 2.0.0:

```sh
uv sync --project /path/to/pinned-source --frozen
uv run --project /path/to/pinned-source --frozen python build_dashboard.py \
  --source-root /path/to/pinned-source \
  --run-dir /path/to/completed-studio-north-run
```

The completed run must contain the original executive PDF and saved analytical
exports. These personal run artifacts and credentials are deliberately not part
of this source package. The earlier editable handoff contains the run evidence.

`build_dashboard.py` precomputes all snapshots into `data/monthly-snapshots.json`
and embeds them into `dashboard.html` using `src/dashboard.html.in`. No computation
or refitting runs on a month-selection click. `src/01_views.sql` is an unchanged
copy of the canonical SQL from the pinned MIT-licensed release.

## Validation

The builder fails on a reconciliation mismatch. It checks all 300 latest
cohort-age cells against the report exports; all 24 company-month totals;
cohort historical CAC; observed discounted prefixes; mature, observed LTV; and
the original report's unchanged hash. Final forecasts are copied verbatim from
the saved output, not recomputed. It independently truncates all eight raw files
at July 1, 2025 and rebuilds June 2025, requiring an identical snapshot.

## Source repository and checks

Source repository: <https://github.com/davidlapasha/MCD-Dashboard>.

The Python builder is `build_dashboard.py`; its raw-record cutoff and
reconciliation checks are part of the build. The complete offline dashboard,
source template, canonical SQL and precomputed monthly snapshots are included.
No credentials, private instructor feedback, usage/debrief logs, or personal
account configuration are included.

Run the dashboard control checks with Node.js 20 or newer:

```sh
node tests/check_dashboard.cjs
```

The checks cover all 24 month states, multi-cohort selection, measure changes,
play/pause, default observed-plus-forecast display, missing values and forecast
visibility. They do not substitute for a browser-rendering test; Chromium
launch was blocked by the authoring environment's macOS sandbox.

## Download the complete source tree

`dashboard-source.zip` contains the complete folder hierarchy, including the
Python builder, source template, canonical SQL, all monthly snapshots and control
tests. Extract it to inspect or run the tests. The root Python builder can also
read its SQL and template directly from that ZIP, so keep `dashboard-source.zip`
beside `build_dashboard.py` when using the root-level builder.

To run the included control checks after extraction:

```sh
node studio-north-dashboard/tests/check_dashboard.cjs
```
