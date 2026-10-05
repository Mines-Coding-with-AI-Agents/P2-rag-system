"""Where every file of the repository lives, in one place (section 1 of the layout)."""

from __future__ import annotations

import re
from pathlib import Path

CORPORA = ("shared", "own")
QUERY_SETS = {"shared": ("practice", "test"), "own": ("own",)}
# A label names a run or answers file; dots are not allowed because they separate the query set
# and the repeat number in a file name (rerank.practice.r2.trec).
LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
REPEAT_RE = re.compile(r"^r([1-9][0-9]*)$")


def corpus_dir(root: Path, corpus: str) -> Path:
    return root / "corpora" / corpus


def docs_dir(root: Path, corpus: str) -> Path:
    return corpus_dir(root, corpus) / "docs"


def manifest(root: Path, corpus: str) -> Path:
    return corpus_dir(root, corpus) / "manifest.tsv"


def queries(root: Path, corpus: str, query_set: str) -> Path:
    if corpus == "own":
        return root / "eval" / "own" / "queries.tsv"
    return root / "eval" / "shared" / f"{query_set}.queries.tsv"


def qrels(root: Path, corpus: str, query_set: str) -> Path:
    if corpus == "own":
        return root / "eval" / "own" / "qrels.txt"
    return root / "eval" / "shared" / f"{query_set}.qrels.txt"


def questions(root: Path, corpus: str = "shared") -> Path:
    return root / "eval" / corpus / "questions.tsv"


def run_file(root: Path, corpus: str, query_set: str, name: str, repeat: int | None = None, ablation: bool = False) -> Path:
    suffix = f".r{repeat}" if repeat else ""
    if corpus == "own":
        folder = root / "runs" / "own" / ("ablation" if ablation else "")
        return folder / f"{name}{suffix}.trec"
    return root / "runs" / "shared" / f"{name}.{query_set}{suffix}.trec"


def trace_file(root: Path, corpus: str, query_set: str, name: str, repeat: int | None = None, ablation: bool = False) -> Path:
    suffix = f".r{repeat}" if repeat else ""
    middle = f"ablation-{name}" if ablation else name
    return root / "traces" / f"{corpus}-{query_set}-{middle}{suffix}.jsonl"


def answers_file(root: Path, corpus: str, label: str, repeat: int | None = None) -> Path:
    suffix = f".r{repeat}" if repeat else ""
    return root / "answers" / corpus / f"{label}{suffix}.json"


def answers_trace(root: Path, label: str, repeat: int | None = None) -> Path:
    suffix = f".r{repeat}" if repeat else ""
    return root / "traces" / f"answers-{label}{suffix}.jsonl"


def results_file(root: Path) -> Path:
    return root / "results" / "results.json"


def rel(root: Path, path: Path) -> str:
    """A path relative to the repository, with forward slashes on every system."""
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def write_text(path: Path, text: str) -> None:
    """Write UTF-8 text with \\n line endings, creating the folder first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
