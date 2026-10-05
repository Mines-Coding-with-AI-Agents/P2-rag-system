"""`p2 check`: is everything committed well-formed, honest and reproducible, and what is left to do?

It prints one line per item, PASS, FAIL or TODO, then a summary, and exits 1 on any FAIL.
Every FAIL says what to do next. TODO is work you have not done yet, and it does not fail the check,
so a fresh copy of the template passes; `p2 check --final` (the submission bar, and what the
autograder runs) also exits 1 on any TODO.

Integrity, the part CI runs on every push:
- the formats of every corpus, manifest, queries, qrels, run and answers file; every document id in
  runs, qrels and answers exists in its corpus; no carriage return under corpora/;
- results/results.json and the EVAL.md tables equal a fresh `p2 score` (to 3 decimals);
- every committed run of a system that does not call Claude is run again and compared: the same
  documents in the same places, except that documents whose scores differ by less than 0.001 may
  trade places, and every metric within 0.005;
- every answers file passes the quote check's mechanics (its retrieved ids are real chunks, its
  claims have a chunk id and a quote); how many quotes verify is a result, reported by p2 score;
- `p2 license` (offline) on your own corpus once it has documents, and the corpus size caps.
Completeness, reported as TODO until done:
- runs for bm25, dense, hybrid and rerank on shared practice, shared test and your own corpus;
- your own corpus (at least 200 documents) and gold set (at least 30 queries, at least 10 written by
  hand, each with a relevant document), one ablation run, an answers file on the 12 shared questions,
  and no TODO markers left in EVAL.md and DECISIONS.md;
- 598E: three repeated reranker runs and answers files, and PREREG.md committed before your qrels.
"""

from __future__ import annotations

import importlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from p2 import config, metrics, paths, retrievers, score, verify
from p2 import corpus as corpus_mod
from p2.runfile import read_qrels, read_queries, read_questions, read_run, run_tag, summarize, validate_run

SCORE_TOLERANCE = 1e-3
METRIC_TOLERANCE = 0.005
OWN_MIN_DOCS = 200
OWN_MAX_BYTES = 25 * 1024 * 1024
OWN_MAX_FILE_BYTES = 10 * 1024 * 1024
OWN_TOKEN_WARNING = 500_000
TOKENS_PER_WORD = 1.4
GOLD_MIN_QUERIES = 30
GOLD_MIN_HAND = 10
REPEATS = 3
TODO_MARK = re.compile(r"\bTODO\b")


@dataclass
class Item:
    status: str  # PASS, FAIL or TODO
    what: str
    detail: str = ""

    def line(self) -> str:
        return f"{self.status} {self.what}" + (f": {self.detail}" if self.detail else "")


class Report:
    def __init__(self):
        self.items: list[Item] = []

    def ok(self, what: str, detail: str = "") -> None:
        self.items.append(Item("PASS", what, detail))

    def fail(self, what: str, problem: str, fix: str) -> None:
        self.items.append(Item("FAIL", what, f"{problem}. {fix}"))

    def todo(self, what: str, detail: str) -> None:
        self.items.append(Item("TODO", what, detail))


class Context:
    """What several checks share: the settings, the corpora, the queries and the run files."""

    def __init__(self, root: Path, cfg: config.Config):
        self.root = root
        self.cfg = cfg
        self._corpora: dict[str, corpus_mod.Corpus] = {}
        self.refs, self.odd = score.discover(root)

    def corpus(self, name: str) -> corpus_mod.Corpus:
        if name not in self._corpora:
            self._corpora[name] = corpus_mod.load(self.root, name)
        return self._corpora[name]

    def doc_ids(self, name: str) -> set[str]:
        return {p.stem for p in corpus_mod.doc_files(paths.docs_dir(self.root, name))}

    def queries(self, corpus: str, query_set: str):
        path = paths.queries(self.root, corpus, query_set)
        return read_queries(path, require_origin=corpus == "own")[0] if path.is_file() else []

    def qrels(self, corpus: str, query_set: str) -> dict:
        path = paths.qrels(self.root, corpus, query_set)
        return read_qrels(path)[0] if path.is_file() else {}

    def chunk_texts(self, data: dict) -> dict[str, str]:
        """The chunks an answers file was made from (cut once per corpus and setting)."""
        chunking = data.get("chunking") or {}
        words = int(chunking.get("words", self.cfg.chunk_words))
        overlap = int(chunking.get("overlap", self.cfg.chunk_overlap))
        return self.corpus(data.get("corpus", "shared")).chunk_texts(words, overlap)


