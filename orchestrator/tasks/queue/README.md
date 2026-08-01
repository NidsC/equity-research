# Overnight queue

Every `*.md` file dropped in this directory is one task, dispatched by
`orchestrator/overnight.sh` as a worker named after the file (`item-1a-diff.md`
becomes worker `item-1a-diff`, branch `agent/item-1a-diff`).

This README is skipped — only files matching `*.md` other than this one should
describe work, so delete or move a task file once it has been merged.

## Before you queue something

A task file is the worker's entire brief; it cannot ask a follow-up question,
and at 3am there is nobody to ask. See `../example-add-store.md` for the shape,
and the "Writing task files" section of `ORCHESTRATION.md` for what each one
must state.

Two rules matter more overnight than they do interactively:

**Partition by file.** Workers run concurrently and merge serially. Two tasks
that touch `parse/financials.py` will produce a merge conflict, and a conflict
costs you the whole task — `integrate.sh` rolls the merge back and leaves the
branch for morning. Check the files named across every queued task before you
go to bed.

**Give the acceptance test.** `integrate.sh` runs `.venv/bin/python -m pytest -q`
and refuses to merge a branch that fails it. A task whose "done" cannot be
expressed as a passing test will come back unmerged even when the work is good.
