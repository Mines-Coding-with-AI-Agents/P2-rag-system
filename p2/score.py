"""`p2 score`: score every run file that has qrels, compare every pair of systems, check the answers files,
write results/results.json, and rewrite the tables between the p2 markers in EVAL.md.

A table in EVAL.md sits between two markers with the same NAME:

    <!-- p2:begin NAME -->
    (p2 score writes this part; anything you type here is replaced)
    <!-- p2:end NAME -->

The names:
    shared-practice            the systems on the shared practice queries: recall@10, MRR@10, nDCG@10
    shared-practice-classes    the same per query class (add -recall, -mrr or -ndcg for one metric)
    shared-practice-pairs      every pair of systems: mean difference, paired 95% interval, minimum
                               detectable difference, reading (add -recall, -mrr or -ndcg for one metric)
    own, own-classes, own-pairs   the same on your own corpus and gold set
    own-ablation               each ablation run against each of the other systems on your corpus
    answers                    each answers file: verified share, not_found share, declined share
    repeats                    598E: the repeated reranker runs and answers files, with their spread
p2 check recomputes every one of these tables, so edit your prose around them, never inside.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from p2 import metrics, paths, stats, verify
from p2 import corpus as corpus_mod
from p2.retrievers import CANONICAL
from p2.runfile import read_qrels, read_queries, read_run

METRIC_NAMES = {"recall@10": "Recall@10", "mrr@10": "MRR@10", "ndcg@10": "nDCG@10"}
METRIC_SLUGS = {"recall": "recall@10", "mrr": "mrr@10", "ndcg": "ndcg@10"}
SETS = {"shared-practice": ("shared", "practice"), "shared-test": ("shared", "test"), "own": ("own", "own")}
VIEWS = ("classes", "pairs", "ablation")
BLOCK_RE = re.compile(r"<!-- p2:begin (?P<name>[A-Za-z0-9_.-]+) -->(?P<body>.*?)<!-- p2:end (?P=name) -->", re.S)
BEGIN_RE = re.compile(r"<!-- p2:begin ([A-Za-z0-9_.-]+) -->")
END_RE = re.compile(r"<!-- p2:end ([A-Za-z0-9_.-]+) -->")
EVAL_FILE = "EVAL.md"
TOO_EASY = 0.95


@dataclass(frozen=True)
class RunRef:
    corpus: str
    query_set: str
    name: str
    path: Path
    repeat: int | None = None
    ablation: bool = False

    @property
    def system(self) -> str:
        """The name the tables show: the file's name, with ablation/ in front for an ablation."""
        return f"ablation/{self.name}" if self.ablation else self.name

    @property
    def set_key(self) -> str:
        return f"{self.corpus}/{self.query_set}"


def discover(root: Path) -> tuple[list[RunRef], list[Path]]:
    """Every run file under runs/ that follows the naming rules, and the files that do not."""
    found: list[RunRef] = []
    odd: list[Path] = []
    base = root / "runs"
    if not base.is_dir():
        return found, odd
    for path in sorted(p for p in base.rglob("*") if p.is_file() and not p.name.startswith(".")):
        where = path.relative_to(base).parts
        parts = path.stem.split(".") if path.suffix == ".trec" else []
        ref = None
        if parts and all(paths.LABEL_RE.match(p) for p in parts):
            repeat = None
            if len(parts) > 1 and paths.REPEAT_RE.match(parts[-1]):
                repeat = int(parts[-1][1:])
                parts = parts[:-1]
            if where[:-1] == ("shared",) and len(parts) == 2 and parts[1] in paths.QUERY_SETS["shared"]:
                ref = RunRef("shared", parts[1], parts[0], path, repeat)
            elif where[:-1] == ("own",) and len(parts) == 1:
                ref = RunRef("own", "own", parts[0], path, repeat)
            elif where[:-1] == ("own", "ablation") and len(parts) == 1 and repeat is None:
                ref = RunRef("own", "own", parts[0], path, None, ablation=True)
        if ref is None:
            odd.append(path)
        else:
            found.append(ref)
    return found, odd


def system_order(name: str) -> tuple:
    if name.startswith("ablation/"):
        return (2, name)
    return (0, CANONICAL.index(name), name) if name in CANONICAL else (1, name)


def r6(x: float) -> float:
    return round(float(x), 6)


