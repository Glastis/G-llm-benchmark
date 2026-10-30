# Architecture summary check

The current folder holds a Lua codebase and `ARCHITECTURE.md`, a summary of its architecture written for a developer who joins the project tomorrow. `_judge/STATEMENT.md` is what the summary's author was asked.

Check the summary claim by claim against the code. A claim is false when the code contradicts it, or when nothing in the code supports it. Then list the important facts a newcomer would need and the summary leaves out. Open the files the summary talks about: do not grade from the summary alone.

Grade two criteria, each out of 10:

- **Truth**: 10 when every claim holds. Each false claim costs points, more when it would mislead the newcomer about how the code works.
- **Completeness**: 10 when the newcomer can find their way in the code with the summary alone. Each important fact left out costs points, more when it concerns a central part.

Write your verdict to `_judge/judgement.json`, in this form, and change no other file:

```json
{
  "false_claims": [{"claim": "…", "why": "…"}],
  "missing_facts": ["…"],
  "criteria": {
    "Truth": {"score": 8, "reasons": "…"},
    "Completeness": {"score": 6.5, "reasons": "…"}
  }
}
```

- `claim`: the sentence of the summary, quoted; `why`: what the code does instead, with the file.
- `score`: from 0 to 10, in steps of 0.5. `reasons`: two to four sentences.
