# Unattended automation

The public site has one cloud publisher and one serialized local publisher.

## Cloud

- `radar-update`: 09:00, 14:00 and 19:00 Beijing time; fetches four sources,
  backfills abstract briefs, tests, builds and pushes.
- `pages-smoke`: runs after a successful update and retries the public homepage,
  archive, RSS, reports and interactive demo until Pages has deployed.
- Pushes retry four times. Generated-HTML conflicts are rebuilt; data conflicts
  fail closed instead of choosing a side silently.

## Local publisher clone

Scheduled tasks must use the dedicated clone:

`C:\Users\Administrator\Projects\cockpit-agent-radar-automation`

The report, full-text review and local-sync scripts share an atomic PID lock.
Busy tasks queue for up to six hours instead of returning a false success.
Stale locks are recovered. Cursor Agent calls make at most two attempts in the
same chat and require an explicit completion sentinel. Push rejection triggers
fetch/rebase/retry.

Beijing schedule:

- 10:30 problem-driven daily report
- 12:00 local report sync
- 20:00 full-text review (at most six canonical papers)

Windows tasks run as `SYSTEM`, while `automation_common.ps1` pins
`USERPROFILE`/`HOME`/`APPDATA` to the dedicated Administrator automation
profile. A live SYSTEM smoke run completed an authenticated Cursor Agent prompt,
so tasks continue while the desktop is locked or the user is signed out.
The machine must still be powered on and have network access; missed starts are
configured to run as soon as the host becomes available.

## Failure semantics

- Lock timeout, network failure, missing sentinel, test failure, non-generated
  merge conflict, push exhaustion and Pages smoke failure all return non-zero.
- Normal no-change/no-high-value work exits zero with an explicit cached,
  research-exhausted, or cost-queued status; infrastructure failures do not.
- Existing local modifications in the publisher clone stop the task so recovery
  data is not overwritten.
- Runtime logs and locks remain ignored by Git.

## Generated-file cleanup

Every site build removes stale item, day and report HTML files that no longer
have a source record, preventing dead pages from accumulating.