def _pairs(names: list[str], per_query: dict[str, dict[str, dict[str, float]]], judged: list[str]) -> list[dict]:
    out = []
    for j, a in enumerate(names):
        for b in names[:j]:
            for m in metrics.METRICS:
                va = [per_query[a][q][m] for q in judged]
                vb = [per_query[b][q][m] for q in judged]
                boot = stats.paired_bootstrap(va, vb)
                out.append({
                    "a": a, "b": b, "metric": m, "n": boot["n"],
                    "mean_diff": r6(boot["mean_diff"]), "ci95": [r6(v) for v in boot["ci95"]],
                    "sd_diff": r6(boot["sd_diff"]), "mdd80": r6(stats.mdd(boot["sd_diff"], boot["n"])),
                    "reading": stats.reading(boot["ci95"], a, b),
                })  # fmt: skip
    return out


def score_set(root: Path, corpus: str, query_set: str, refs: list[RunRef], qrels_path: Path) -> tuple[dict | None, list[str]]:
    """The results for one corpus and query set, or None when there is nothing to score."""
    notes: list[str] = []
    qpath = paths.queries(root, corpus, query_set)
    if not qrels_path.is_file() or not qpath.is_file():
        return None, notes
    queries, _ = read_queries(qpath)
    qrels, _ = read_qrels(qrels_path)
    judged = metrics.judged_queries(qrels, [q.qid for q in queries])
    mine = [r for r in refs if r.corpus == corpus and r.query_set == query_set]
    if not judged or not mine:
        return None, notes
    classes = {q.qid: q.cls for q in queries}
    class_names = list(dict.fromkeys(classes[q] for q in judged))
    n_docs = len(corpus_mod.doc_files(paths.docs_dir(root, corpus)))
    graded = any(r > 1 for rels in qrels.values() for r in rels.values())
    result = {
        "corpus": corpus, "queries": query_set,
        "queries_file": paths.rel(root, qpath), "qrels_file": paths.rel(root, qrels_path),
        "n_queries": len(judged), "n_documents": n_docs, "graded": graded,
        "chance_recall@10": r6(min(1.0, 10 / n_docs)) if n_docs else None,
        "systems": {}, "pairs": [],
    }  # fmt: skip
    per_query: dict[str, dict[str, dict[str, float]]] = {}
    for ref in sorted((r for r in mine if r.repeat is None), key=lambda r: system_order(r.system)):
        try:
            run = read_run(ref.path)
            pq = metrics.evaluate(run, qrels, judged)
        except ValueError as error:
            notes.append(f"{paths.rel(root, ref.path)} was not scored: {error}")
            continue
        per_query[ref.system] = pq
        result["systems"][ref.system] = {
            "run": paths.rel(root, ref.path),
            "mean": {m: r6(metrics.mean(pq, m)) for m in metrics.METRICS},
            "by_class": {
                c: {"n": sum(1 for q in judged if classes[q] == c), **{m: r6(metrics.mean(pq, m, [q for q in judged if classes[q] == c])) for m in metrics.METRICS}}
                for c in class_names
            },
            "per_query": {q: {m: r6(v) for m, v in pq[q].items()} for q in judged},
        }
    names = list(result["systems"])
    result["pairs"] = _pairs(names, per_query, judged)
    repeats: dict[str, dict] = {}
    for ref in sorted((r for r in mine if r.repeat is not None), key=lambda r: (system_order(r.system), r.repeat)):
        try:
            pq = metrics.evaluate(read_run(ref.path), qrels, judged)
        except ValueError as error:
            notes.append(f"{paths.rel(root, ref.path)} was not scored: {error}")
            continue
        entry = repeats.setdefault(ref.system, {"runs": [], "repeat": [], "values": {m: [] for m in metrics.METRICS}, "vs": {}})
        entry["runs"].append(paths.rel(root, ref.path))
        entry["repeat"].append(ref.repeat)
        for m in metrics.METRICS:
            entry["values"][m].append(r6(metrics.mean(pq, m)))
        for other in names:
            if other == ref.system:
                continue
            for m in metrics.METRICS:
                boot = stats.paired_bootstrap([pq[q][m] for q in judged], [per_query[other][q][m] for q in judged])
                entry["vs"].setdefault(other, {}).setdefault(m, []).append(
                    {"repeat": ref.repeat, "mean_diff": r6(boot["mean_diff"]), "ci95": [r6(v) for v in boot["ci95"]], "reading": stats.reading(boot["ci95"], f"{ref.system}.r{ref.repeat}", other)}
                )
    for entry in repeats.values():
        entry["spread"] = {m: {"min": min(v), "max": max(v), "range": r6(max(v) - min(v)), "sd": r6(stats.sd(v))} for m, v in entry["values"].items()}
    if repeats:
        result["repeats"] = repeats
    return result, notes


