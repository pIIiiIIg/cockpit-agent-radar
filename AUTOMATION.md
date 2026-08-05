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
Stale locks are recovered. Cursor Agent calls retry three times and require an
explicit completion sentinel. Push rejection triggers fetch/rebase/retry.

Recommended Beijing schedule:

- 02:00 full-text review
- 10:30 problem-driven daily report
- 12:00 local report sync
- 15:00, 20:00 and 23:00 full-text review

The machine must remain logged into the Administrator account because Cursor
Agent credentials are user-scoped. Locking the desktop is fine; signing out is
not. This is the only host constraint that cannot be removed without a separate
service-account Cursor login.

## Failure semantics

- Lock timeout, network failure, missing sentinel, test failure, non-generated
  merge conflict, push exhaustion and Pages smoke failure all return non-zero.
- A skipped task is never reported as success.
- Existing local modifications in the publisher clone stop the task so recovery
  data is not overwritten.
- Runtime logs and locks remain ignored by Git.

## Generated-file cleanup

Every site build removes stale item, day and report HTML files that no longer
have a source record, preventing dead pages from accumulating.
