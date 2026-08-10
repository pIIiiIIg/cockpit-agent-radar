# Radar cost controls

Radar shares `%LOCALAPPDATA%\CursorCostGovernance\cost-ledger.sqlite3` with
StreamingModelHarness. The local gate is $60 soft / $80 hard per Beijing day.
It is a second line of defense; configure the account-level on-demand spend
limit in Cursor Dashboard. Automation never changes account billing settings.

- Agent-free GitHub fetch/build remains at 09:00, 14:00 and 19:00.
- ProblemDrivenDaily remains at 10:30 and renders a deterministic structured
  report by default (0-Agent). Only an uncovered schema may request one
  budgeted Composer fallback.
- Full-text review runs only at 20:00, defaults to `composer-2.5`, and processes at
  most three canonical papers in one batch. Mirror IDs do not consume another slot.
- Both tasks exit without Agent when their deterministic input hash is unchanged.
- No high-value pending paper means zero review calls.
- Review and optional daily fallback get one attempt each. Harness alone may
  use a same-chat second attempt as a hard-capped continuation.
- Missing configured models fail closed and never fall back to a more expensive
  model.

The 2026-08-10 CLI list confirms `composer-2.5`, `auto`,
`glm-5.2-high` (GLM 5.2), and `glm-5.2-max`. Official effective rates make
standard Composer the cheapest of the requested options:

- Composer 2.5: $0.50/M input, $0.20/M cache read, $2.50/M output.
- Auto Cost: $1.25/M input/cache write, $0.25/M cache read, $6/M output.
  The CLI exposes `auto`, but does not identify the account's Auto optimization
  mode, so the automation does not assume that every `auto` request is Auto Cost.
- GLM 5.2: $1.40/M input, $0.26/M cache read, $4.40/M output. Teams and
  Enterprise add the official $0.25/M Cursor Token Rate to third-party tokens;
  the local rate table conservatively includes it.

Set `RADAR_AGENT_MODEL=glm-5.2-high` to prefer GLM. Any configured model must
first pass both fixed canaries with:

`python scripts/model_canary.py run --agent <cursor-agent> --workspace <repo> --model <id>`

The canaries validate output schema, exact citation, sentinel and supplied-fact
consistency for one review and one daily-report packet. A missing/failed canary
queues work for manual choice; it never upgrades to xhigh.

Every call reserves before launch and reconciles final Cursor CLI JSON usage.
The CLI probe on 2026-08-10 confirmed input, output, cache-read and cache-write
token fields. If a future CLI omits usage, `actual_usd` remains null and the
conservative reservation remains charged. Prompt text and secrets are never
written to the ledger.

The public `data/cost_status.json` contains aggregates only, including the
number of canonical reviews and Harness candidates queued by daily cost/count
limits.

## Observed Dashboard baseline

The local, uncommitted Cursor Usage Dashboard export for August 4–10 records
$2,537.67, 1.838B tokens and 585 calls. The six complete days averaged
$373.19/day. Reaching $60 therefore requires an 83.9% reduction (6.22x lower);
reaching $80 requires 78.6% (4.66x lower).

`gpt-5.6-sol-medium` was $2,128.99 (83.89%), compared with xhigh at $350.63
(13.82%) and high at $57.90 (2.28%). Cost control must primarily reduce medium
call count and context size and migrate Radar to included Composer; reducing
xhigh alone cannot meet the target.

Historical Dashboard rows mix manual chats/subagents and scheduled automation
and contain no pipeline/stage field. The baseline is valid for total spend but
not exact automation attribution. Future calls are attributable through the
shared ledger's `pipeline` and `stage` columns.

The $80 local gate covers scheduled Harness/Radar calls only. Manual chats and
manually launched subagents are not controlled by the local scheduler, so an
account-level Cursor Dashboard spend limit remains necessary.

The frugal weekly projection reserves one $35 Harness implementation on Monday,
Wednesday and Friday plus one $6 Radar review per day: $147/week or $21/day.
Allowing a $4 schema fallback every day raises the conservative upper projection
to $175/week or $25/day. A Harness retry day can reach $70 plus Radar, but the
shared hard gate stops all new/continuation calls at $80.