def score_answers(root: Path, cfg) -> tuple[dict, dict, list[str]]:
    """(answers results, answer repeats, notes) for every answers file under answers/."""
    results: dict[str, dict] = {}
    notes: list[str] = []
    chunk_cache: dict[tuple, dict[str, str]] = {}
    for path in sorted((root / "answers").glob("*/*.json")):
        corpus = path.parent.name
        try:
            data = verify.load_answers(path)
        except verify.AnswersError as error:
            notes.append(f"{paths.rel(root, path)} was not checked: it {error}")
            continue
        chunking = data.get("chunking") or {}
        key = (data.get("corpus", corpus), int(chunking.get("words", cfg.chunk_words)), int(chunking.get("overlap", cfg.chunk_overlap)))
        if key not in chunk_cache:
            chunk_cache[key] = verify.chunk_texts(data, root, cfg)
        totals = verify.evaluate(data, chunk_cache[key], label=path.stem)
        t = totals.as_dict()
        entry = {
            "file": paths.rel(root, path), "corpus": corpus, "system": data.get("system"), "model": data.get("model"), **t,
            "verified_share": r6(t["verified"] / t["n_in"]) if t["n_in"] else None,
            "verified_wilson95": [r6(v) for v in stats.wilson(t["verified"], t["n_in"])],
            "not_found_in_share": r6(t["not_found_in"] / t["n_in"]) if t["n_in"] else None,
            "declined_out_share": r6(t["declined_out"] / t["n_out"]) if t["n_out"] else None,
            "declined_out_wilson95": [r6(v) for v in stats.wilson(t["declined_out"], t["n_out"])],
        }  # fmt: skip
        results[f"{corpus}/{path.stem}"] = entry
    repeats: dict[str, dict] = {}
    for key, entry in results.items():
        parts = key.split("/", 1)[1].split(".")
        if len(parts) == 2 and paths.REPEAT_RE.match(parts[1]):
            group = repeats.setdefault(f"{entry['corpus']}/{parts[0]}", {"files": [], "verified_share": [], "declined_out_share": []})
            group["files"].append(entry["file"])
            group["verified_share"].append(entry["verified_share"])
            group["declined_out_share"].append(entry["declined_out_share"])
            for f in ("verified", "n_in", "declined_out", "n_out"):
                group[f] = group.get(f, 0) + entry[f]
    for group in repeats.values():
        group["pooled_verified_wilson95"] = [r6(v) for v in stats.wilson(group["verified"], group["n_in"])]
        group["pooled_declined_out_wilson95"] = [r6(v) for v in stats.wilson(group["declined_out"], group["n_out"])]
        for f in ("verified_share", "declined_out_share"):
            values = [v for v in group[f] if v is not None]
            group[f + "_range"] = r6(max(values) - min(values)) if values else None
    return results, repeats, notes


def compute(root: Path, cfg, test_qrels: Path | None = None) -> tuple[dict, list[str]]:
    """Everything p2 score writes to results.json, and notes about files it could not use."""
    refs, odd = discover(root)
    notes = [f"{paths.rel(root, p)} does not follow the run-file naming rules, so it was not scored" for p in odd]
    sets: dict[str, dict] = {}
    plan = [("shared", "practice", paths.qrels(root, "shared", "practice")), ("own", "own", paths.qrels(root, "own", "own"))]
    if test_qrels:
        plan.insert(1, ("shared", "test", Path(test_qrels)))
    for corpus, query_set, qrels_path in plan:
        result, set_notes = score_set(root, corpus, query_set, refs, qrels_path)
        notes += set_notes
        if result:
            sets[f"{corpus}/{query_set}"] = result
    answers, answer_repeats, answer_notes = score_answers(root, cfg)
    notes += answer_notes
    results = {
        "written_by": "uv run p2 score",
        "note": "p2 check recomputes this file from the committed runs, qrels and answers; do not edit it by hand.",
        "metrics": list(metrics.METRICS),
        "sets": sets,
        "answers": answers,
    }
    if answer_repeats:
        results["answer_repeats"] = answer_repeats
    return results, notes


