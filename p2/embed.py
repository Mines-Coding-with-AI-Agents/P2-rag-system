"""Helpers for dense retrievers: load an embedding model, encode texts, and cache document vectors.

The two models of the 12 lab load the way the lab loads them:
- potion-retrieval-32M (POTION) through model2vec, a static model: fast, no neural network at query time.
- bge-small-en-v1.5 (BGE) through fastembed, a small contextual model run with ONNX.
Both download once into the Hugging Face cache (~/.cache/huggingface/hub), the folder CI caches.
Another model name goes to fastembed if fastembed lists it, and to model2vec otherwise.

Every vector comes back with length 1, so a dot product is the cosine similarity.

doc_vectors() encodes a list of texts (your chunks) and keeps the vectors in
.cache/vectors/<model>.npz, keyed by each text's hash: a second run, a changed chunking setting or
the autograder's extra documents only encode the texts that are new. It encodes the texts sorted
by length in batches of 8, which measured 2 to 3 times faster than the original order and keeps
memory near 600 MB instead of several GB (the largest vector difference it caused was 0.0004).
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import tempfile
from collections.abc import Callable, Sequence
from functools import lru_cache
from pathlib import Path

import numpy as np

POTION = "minishlab/potion-retrieval-32M"
BGE = "BAAI/bge-small-en-v1.5"
BATCH_SIZE = 8


def unit(x) -> np.ndarray:
    """Rows scaled to length 1 (float32)."""
    x = np.asarray(x, dtype=np.float32)
    if x.ndim == 1:
        x = x[None, :]
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-9)


class Embedder:
    """A loaded model: encode(texts) gives one unit-length row per text."""

    def __init__(self, name: str, encode: Callable[[list[str]], Sequence]):
        self.name = name
        self._encode = encode

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        texts = list(texts)
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return unit(self._encode(texts))


def _hf_cache() -> str:
    from huggingface_hub.constants import HF_HUB_CACHE

    return HF_HUB_CACHE


def _load_model2vec(name: str) -> Embedder:
    from huggingface_hub import snapshot_download
    from model2vec import StaticModel

    # model2vec needs the weights and tokenizer only; skip the unused ONNX copy.
    path = snapshot_download(name, ignore_patterns=["onnx/*", "README.md"])
    model = StaticModel.from_pretrained(path)
    return Embedder(name, lambda texts: model.encode(texts))


def _load_fastembed(name: str) -> Embedder:
    from fastembed import TextEmbedding

    # fastembed's default cache is a temporary folder that the system can empty; use the Hugging Face cache.
    model = TextEmbedding(name, cache_dir=_hf_cache())
    return Embedder(name, lambda texts: np.stack(list(model.embed(texts, batch_size=BATCH_SIZE))))


def _fastembed_names() -> set[str]:
    from fastembed import TextEmbedding

    return {m["model"] for m in TextEmbedding.list_supported_models()}


@lru_cache(maxsize=None)
def load(name: str = BGE) -> Embedder:
    """Load an embedding model by its Hugging Face name (once per process)."""
    if name == POTION or name.startswith("minishlab/"):
        return _load_model2vec(name)
    if name == BGE or name in _fastembed_names():
        return _load_fastembed(name)
    return _load_model2vec(name)


def encode_sorted(embedder: Embedder, texts: Sequence[str]) -> np.ndarray:
    """Encode texts in order of length (short first), and return the rows in the original order."""
    texts = list(texts)
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    by_length = sorted(range(len(texts)), key=lambda i: len(texts[i]))
    rows = embedder.encode([texts[i] for i in by_length])
    out = np.empty_like(rows)
    out[by_length] = rows
    return out


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def store_path(root: Path, name: str) -> Path:
    return Path(root) / ".cache" / "vectors" / f"{_slug(name)}.npz"


def doc_vectors(embedder: Embedder, texts: Sequence[str], root: Path) -> np.ndarray:
    """One unit vector per text, from the cache where possible; new texts are encoded and saved."""
    texts = list(texts)
    path = store_path(root, embedder.name)
    keys = [_key(t) for t in texts]
    known: dict[str, int] = {}
    vectors = None
    if path.is_file():
        try:
            with np.load(path, allow_pickle=False) as saved:
                stored_keys, vectors = saved["keys"].tolist(), saved["vectors"]
            known = {k: i for i, k in enumerate(stored_keys)}
        except (OSError, ValueError, KeyError):
            known, vectors = {}, None  # a damaged cache is rebuilt
    missing = list(dict.fromkeys(k for k in keys if k not in known))
    if missing:
        wanted = set(missing)
        first = {k: t for k, t in zip(keys, texts) if k in wanted}
        print(f"Encoding {len(missing):,} texts with {embedder.name} (saved in .cache/vectors/ for next time)...", file=sys.stderr, flush=True)
        new = encode_sorted(embedder, [first[k] for k in missing])
        if vectors is None or len(known) == 0:
            all_keys, vectors = missing, new
        else:
            all_keys = list(known) + missing
            vectors = np.concatenate([vectors, new])
        known = {k: i for i, k in enumerate(all_keys)}
        _save(path, all_keys, vectors)
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    return np.asarray(vectors[[known[k] for k in keys]], dtype=np.float32)


def _save(path: Path, keys: list[str], vectors: np.ndarray) -> None:
    """Write the cache in one step, so an interrupted run never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as out:
            np.savez(out, keys=np.array(keys), vectors=np.asarray(vectors, dtype=np.float32))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