def rel(ctx: Context, path: Path) -> str:
    return paths.rel(ctx.root, path)


# ---- integrity ----


def check_line_endings(ctx: Context, r: Report) -> None:
    base = ctx.root / "corpora"
    bad = [p for p in sorted(base.rglob("*")) if p.is_file() and b"\r" in p.read_bytes()] if base.is_dir() else []
    if bad:
        r.fail("no carriage returns under corpora/", f"{len(bad)} file(s) have Windows line endings, such as {rel(ctx, bad[0])}",
               "Convert them to LF line endings (your editor's line-ending setting, or run p2 ingest again) and commit.")  # fmt: skip
    else:
        r.ok("no carriage returns under corpora/")


def check_corpus(ctx: Context, r: Report, name: str) -> bool:
    """Format checks for one corpus; True when it has documents."""
    docs = corpus_mod.doc_files(paths.docs_dir(ctx.root, name))
    what = f"{name} corpus documents and manifest"
    if not docs:
        if name == "own":
            r.todo(what, "your own corpus has no documents yet; stage 2 starts with `uv run p2 ingest SRC_DIR`")
        else:
            r.todo(what, "the shared corpus has no documents in this copy")
        return False
    problems = corpus_mod.check_docs(paths.docs_dir(ctx.root, name)) + corpus_mod.check_manifest(ctx.root, name)
    if problems:
        fix = ("Fix the files named (or run `uv run p2 ingest` again), then commit." if name == "own"
               else "Restore corpora/shared/ from the template; it is course-owned and should not change.")  # fmt: skip
        r.fail(what, summarize(problems), fix)
    else:
        r.ok(what, f"{len(docs):,} documents, one manifest row each")
    return True