# ---- rendering the EVAL.md tables ----


def f3(x) -> str:
    return "-" if x is None else f"{x:.3f}"


def signed(x: float) -> str:
    return f"{x:+.3f}"


def interval(ci) -> str:
    return f"[{ci[0]:+.3f}, {ci[1]:+.3f}]"


def share(k: int, n: int) -> str:
    return f"{k} of {n} ({100 * k / n:.0f}%)" if n else "no questions"


def table(header: list[str], rows: list[list[str]], right: int = 1, text_last: bool = False) -> str:
    """A Markdown table: the first `right` columns align left and the numbers after them right;
    text_last keeps a last column of words (a reading) aligned left too."""
    align = ["---"] * right + ["---:"] * (len(header) - right)
    if text_last:
        align[-1] = "---"
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(align) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def _metrics_for(slug: str | None) -> list[str]:
    return [METRIC_SLUGS[slug]] if slug else list(metrics.METRICS)


def render_systems(s: dict) -> str:
    rows = [[name] + [f3(v["mean"][m]) for m in metrics.METRICS] for name, v in s["systems"].items()]
    chance = s.get("chance_recall@10")
    note = f"{s['n_queries']} judged queries; nDCG uses {'graded' if s['graded'] else 'binary'} labels"
    note += f"; a random ranking of the {s['n_documents']:,} documents would get recall@10 near {chance:.3f}." if chance is not None else "."
    return table(["System"] + [METRIC_NAMES[m] for m in metrics.METRICS], rows) + "\n\n" + note


def render_classes(s: dict, slug: str | None) -> str:
    wanted = _metrics_for(slug)
    first = next(iter(s["systems"].values()))
    classes = list(first["by_class"])
    header = ["System", "Metric"] + [f"{c} (n={first['by_class'][c]['n']})" for c in classes]
    rows = [[name, METRIC_NAMES[m]] + [f3(v["by_class"][c][m]) for c in classes] for name, v in s["systems"].items() for m in wanted]
    return table(header, rows, right=2)


def render_pairs(pairs: list[dict], slug: str | None) -> str:
    wanted = set(_metrics_for(slug))
    rows = [
        [f"{p['a']} minus {p['b']}", METRIC_NAMES[p["metric"]], signed(p["mean_diff"]), interval(p["ci95"]), f3(p["mdd80"]), p["reading"]]
        for p in pairs
        if p["metric"] in wanted
    ]
    if not rows:
        return "_Only one system is scored here, so there is nothing to compare yet._"
    note = "The interval is a paired bootstrap (10,000 resamples of the queries); MDD is the smallest difference this many queries detect 80% of the time."
    return table(["Comparison", "Metric", "Mean difference", "95% interval", "MDD", "Reading"], rows, right=2, text_last=True) + "\n\n" + note


def render_answers(results: dict) -> str:
    rows = []
    for key, a in results["answers"].items():
        if paths.REPEAT_RE.match(key.rsplit(".", 1)[-1]) and "." in key:
            continue
        rows.append([
            key.split("/", 1)[1], str(a["system"]),
            share(a["verified"], a["n_in"]), interval(a["verified_wilson95"]).replace("+", ""),
            share(a["not_found_in"], a["n_in"]),
            share(a["declined_out"], a["n_out"]), interval(a["declined_out_wilson95"]).replace("+", ""),
            f"{a['claims_verified']} of {a['claims']}",
        ])  # fmt: skip
    if not rows:
        return "_No answers files yet: run `uv run p2 answer --corpus shared --system NAME`, then `uv run p2 score`._"
    header = ["Label", "System", "Verified (in)", "95% interval", "not_found (in)", "Declined (out)", "95% interval", "Quotes found"]
    return table(header, rows, right=2)


