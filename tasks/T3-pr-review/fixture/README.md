# Shelfwise

Lending service for a neighbourhood library: catalogue, members, loans, fines and monthly reports.
C++20 and SQLite, nothing else.

```bash
cmake -B build -G Ninja && cmake --build build
build/shelfwise init
build/shelfwise add-book 9780451524935 "Nineteen Eighty-Four" "George Orwell"
build/shelfwise add-member "Ada Lovelace" --email ada@example.org
build/shelfwise borrow 1 9780451524935
build/shelfwise renew 1
build/shelfwise search orwell --page 2 --per-page 10 --sort year
build/shelfwise overdue
build/shelfwise remind --dry-run
ctest --test-dir build              # tests
```

Settings come from a file (`--config`, one `name = value` per line) and `SHELFWISE_*` environment
variables (`SHELFWISE_DATABASE`, `SHELFWISE_LOAN_DAYS`…). See `src/config.hpp`.

| Setting | Default | Meaning |
|---|---|---|
| `loan_days` | 21 | length of a loan, and of each renewal |
| `max_loans` | 5 | open loans per member |
| `max_renewals` | 2 | renewals per loan |
| `fine_per_day_cents` | 25 | fine per day of delay |
| `grace_days` | 2 | days of delay before the fine starts |
| `smtp_host` | empty | mail server; without it, `remind` only prints |
| `reminder_workers` | 4 | threads sending the reminders |

Existing databases get the new `loans.renewals` column automatically, on the first command.

## Layout

| Module | Role |
|---|---|
| `config` | settings |
| `date` | calendar dates |
| `db` | SQLite connection, statements, schema, transactions |
| `models` | `Book`, `Member`, `Loan` |
| `repository` | every SQL query |
| `loans` | lending rules and fines |
| `search` | catalogue search |
| `reports` | monthly and overdue reports |
| `notify`, `mailer` | overdue reminders, sent by worker threads |
| `cli` | desk command line |
