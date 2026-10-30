# Code review

The current folder holds a C++20 program. `_judge/STATEMENT.md` is the statement it was written to.

Grade its code on the five criteria below, each out of 10, with the grid that follows: it is the reviewer's own, so apply it as written, including where it departs from common practice. Read every source file before you grade. Judge only the code: whether the program works and follows the statement is checked elsewhere. Where the grid names a task, the hint applies to that program only: T1 is the elevator simulation, T4 the city builder.

{grid}

Write your grades to `_judge/judgement.json`, in this form, and change no other file:

```json
{
  "criteria": {
    "Readability": {"score": 7, "reasons": "…"},
    "Architecture": {"score": 6.5, "reasons": "…"},
    "Factoring": {"score": 8, "reasons": "…"},
    "Cleanliness": {"score": 5, "reasons": "…"},
    "Safety": {"score": 9, "reasons": "…"}
  }
}
```

- `score`: from 0 to 10, in steps of 0.5.
- `reasons`: two to four sentences that name the files and functions that weigh most in the grade.