def render_repeats(results: dict) -> str:
    parts = []
    for key, s in results["sets"].items():
        for name, entry in (s.get("repeats") or {}).items():
            rows = [[f"{name}.r{r}"] + [f3(entry["values"][m][i]) for m in metrics.METRICS] for i, r in enumerate(entry["repeat"])]
            rows.append(["range (max minus min)"] + [f3(entry["spread"][m]["range"]) for m in metrics.METRICS])
            parts.append(f"Repeated runs of {name} on {key}:\n\n" + table(["Run"] + [METRIC_NAMES[m] for m in metrics.METRICS], rows))
            against = ["hybrid"] if "hybrid" in entry["vs"] else list(entry["vs"])
            vs_rows = [
                [f"{name}.r{c['repeat']} minus {other}", METRIC_NAMES[m], signed(c["mean_diff"]), interval(c["ci95"]), c["reading"]]
                for other in against
                for m in metrics.METRICS
                for c in entry["vs"][other][m]
            ]
            if vs_rows:
                parts.append(table(["Comparison", "Metric", "Mean difference", "95% interval", "Reading"], vs_rows, right=2, text_last=True))
    for key, g in (results.get("answer_repeats") or {}).items():
        rows = []
        for f in g["files"]:
            a = results["answers"][f"{key.split('/', 1)[0]}/{Path(f).stem}"]
            rows.append([Path(f).stem, share(a["verified"], a["n_in"]), interval(a["verified_wilson95"]).replace("+", ""), share(a["declined_out"], a["n_out"]), interval(a["declined_out_wilson95"]).replace("+", "")])
        rows.append(["pooled", share(g["verified"], g["n_in"]), interval(g["pooled_verified_wilson95"]).replace("+", ""), share(g["declined_out"], g["n_out"]), interval(g["pooled_declined_out_wilson95"]).replace("+", "")])
        parts.append(f"Repeated answers {key}:\n\n" + table(["File", "Verified (in)", "95% interval", "Declined (out)", "95% interval"], rows))
    if not parts:
        return "_No repeated runs or answers files yet (598E: `p2 run ... --repeat 3` and `p2 answer ... --repeat 3`)._"
    return "\n\n".join(parts)


def render(name: str, results: dict) -> str | None:
    """The text of one EVAL.md block, or None when the name is not one p2 knows."""
    if name == "answers":
        return render_answers(results)
    if name == "repeats":
        return render_repeats(results)
    for set_name, (corpus, query_set) in sorted(SETS.items(), key=lambda kv: -len(kv[0])):
        if name != set_name and not name.startswith(set_name + "-"):
            continue
        rest = name[len(set_name) + 1 :].split("-") if name != set_name else []
        view = rest[0] if rest else None
        slug = rest[1] if len(rest) > 1 else None
        if len(rest) > 2 or (view and view not in VIEWS) or (slug and slug not in METRIC_SLUGS) or (view == "ablation" and corpus != "own"):
            return None
        s = results["sets"].get(f"{corpus}/{query_set}")
        if not s or not s["systems"]:
            where = "--corpus own" if corpus == "own" else f"--corpus shared --queries {query_set}"
            return f"_No scored runs here yet: run `uv run p2 run {where} --system bm25` (or `--all`), then `uv run p2 score`._"
        if view is None:
            return render_systems(s)
        if view == "classes":
            return render_classes(s, slug)
        if view == "pairs":
            return render_pairs(s["pairs"], slug)
        ablations = [p for p in s["pairs"] if p["a"].startswith("ablation/") != p["b"].startswith("ablation/")]
        if not any(n.startswith("ablation/") for n in s["systems"]):
            return "_No ablation runs yet: `uv run p2 run --corpus own --system NAME --ablation` writes one to runs/own/ablation/._"
        return render_pairs(ablations, slug)
    return None


def blocks(text: str) -> dict[str, str]:
    """{name: body} of every complete block in an EVAL.md text."""
    return {m.group("name"): m.group("body") for m in BLOCK_RE.finditer(text)}


def marker_problems(text: str) -> list[str]:
    """Markers without a partner, or a name used twice."""
    begins, ends = BEGIN_RE.findall(text), END_RE.findall(text)
    problems = []
    for name in sorted(set(begins) | set(ends)):
        if begins.count(name) != ends.count(name):
            problems.append(f"the {name} block is missing its {'end' if begins.count(name) > ends.count(name) else 'begin'} marker")
        elif begins.count(name) > 1:
            problems.append(f"the {name} block appears more than once")
    return problems