def check_own_size(ctx: Context, r: Report) -> None:
    base = paths.corpus_dir(ctx.root, "own")
    files = [p for p in base.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    big = [p for p in files if p.stat().st_size > OWN_MAX_FILE_BYTES]
    what = "own corpus size (at most 25 MB in all and 10 MB per file)"
    if big:
        r.fail(what, f"{rel(ctx, big[0])} is {big[0].stat().st_size / 1e6:.1f} MB", "Split it into parts or drop it, then commit.")
        return
    if total > OWN_MAX_BYTES:
        r.fail(what, f"corpora/own/ holds {total / 1e6:.1f} MB", "Remove documents until it is under 25 MB, then commit.")
        return
    words = sum(len(d.text.split()) for d in ctx.corpus("own").docs.values())
    tokens = int(words * TOKENS_PER_WORD)
    note = f"{total / 1e6:.1f} MB, about {tokens:,} tokens"
    if tokens > OWN_TOKEN_WARNING:
        note += "; above about 500,000 tokens a cold CI run may take more than 10 minutes, so consider trimming"
    r.ok(what, note)


def check_shared_eval(ctx: Context, r: Report, has_docs: bool) -> None:
    docs = ctx.doc_ids("shared")
    files = {
        "practice queries": paths.queries(ctx.root, "shared", "practice"),
        "practice qrels": paths.qrels(ctx.root, "shared", "practice"),
        "test queries": paths.queries(ctx.root, "shared", "test"),
        "questions": paths.questions(ctx.root, "shared"),
    }
    problems = []
    missing = [rel(ctx, p) for p in files.values() if not p.is_file()]
    for label, path in files.items():
        if not path.is_file():
            continue
        if label.endswith("queries"):
            problems += [f"{rel(ctx, path)} {p}" for p in read_queries(path)[1]]
        elif label.endswith("qrels"):
            qrels, found = read_qrels(path)
            problems += [f"{rel(ctx, path)} {p}" for p in found]
            unknown = sorted({d for rels in qrels.values() for d in rels if d not in docs})
            if docs and unknown:
                problems.append(f"{rel(ctx, path)} names {unknown[0]}, which is not in the shared corpus")
        else:
            questions, found = read_questions(path)
            problems += [f"{rel(ctx, path)} {p}" for p in found]
            unknown = sorted({g for q in questions for g in q.gold if g not in docs})
            if docs and unknown:
                problems.append(f"{rel(ctx, path)} names {unknown[0]}, which is not in the shared corpus")
    what = "shared queries, qrels and questions"
    if missing and not has_docs:
        r.todo(what, f"{missing[0]} is not in this copy yet")
    elif missing or problems:
        r.fail(what, summarize([f"{m} is missing" for m in missing] + problems), "Restore eval/shared/ from the template; it is course-owned.")
    else:
        r.ok(what)


def check_own_eval(ctx: Context, r: Report) -> None:
    qpath, rpath = paths.queries(ctx.root, "own", "own"), paths.qrels(ctx.root, "own", "own")
    what = "own gold set format (eval/own/queries.tsv and qrels.txt)"
    queries, problems = read_queries(qpath, require_origin=True) if qpath.is_file() else ([], [])
    problems = [f"queries.tsv {p}" for p in problems]
    qrels, found = read_qrels(rpath) if rpath.is_file() else ({}, [])
    problems += [f"qrels.txt {p}" for p in found]
    if not queries and not qrels and not problems:
        r.todo(what, "no queries yet; write them in eval/own/queries.tsv (stage 2)")
        return
    docs = ctx.doc_ids("own")
    unknown = sorted({d for rels in qrels.values() for d in rels if d not in docs})
    if unknown:
        problems.append(f"qrels.txt names {unknown[0]}, which is not in corpora/own/docs/")
    stray = sorted(set(qrels) - {q.qid for q in queries})
    if stray:
        problems.append(f"qrels.txt judges {stray[0]}, which is not in queries.tsv")
    if problems:
        r.fail(what, summarize(problems), "Fix those lines in eval/own/, then commit.")
    else:
        r.ok(what, f"{len(queries)} queries, {sum(len(v) for v in qrels.values())} judgments")


def _field(finding, name: str):
    return finding.get(name) if isinstance(finding, dict) else getattr(finding, name, None)


def check_license(ctx: Context, r: Report) -> None:
    what = "own corpus licenses (p2 license, offline)"
    try:
        license_mod = importlib.import_module("p2.license")
    except ModuleNotFoundError as error:
        if error.name != "p2.license":
            raise
        r.todo(what, "p2 license is not built yet in this copy")
        return
    findings = list(license_mod.offline_report(paths.corpus_dir(ctx.root, "own")))
    bad = [f for f in findings if _field(f, "status") in ("fail", "flag")]
    if bad:
        fails = sum(1 for f in bad if _field(f, "status") == "fail")
        first = bad[0]
        r.fail(what, f"{fails} document(s) fail and {len(bad) - fails} flag(s) are unresolved, such as {_field(first, 'docid')} ({_field(first, 'reason')})",
               "Run `uv run p2 license` for the full report and walk each one through the license-check skill.")  # fmt: skip
    else:
        r.ok(what, f"{len(findings):,} documents checked")


def check_runs(ctx: Context, r: Report) -> list[score.RunRef]:
    """Validate every run file; returns the ones that are well-formed."""
    for path in ctx.odd:
        r.fail(f"{rel(ctx, path)} is a run file p2 can read", "its name does not follow runs/shared/<name>.<practice|test>.trec, runs/own/<name>.trec or runs/own/ablation/<name>.trec",
               "Rename or remove it, then commit.")  # fmt: skip
    good = []
    for ref in ctx.refs:
        queries = ctx.queries(ref.corpus, ref.query_set)
        problems = validate_run(ref.path, k=ctx.cfg.k, docids=ctx.doc_ids(ref.corpus), qids=[q.qid for q in queries] if queries else None)
        tag = run_tag(ref.path)
        if tag and tag not in retrievers.names():
            problems.append(f"its tag {tag} names no system in p2/retrievers/")
        if problems:
            r.fail(f"{rel(ctx, ref.path)} is a valid run file", summarize(problems), "Run `uv run p2 run` for it again (or remove it), then commit.")
        else:
            good.append(ref)
    if not ctx.refs and not ctx.odd:
        r.todo("run files", "no runs yet; start with `uv run p2 run --all`")
    elif good:
        r.ok(f"{len(good)} run file(s) well-formed")
    return good


def compare_lists(committed: list[tuple[str, float]], fresh: list[tuple[str, float]], tol: float = SCORE_TOLERANCE) -> str | None:
    """None when two rankings agree up to near-ties, else the first difference."""
    n = len(committed)
    if n != len(fresh):
        return f"lists {n} documents where a fresh run lists {len(fresh)}"
    in_fresh = {d: i for i, (d, _) in enumerate(fresh)}
    in_committed = {d: i for i, (d, _) in enumerate(committed)}
    for i, ((dc, sc), (df, sf)) in enumerate(zip(committed, fresh)):
        if abs(sc - sf) >= tol:
            return f"has score {sc:.6f} at rank {i + 1} where a fresh run has {sf:.6f}"
        if dc == df:
            continue
        # A document may only trade places with documents of near-equal score; one that left the
        # list must have been near the cut-off. Lists are sorted, so comparing the ends is enough.
        j = in_fresh.get(dc, n - 1)
        h = in_committed.get(df, n - 1)
        if abs(committed[i][1] - committed[j][1]) >= tol or abs(fresh[i][1] - fresh[h][1]) >= tol:
            return f"has {dc} at rank {i + 1} where a fresh run has {df}, and their scores are not near-equal"
    return None


def check_regenerate(ctx: Context, r: Report, refs: list[score.RunRef]) -> None:
    built: dict[tuple[str, str], object] = {}
    regenerated, skipped = [], set()
    for ref in refs:
        tag = run_tag(ref.path)
        if not tag:
            continue
        if retrievers.needs_claude(tag):
            skipped.add(tag)
            continue
        what = f"{rel(ctx, ref.path)} matches a fresh run"
        key = (ref.corpus, tag)
        if key not in built:
            try:
                built[key] = retrievers.build(tag, ctx.corpus(ref.corpus), ctx.cfg)
            except NotImplementedError:
                built[key] = None
        system = built[key]
        if system is None:
            r.fail(what, f"p2/retrievers/{tag}.py still raises NotImplementedError", f"Build {tag} first, or remove this run file, then commit.")
            continue
        committed = read_run(ref.path)
        queries = ctx.queries(ref.corpus, ref.query_set)
        fresh = {q.qid: system.search(q.text, ctx.cfg.k) for q in queries}
        problem = None
        for q in queries:
            diff = compare_lists(committed.get(q.qid, []), [(d, round(float(s), 6)) for d, s in fresh[q.qid]])
            if diff:
                problem = f"for {q.qid} it {diff}"
                break
        qrels = ctx.qrels(ref.corpus, ref.query_set)
        if problem is None and qrels:
            judged = metrics.judged_queries(qrels, [q.qid for q in queries])
            old, new = metrics.evaluate(committed, qrels, judged), metrics.evaluate(fresh, qrels, judged)
            for m in metrics.METRICS:
                a, b = metrics.mean(old, m), metrics.mean(new, m)
                if abs(a - b) > METRIC_TOLERANCE:
                    problem = f"its {m} is {a:.3f} where a fresh run gets {b:.3f}"
                    break
        if problem:
            r.fail(what, problem, "Run `uv run p2 run --all` (did p2.toml or a retriever change since?) and commit the new runs.")
        else:
            regenerated.append(ref)
    if regenerated:
        names = ", ".join(sorted({run_tag(x.path) for x in regenerated}))
        note = f"{len(regenerated)} run(s) of {names}"
        if skipped:
            note += f"; runs of {', '.join(sorted(skipped))} call Claude, so they are not run again"
        r.ok("committed runs match a fresh run", note)


def check_results(ctx: Context, r: Report) -> dict:
    fresh, _notes = score.compute(ctx.root, ctx.cfg)
    has_any = bool(fresh["sets"] or fresh["answers"])
    path = paths.results_file(ctx.root)
    what = "results/results.json matches a fresh `p2 score`"
    if not path.is_file():
        if has_any:
            r.fail(what, "results/results.json is missing", "Run `uv run p2 score` and commit results/results.json and EVAL.md.")
        else:
            r.todo(what, "nothing to score yet; run `uv run p2 score` once you have runs")
    else:
        try:
            committed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            committed = None
        where = "the file is not valid JSON" if committed is None else score.same_results(committed, fresh)
        if where:
            r.fail(what, f"they differ at {where}", "Run `uv run p2 score` and commit what it writes.")
        else:
            r.ok(what)
    eval_path = ctx.root / score.EVAL_FILE
    what = "EVAL.md tables match a fresh `p2 score`"
    if not eval_path.is_file():
        if has_any:
            r.fail(what, "EVAL.md is missing", "Restore EVAL.md from the template, then run `uv run p2 score` and commit.")
        return fresh
    text = eval_path.read_text(encoding="utf-8")
    problems = score.marker_problems(text)
    stale = []
    known = 0
    for name, body in score.blocks(text).items():
        expected = score.render(name, fresh)
        if expected is None:
            continue
        known += 1
        if not body.strip() and expected.startswith("_"):
            continue  # an empty block, and nothing to put in it yet
        if not score.same_text(body, expected):
            stale.append(name)
    if problems:
        r.fail(what, summarize(problems), "Put the p2 markers back as in the template, then run `uv run p2 score`.")
    elif stale:
        r.fail(what, f"{len(stale)} table(s) are out of date or edited by hand, such as {stale[0]}", "Run `uv run p2 score` and commit EVAL.md.")
    elif known:
        r.ok(what, f"{known} table(s)")
    return fresh


def check_answers(ctx: Context, r: Report) -> None:
    files = sorted((ctx.root / "answers").glob("*/*.json"))
    if not files:
        return
    questions_cache: dict[str, dict] = {}
    good = 0
    for path in files:
        what = f"{rel(ctx, path)} is a valid answers file"
        try:
            data = verify.load_answers(path)
        except verify.AnswersError as error:
            r.fail(what, f"it {error}", "Run `uv run p2 answer` again to rewrite it (or remove it), then commit.")
            continue
        corpus = data.get("corpus", path.parent.name)
        problems = verify.mechanics(data, ctx.chunk_texts(data))
        if corpus not in questions_cache:
            qpath = paths.questions(ctx.root, corpus)
            questions_cache[corpus] = {q.qid: q for q in read_questions(qpath)[0]} if qpath.is_file() else {}
        known = questions_cache[corpus]
        for record in data["answers"]:
            q = known.get(record["qid"])
            if q is None:
                problems.append(f"{record['qid']} is not a question in eval/{corpus}/questions.tsv")
            elif q.kind != record["kind"] or q.text != record["question"]:
                problems.append(f"{record['qid']} does not match its line in eval/{corpus}/questions.tsv")
        if problems:
            r.fail(what, summarize(problems), "Run `uv run p2 answer` again to rewrite it, then commit.")
        else:
            good += 1
    if good:
        r.ok(f"{good} answers file(s) well-formed", "how many quotes verify is in results.json and EVAL.md")


# ---- completeness ----


def check_complete_runs(ctx: Context, r: Report) -> None:
    present = {(x.corpus, x.query_set, x.name) for x in ctx.refs if x.repeat is None and not x.ablation}
    for corpus, query_set in (("shared", "practice"), ("shared", "test"), ("own", "own")):
        where = "own corpus" if corpus == "own" else f"shared {query_set} queries"
        missing = [s for s in retrievers.CANONICAL if (corpus, query_set, s) not in present]
        what = f"runs of bm25, dense, hybrid and rerank on the {where}"
        if missing:
            r.todo(what, f"missing {', '.join(missing)}; `uv run p2 run --all` writes them (rerank needs --with-claude)")
        else:
            r.ok(what)


def check_complete_own(ctx: Context, r: Report) -> None:
    n = len(ctx.doc_ids("own"))
    if n >= OWN_MIN_DOCS:
        r.ok("own corpus has at least 200 documents", f"{n:,}")
    else:
        r.todo("own corpus has at least 200 documents", f"it has {n}")
    queries = ctx.queries("own", "own")
    rels = {q for q, judged in ctx.qrels("own", "own").items() if any(v > 0 for v in judged.values())}
    hand = sum(1 for q in queries if q.origin == "hand")
    without = [q.qid for q in queries if q.qid not in rels]
    gaps = []
    if len(queries) < GOLD_MIN_QUERIES:
        gaps.append(f"{len(queries)} queries of at least {GOLD_MIN_QUERIES}")
    if hand < GOLD_MIN_HAND:
        gaps.append(f"{hand} written by hand of at least {GOLD_MIN_HAND}")
    if without:
        gaps.append(f"{len(without)} without a relevant document, such as {without[0]}")
    what = "own gold set: 30 queries, 10 by hand, each with a relevant document"
    if gaps:
        r.todo(what, "; ".join(gaps))
    else:
        r.ok(what, f"{len(queries)} queries, {hand} by hand")
    ablations = [x for x in ctx.refs if x.ablation]
    if ablations:
        r.ok("at least one ablation run", ", ".join(x.name for x in ablations))
    else:
        r.todo("at least one ablation run", "`uv run p2 run --corpus own --system NAME --ablation` writes one to runs/own/ablation/")


def check_complete_answers(ctx: Context, r: Report) -> None:
    qpath = paths.questions(ctx.root, "shared")
    wanted = {q.qid for q in read_questions(qpath)[0]} if qpath.is_file() else set()
    what = "an answers file on the shared questions"
    complete = []
    for path in sorted((ctx.root / "answers" / "shared").glob("*.json")):
        if paths.REPEAT_RE.match(path.stem.rsplit(".", 1)[-1]) and "." in path.stem:
            continue
        try:
            data = verify.load_answers(path)
        except verify.AnswersError:
            continue
        if wanted and wanted <= {a["qid"] for a in data["answers"]}:
            complete.append(path.stem)
    if complete:
        r.ok(what, ", ".join(complete))
    else:
        r.todo(what, f"`uv run p2 answer --corpus shared --system NAME` answers all {len(wanted) or 12}")


def check_complete_writing(ctx: Context, r: Report) -> None:
    for name in ("EVAL.md", "DECISIONS.md"):
        path = ctx.root / name
        what = f"{name} has no TODO markers left"
        if not path.is_file():
            r.todo(what, f"{name} is missing; restore it from the template")
            continue
        count = len(TODO_MARK.findall(path.read_text(encoding="utf-8")))
        if count:
            r.todo(what, f"{count} left")
        else:
            r.ok(what)


def git(root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError:
        return None
    return done.stdout if done.returncode == 0 else None


def first_commit_where(root: Path, relpath: str, test, position: dict[str, int]) -> int | None:
    """The position (in history order) of the first commit where the file passes `test`."""
    log = git(root, "log", "--reverse", "--topo-order", "--format=%H", "--", relpath)
    for sha in (log or "").split():
        content = git(root, "show", f"{sha}:{relpath}")
        if content is not None and test(content):
            return position.get(sha)
    return None


def check_rider(ctx: Context, r: Report) -> None:
    present = {(x.name, x.repeat) for x in ctx.refs if x.corpus == "shared" and x.query_set == "practice" and x.repeat}
    missing = [f"r{i}" for i in range(1, REPEATS + 1) if ("rerank", i) not in present]
    what = "598E: rerank.practice.r1 to r3"
    if missing:
        r.todo(what, f"missing {', '.join(missing)}; `uv run p2 run --corpus shared --queries practice --system rerank --repeat 3`")
    else:
        r.ok(what)
    groups: dict[str, set[int]] = {}
    for path in (ctx.root / "answers" / "shared").glob("*.json"):
        parts = path.stem.split(".")
        if len(parts) == 2 and paths.REPEAT_RE.match(parts[1]):
            groups.setdefault(parts[0], set()).add(int(parts[1][1:]))
    full = [label for label, reps in groups.items() if set(range(1, REPEATS + 1)) <= reps]
    what = "598E: three repeated answers files, scored with Wilson intervals"
    results_path = paths.results_file(ctx.root)
    scored = False
    if full and results_path.is_file():
        try:
            scored = bool(json.loads(results_path.read_text(encoding="utf-8")).get("answer_repeats"))
        except ValueError:
            scored = False
    if not full:
        r.todo(what, "`uv run p2 answer --corpus shared --system NAME --repeat 3`, then `uv run p2 score`")
    elif not scored:
        r.todo(what, "run `uv run p2 score` so results.json has the Wilson intervals")
    else:
        r.ok(what, ", ".join(full))
    prereg = ctx.root / "PREREG.md"
    what = "598E: PREREG.md filled in and committed before eval/own/qrels.txt"
    if not prereg.is_file():
        r.todo(what, "PREREG.md is missing; restore it from the template")
        return
    if TODO_MARK.search(prereg.read_text(encoding="utf-8")):
        r.todo(what, "PREREG.md still has TODO markers")
        return
    shallow = (git(ctx.root, "rev-parse", "--is-shallow-repository") or "").strip()
    if shallow not in ("true", "false"):
        r.todo(what, "this folder has no git history to read")
        return
    if shallow == "true":
        r.todo(what, "the git history here is shallow; `git fetch --unshallow`, or run p2 check --final on your machine")
        return
    order = (git(ctx.root, "rev-list", "--reverse", "--topo-order", "HEAD") or "").split()
    position = {sha: i for i, sha in enumerate(order)}
    log = (git(ctx.root, "log", "--reverse", "--topo-order", "--format=%H", "--", "PREREG.md") or "").split()
    original = git(ctx.root, "show", f"{log[0]}:PREREG.md") if log else None
    prereg_at = first_commit_where(ctx.root, "PREREG.md", lambda text: text != original, position) if original is not None else None
    qrels_at = first_commit_where(ctx.root, "eval/own/qrels.txt", lambda text: any(line.strip() and not line.startswith("#") for line in text.splitlines()), position)
    if prereg_at is None:
        r.todo(what, "commit your filled-in PREREG.md before you commit judgments in eval/own/qrels.txt")
    elif qrels_at is None:
        r.todo(what, "PREREG.md is committed; your own qrels are not committed yet")
    elif prereg_at < qrels_at:
        r.ok(what)
    else:
        r.fail(what, "eval/own/qrels.txt had judgments in a commit before PREREG.md was first changed",
               "History cannot be rewritten fairly, so tell the instructor and explain the order in PREREG.md.")  # fmt: skip


# ---- running it ----


def run_checks(root: Path, final: bool = False) -> list[Item]:
    r = Report()
    try:
        cfg = config.load(root)
        r.ok("p2.toml settings", f"section {cfg.section}, k {cfg.k}, chunks of {cfg.chunk_words} words")
    except config.ConfigError as error:
        r.fail("p2.toml settings", str(error).rstrip("."), "The other checks use the default settings until then.")
        cfg = config.Config(root=root)
    ctx = Context(root, cfg)
    steps = [
        lambda: check_line_endings(ctx, r),
        lambda: check_shared_eval(ctx, r, check_corpus(ctx, r, "shared")),
        lambda: check_own_corpus_steps(ctx, r),
        lambda: check_own_eval(ctx, r),
        lambda: check_regenerate(ctx, r, check_runs(ctx, r)),
        lambda: check_results(ctx, r),
        lambda: check_answers(ctx, r),
        lambda: check_complete_runs(ctx, r),
        lambda: check_complete_own(ctx, r),
        lambda: check_complete_answers(ctx, r),
        lambda: check_complete_writing(ctx, r),
    ]
    if cfg.section == "598E":
        steps.append(lambda: check_rider(ctx, r))
    for step in steps:
        try:
            step()
        except Exception as error:  # report, do not hide: the student needs the line and the instructor the error
            r.fail("p2 check itself", f"something unexpected happened ({type(error).__name__}: {error})",
                   "Show this line to the instructor; the checks after it may be incomplete.")  # fmt: skip
    return r.items


def check_own_corpus_steps(ctx: Context, r: Report) -> None:
    if check_corpus(ctx, r, "own"):
        check_own_size(ctx, r)
        check_license(ctx, r)


def run(args, cfg_root: Path) -> int:
    items = run_checks(cfg_root, final=args.final)
    for item in items:
        print(item.line())
    fails = sum(1 for i in items if i.status == "FAIL")
    todos = sum(1 for i in items if i.status == "TODO")
    passes = len(items) - fails - todos
    print(f"{passes} passed, {todos} to do, {fails} failed.")
    if fails:
        print("Fix the FAIL lines first; each one says what to do.")
    elif todos and args.final:
        print("--final is the submission bar, so every TODO line has to be done.")
    elif todos:
        print("TODO lines are work still to do; they do not fail this check.")
    else:
        print("Everything checks out.")
    return 1 if fails or (args.final and todos) else 0
