# Renewals, overdue reminders and paginated search

Branch `feature/renewals-and-reminders` → `main` · 0.4.0 → 0.5.0

Volunteers asked for three things at the last meeting: renewing a loan at the desk, mailing the members whose books are late, and a search that doesn't stop at 50 results.

## Changes

- **Renewals**: `shelfwise renew <loan>` pushes the due date back by one loan period, counted from the current due date. At most `max_renewals` per loan (2 by default), and never for an overdue loan. The new `loans.renewals` column is added to existing databases on the first command (small migration helper in `db.cpp`).
- **Grace period on fines**: no fine for the first `grace_days` days of delay (2 by default); the volunteers kept waiving them by hand anyway.
- **Overdue report**: `shelfwise overdue` lists the late loans, the most overdue first.
- **Reminders**: `shelfwise remind` now actually sends mail when `smtp_host` is set, from a pool of `reminder_workers` threads (one SQLite connection per thread). The scheduler runs it every hour, so the dispatcher makes sure a loan is reminded only once. `--dry-run` prints the messages instead. `Outbox` is now safe to share between threads.
- **Search**: results come in pages (`--page`, `--per-page`, at most 100 per page) and can be sorted by title, author or year (`--sort`).
- Tests updated and extended (33 tests), README documents the new commands and settings.

## How to try

```bash
cmake -B build -G Ninja && cmake --build build && ctest --test-dir build
build/shelfwise init && build/shelfwise search orwell --sort year
```