def rewrite(text: str, results: dict) -> tuple[str, list[str], list[str]]:
    """(new text, names rewritten, names p2 does not know). Unknown blocks are left as they are."""
    done: list[str] = []
    unknown: list[str] = []

    def replace(m: re.Match) -> str:
        name = m.group("name")
        body = render(name, results)
        if body is None:
            unknown.append(name)
            return m.group(0)
        done.append(name)
        return f"<!-- p2:begin {name} -->\n{body}\n<!-- p2:end {name} -->"

    return BLOCK_RE.sub(replace, text), done, unknown


NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")


def same_text(a: str, b: str, tolerance: float = 0.0011) -> bool:
    """True when two block texts differ at most in their numbers, by no more than the tolerance."""
    a, b = a.strip(), b.strip()
    if NUMBER.sub("#", a) != NUMBER.sub("#", b):
        return False
    return all(abs(float(x) - float(y)) <= tolerance for x, y in zip(NUMBER.findall(a), NUMBER.findall(b)))


def same_results(a, b, tolerance: float = 0.0005, where: str = "results") -> str | None:
    """None when two results structures match (numbers to 3 decimals), else where they first differ."""
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            extra = sorted(set(a) ^ set(b))
            return f"{where}.{extra[0]}"
        for k in a:
            found = same_results(a[k], b[k], tolerance, f"{where}.{k}")
            if found:
                return found
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return where
        for i, (x, y) in enumerate(zip(a, b)):
            found = same_results(x, y, tolerance, f"{where}[{i}]")
            if found:
                return found
        return None
    if isinstance(a, bool) or isinstance(b, bool):
        return None if a == b else where
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return None if abs(a - b) <= tolerance else where
    return None if a == b else where


def dumps(results: dict) -> str:
    return json.dumps(results, indent=2, ensure_ascii=False) + "\n"


def print_summary(results: dict) -> None:
    for key, s in results["sets"].items():
        print(f"\n{key}: {s['n_queries']} judged queries")
        width = max(len(n) for n in s["systems"]) if s["systems"] else 6
        print(f"  {'system':<{width}}  recall@10  MRR@10  nDCG@10")
        for name, v in s["systems"].items():
            print(f"  {name:<{width}}  {v['mean']['recall@10']:9.3f}  {v['mean']['mrr@10']:6.3f}  {v['mean']['ndcg@10']:7.3f}")
        for p in s["pairs"]:
            if p["metric"] == "mrr@10":
                print(f"  MRR@10 {p['a']} minus {p['b']}: {p['mean_diff']:+.3f} {interval(p['ci95'])}, {p['reading']}")
        if key == "own/own" and "bm25" in s["systems"]:
            best = max(v["mean"]["mrr@10"] for v in s["systems"].values())
            if s["systems"]["bm25"]["mean"]["recall@10"] >= TOO_EASY or best >= TOO_EASY:
                print("  Note: a score of 0.95 or more suggests your queries are too easy to tell the systems apart; harder queries make the comparison mean more.")
    for key, a in results["answers"].items():
        print(f"\nanswers {key}: verified {share(a['verified'], a['n_in'])}, not_found in {share(a['not_found_in'], a['n_in'])}, declined out {share(a['declined_out'], a['n_out'])}")


def run(args, cfg) -> int:
    root = cfg.root
    results, notes = compute(root, cfg, getattr(args, "test_qrels", None))
    for note in notes:
        print(f"Note: {note}.", file=sys.stderr)
    if getattr(args, "test_qrels", None):
        text = dumps(results)
        if args.out:
            paths.write_text(Path(args.out), text)
            print(f"Wrote {args.out} (results.json and EVAL.md are unchanged).")
        else:
            sys.stdout.write(text)
        return 0
    out = paths.results_file(root)
    paths.write_text(out, dumps(results))
    print(f"Wrote {paths.rel(root, out)}.")
    eval_path = root / EVAL_FILE
    if eval_path.is_file():
        text = eval_path.read_text(encoding="utf-8")
        problems = marker_problems(text)
        for problem in problems:
            print(f"EVAL.md: {problem}; put the marker back as in the template.")
        new, done, unknown = rewrite(text, results)
        if new != text:
            paths.write_text(eval_path, new)
        print(f"Rewrote {len(done)} table(s) in EVAL.md" + (f": {', '.join(done)}." if done else "."))
        if unknown:
            print(f"EVAL.md has block names p2 does not know, left as they were: {', '.join(unknown)}.")
    else:
        print("There is no EVAL.md, so no tables were rewritten.")
    print_summary(results)
    return 0
