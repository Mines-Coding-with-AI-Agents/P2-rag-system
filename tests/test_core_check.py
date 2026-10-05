"""p2 check: a fresh repository passes with TODO lines, and broken or stale files FAIL with a next step."""

import json

from core_repo import make_repo

from p2 import check, cli


def run(root, *argv):
    return cli.main(["--root", str(root), *argv])


def statuses(root, final=False):
    return check.run_checks(root, final=final)


def fails(items):
    return [i for i in items if i.status == "FAIL"]


def test_fresh_repository_passes_with_todo_lines(tmp_path, capsys):
    root = make_repo(tmp_path)
    assert run(root, "check") == 0
    out = capsys.readouterr().out
    assert "FAIL" not in out
    assert "TODO runs of bm25, dense, hybrid and rerank on the shared practice queries" in out
    assert "TODO own corpus has at least 200 documents" in out
    assert run(root, "check", "--final") == 1


def test_scored_runs_regenerate_and_match(tmp_path):
    root = make_repo(tmp_path)
    run(root, "run", "--all")
    run(root, "score")
    items = statuses(root)
    assert fails(items) == [], [i.line() for i in fails(items)]
    lines = [i.line() for i in items]
    assert any(line.startswith("PASS committed runs match a fresh run: 2 run(s) of bm25") for line in lines), lines
    assert "PASS results/results.json matches a fresh `p2 score`" in lines
    assert "PASS EVAL.md tables match a fresh `p2 score`: 3 table(s)" in lines


def test_corrupted_run_fails_with_one_next_step(tmp_path):
    root = make_repo(tmp_path)
    run(root, "run", "--corpus", "shared", "--queries", "practice", "--system", "bm25")
    path = root / "runs" / "shared" / "bm25.practice.trec"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[0]  # a duplicate document with the wrong rank
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    bad = fails(statuses(root))
    assert bad and bad[0].what == "runs/shared/bm25.practice.trec is a valid run file"
    assert bad[0].detail.endswith("Run `uv run p2 run` for it again (or remove it), then commit.")


def test_tampered_run_and_hand_edited_results_fail(tmp_path):
    root = make_repo(tmp_path)
    run(root, "run", "--corpus", "shared", "--queries", "practice", "--system", "bm25")
    run(root, "score")
    results_path = root / "results" / "results.json"
    data = json.loads(results_path.read_text(encoding="utf-8"))
    data["sets"]["shared/practice"]["systems"]["bm25"]["mean"]["mrr@10"] = 0.99
    results_path.write_text(json.dumps(data), encoding="utf-8")
    path = root / "runs" / "shared" / "bm25.practice.trec"
    text = path.read_text(encoding="utf-8").replace("cfr30-75.403", "cfr30-75.400", 1)
    path.write_text(text, encoding="utf-8", newline="\n")
    whats = {i.what for i in fails(statuses(root))}
    assert "results/results.json matches a fresh `p2 score`" in whats
    assert any(w.endswith("matches a fresh run") or w.endswith("is a valid run file") for w in whats)


def test_carriage_returns_and_stub_runs_fail(tmp_path):
    root = make_repo(tmp_path)
    doc = root / "corpora" / "shared" / "docs" / "cfr30-75.400.md"
    doc.write_bytes(doc.read_bytes().replace(b"\n", b"\r\n"))
    run(root, "run", "--corpus", "shared", "--queries", "practice", "--system", "bm25", "--label", "dense")
    text = (root / "runs" / "shared" / "dense.practice.trec").read_text(encoding="utf-8").replace(" bm25\n", " dense\n")
    (root / "runs" / "shared" / "dense.practice.trec").write_text(text, encoding="utf-8", newline="\n")
    whats = {i.what: i.detail for i in fails(statuses(root))}
    assert "no carriage returns under corpora/" in whats
    assert "NotImplementedError" in whats["runs/shared/dense.practice.trec matches a fresh run"]


def test_compare_lists_allows_near_ties_only():
    committed = [("a", 1.0), ("b", 0.9995), ("c", 0.5)]
    assert check.compare_lists(committed, [("b", 0.9996), ("a", 0.9999), ("c", 0.5)]) is None
    assert check.compare_lists(committed, [("a", 1.0), ("c", 0.9995), ("b", 0.5)]) is not None
    assert check.compare_lists(committed, committed[:2]) is not None
    # A near-tie at the cut-off may swap a document out of the list.
    assert check.compare_lists(committed, [("a", 1.0), ("b", 0.9995), ("d", 0.5004)]) is None


def git(root, *args):
    import subprocess

    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args], cwd=root, check=True, capture_output=True)


def rider_item(root):
    return next(i for i in statuses(root) if i.what.startswith("598E: PREREG.md"))


def make_rider_repo(tmp_path):
    root = make_repo(tmp_path)
    toml = root / "p2.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace('section = "498E"', 'section = "598E"'), encoding="utf-8")
    (root / "PREREG.md").write_text("# PREREG\n\nTODO: your hypothesis.\n", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "template")
    return root


def test_prereg_committed_before_own_qrels_passes(tmp_path):
    root = make_rider_repo(tmp_path)
    assert rider_item(root).status == "TODO"
    (root / "PREREG.md").write_text("# PREREG\n\nHypothesis: dense beats bm25 by 0.10 MRR.\n", encoding="utf-8")
    git(root, "commit", "-q", "-am", "prereg")
    (root / "eval" / "own" / "qrels.txt").write_text("# qid 0 docid rel\no01 0 doc-1 1\n", encoding="utf-8")
    git(root, "commit", "-q", "-am", "qrels")
    assert rider_item(root).status == "PASS"


def test_prereg_committed_after_own_qrels_fails(tmp_path):
    root = make_rider_repo(tmp_path)
    (root / "eval" / "own" / "qrels.txt").write_text("# qid 0 docid rel\no01 0 doc-1 1\n", encoding="utf-8")
    git(root, "commit", "-q", "-am", "qrels")
    (root / "PREREG.md").write_text("# PREREG\n\nHypothesis written afterwards.\n", encoding="utf-8")
    git(root, "commit", "-q", "-am", "prereg")
    item = rider_item(root)
    assert item.status == "FAIL" and "tell the instructor" in item.detail
