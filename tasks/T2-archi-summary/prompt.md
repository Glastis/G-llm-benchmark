# Architecture summary

The workspace contains a Lua codebase for ComputerCraft, the Minecraft mod with programmable computers and robots ("turtles"). A developer joins the project tomorrow. Write them an architecture summary that lets them find their way in the code without reading all of it.

## Deliverable

`ARCHITECTURE.md` at the root of the workspace, in English, with exactly these second-level sections, in this order:

1. `## Purpose`: what the code is for, in a few sentences.
2. `## Layout`: the top-level folders and files, and the role of each.
3. `## Components`: the main modules, what each one provides, and which ones depend on which.
4. `## Entry points`: how the code gets onto a computer and runs, and how modules are loaded.
5. `## Data flows`: how data moves through the main subsystems.
6. `## Diagram`: at least one diagram of the architecture, in a fenced code block, either Mermaid (` ```mermaid `) or text drawing.
7. `## Observations`: notable patterns, conventions, weaknesses and risks.

A first-level title may come before the sections.

## Rules

- **At most 1,200 words**, fenced code blocks excluded.
- **Every statement must be true of this code.** The summary is checked claim by claim against the code: each wrong claim costs points, and so does each important fact that is missing. When you are not sure of something, check it in the code or leave it out.
- Do not modify, create or delete any other file in the workspace.
- You have 20 minutes at most. Whatever `ARCHITECTURE.md` holds when time runs out is what gets graded. It doesn't mean you have to spend 20 minutes, it means it's the hard upper limit.
