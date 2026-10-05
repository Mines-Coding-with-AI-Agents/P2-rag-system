# CLAUDE.md - P2, a RAG system and its measurement

This repo is a student's Project 2 for CSCI 498E/598E: retrieval systems over two corpora, scored with paired intervals, plus cited answers.
`README.md` is the brief; read the section for the stage the student is on before you build anything.
The course repo's rule holds here: the student directs, you build one step at a time and narrate each change, and the student's own words stay theirs.

## The student's words

The student writes the answers in `DECISIONS.md`, the prose in `EVAL.md`, all of `PREREG.md`, and every query whose `origin` is `hand`.
Point at evidence, run commands and explain what a number means; leave their prompts and prose to them.
A query you draft is `origin` `claude`.
A relevance judgment is made by the student after reading the document; you can find the candidates.

## Where code and files go

Student work, edit freely:
- `p2/retrievers/dense.py`, `hybrid.py`, `rerank.py` (stubs that raise `NotImplementedError` until built), and new files beside them for extra systems; a file in `p2/retrievers/` is a system, and nothing else needs registering
- `prompts/answer.txt`, `p2.toml`, `corpora/own/`, `eval/own/`, `DECISIONS.md`, the prose of `EVAL.md`, `PREREG.md`, and scripts the student adds outside `p2/`

Course-owned contract, leave as is:
- the rest of `p2/`, `tests/`, `corpora/shared/`, `eval/shared/`, `.github/workflows/`, `.gitattributes`, `.claude/skills/license-check/`
- the autograder runs the instructor's copy of `p2 check --final`, so a local edit to a contract file cannot help and would show in git history
- if one looks buggy, show the student the evidence and have them report it to the instructor

Written by commands, never by hand: `runs/`, `answers/`, `traces/`, `results/results.json`, the tables between `<!-- p2:begin NAME -->` and `<!-- p2:end NAME -->` in `EVAL.md`, `LICENSES.md`, `corpora/own/INGEST.md`.
`p2 check` runs every system that does not call Claude again and compares its runs, recomputes `results/results.json` and the tables, and checks that every answers file cites real chunks, so a hand edit there turns CI red.

## Commands

Everything runs through `uv`, from the repo root: `uv sync` (add `--group ingest` before `p2 ingest`), `uv run p2 <command>`, `uv run pytest`.
The commands are `run`, `score`, `answer`, `verify`, `ingest`, `license` and `check`; `uv run p2 --help` lists their flags.
A new dependency goes in through `uv add`, and `uv.lock` is committed with it, because CI installs with `uv sync --frozen`.

## Formats

- Document: `corpora/<name>/docs/<docid>.md`, first line `# <title>`, a blank line, the body.
  A docid matches `^[a-z0-9][a-z0-9._-]*$`, is unique, and keeps its name once qrels mention it.
- Manifest: `corpora/<name>/manifest.tsv`, tab-separated, header `docid`, `title`, `source`, `license`, `notes`.
- Queries: `qid<TAB>class<TAB>text` and, in `eval/own/queries.tsv`, a fourth column `origin` (`hand` or `claude`).
  Lines that start with `#` are comments.
- Qrels: `qid 0 docid rel`, four whitespace-separated columns, `rel` 1 unless EVAL.md declares graded labels.
- Run file: `qid Q0 docid rank score tag`, document level, at most `k` lines per query, ranks 1 to n, scores non-increasing, equal scores ordered by docid, six decimals, `tag` the system name.
- Answers file: JSON with a record per question; a chunk id is `<docid>#<n>`.
- UTF-8 and `\n` line endings everywhere, and no carriage return under `corpora/`.

## Checks and cost

- Run `uv run p2 check` before every push and keep CI green.
  A `FAIL` line names the next step, an unfinished-work line exits 0, and `--final` is the submission bar.
- `claude -p` runs on the student's own Claude plan, through `p2/claude.py` only.
  Before a command that makes many calls (the reranker over a query set, `p2 answer`), say how many calls it makes, try two or three first (`--only` for answers), and ask before the full run.
- A corpus document needs a license from the `p2 license` vocabulary.
  Walk a failing or flagged document through the `license-check` skill, and write `reviewed: <reason with the quote>` in `notes` only after quoting the license text from the source page.
- Keep keys, tokens and private files out of the repo; it is public, and so is its history.
