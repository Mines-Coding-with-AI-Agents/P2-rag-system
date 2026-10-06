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

Written by commands, never by hand: `runs/`, `answers/`, `traces/`, `results/results.json`, the tables between `<!-- p2:begin NAME -->` and `<!-- p2:end NAME -->` in `EVAL.md`, `LICENSES.md`, `corpora/own/INGEST.md` (`uv run p2 ingest --report` rewrites it after documents are removed).
`p2 check` runs every system again in a separate process with Claude switched off: the runs of systems that do not call Claude must match, and the runs of systems that do must match the traces committed with them in `traces/`.
It also recomputes `results/results.json` and the tables, requires every table in `EVAL.md` to stay, pins `corpora/shared/` and `eval/shared/` to `p2/shared.sha256`, and checks that every answers file's retrieved chunks are real.
A run file named after a system (`dense.practice.trec`) must be written by that system, so never use `--label` to name one system's run after another.

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
  Before a command that makes many calls (the reranker over a query set, `p2 answer`, `p2 run --all --with-claude`), say how many calls it makes, try two or three first (`--only` for answers, a two-line queries file for runs), and ask before the full run.
  `p2` stops by itself before more than 5 calls and prints the number; add `--yes` only after the student has said yes to that number.
- A corpus document needs a license from the `p2 license` vocabulary.
  Walk a failing or flagged document through the license-check skill (read `.claude/skills/license-check/SKILL.md` in this repo and follow it), and write `reviewed: <reason with the quote>` in `notes` only after quoting the license text from the source page.
- The own corpus needs at least 200 documents and at most 1,000,000 estimated tokens (words times 1.4; `p2 check` warns above 800,000), because CI encodes it within a 45-minute job.
  When long PDFs leave it under 200, `uv run p2 ingest SRC_DIR --part-pages 5` splits every PDF longer than 5 pages into 5-page parts that each count as a document.
  Do it before any judgment names those documents; ingest skips a file already in the corpus cut another way and names its documents, which must be removed (files and manifest rows) before the file is cut again.
- Keep keys, tokens, private files and private information about people out of the repo: student records, patient data, survey or interview answers, home addresses or personal phone numbers, private messages, lab members' data.
  It is public, and so is its history.
  Names and work contact details that a publisher printed in a public document may stay, such as an author's email on a paper or the "Prepared by" line on a USGS chapter.
