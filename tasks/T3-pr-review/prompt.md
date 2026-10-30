# Pull request review

You are reviewing a pull request on **Shelfwise**, a small lending service for a neighbourhood library, written in C++20 with SQLite.

- The workspace contains the repository **as it is on the pull request's branch**.
- `pr/PR.md` is the pull request's description.
- `pr/changes.diff` is its diff against `main`.
- It builds with `cmake -B build -G Ninja && cmake --build build`, and the tests run with `ctest --test-dir build`.

## What to do

Review the changes this pull request introduces, the way a careful senior reviewer would before approving a merge. Report the problems the PR brings in: bugs, security issues, concurrency issues, broken error handling, performance problems, regressions. Leave out matters of style or taste, and problems in code the PR does not touch.

Write your review to `review.json` at the root of the workspace. It must follow `review.schema.json`:

```json
{
  "summary": "optional overall assessment",
  "comments": [
    {"file": "src/example.cpp", "line": 42, "severity": "high", "description": "what is wrong, why it matters, how to fix it"}
  ]
}
```

- `file`: path relative to the repository root.
- `line`: the line number **in the file as it is in the workspace**, after the pull request, where the problem is.
- `severity`: `low`, `medium`, `high` or `critical`.
- One entry per distinct problem, without duplicates.

## Rules

- **Do not modify any file of the repository.** The only file you may create is `review.json`, besides the `build/` folder. You may build and run the code and the tests, and write throwaway programs outside the repository, for example in `/tmp`.
- Each wrong report counts against you, and so does each problem you miss.
- You have 20 minutes at most. Whatever `review.json` holds when time runs out is what gets graded. It doesn't mean you have to spend 20 minutes, it means it's the hard upper limit.
