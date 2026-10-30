# Shelfwise

Lending service for a neighbourhood library: catalogue, members, loans, fines and monthly reports.
C++20 and SQLite, nothing else.

```bash
cmake -B build -G Ninja && cmake --build build
build/shelfwise init
build/shelfwise add-book 9780451524935 "Nineteen Eighty-Four" "George Orwell"
build/shelfwise add-member "Ada Lovelace" --email ada@example.org
build/shelfwise borrow 1 9780451524935
ctest --test-dir build              # tests
```

Settings come from a file (`--config`, one `name = value` per line) and `SHELFWISE_*` environment
variables (`SHELFWISE_DATABASE`, `SHELFWISE_LOAN_DAYS`…). See `src/config.hpp`.

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
| `reports` | monthly report |
| `notify`, `mailer` | overdue reminders |
| `cli` | desk command line |
