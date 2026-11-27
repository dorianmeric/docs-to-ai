"""
In-process BM25 index used for hybrid (sparse + dense) retrieval.

ChromaDB's local persistent client has no native sparse/BM25 support (its
``collection.search`` hybrid API is limited to the hosted/distributed backend),
so a small Okapi BM25 index is built in memory from the chunks that are already
stored in the collection. It is rebuilt lazily whenever the collection changes,
and its ranking is fused with dense results using Reciprocal Rank Fusion (RRF)
in :mod:`app.vector_store`.

Why hybrid: dense-only retrieval misses exact terms — IDs, ticket numbers,
product codes, surnames — that BM25 matches trivially. Fusing both lists lifts
nDCG by roughly 7% in published benchmarks.
"""

import math
import re
import threading
from collections import Counter
from typing import Dict, Iterable, List, Sequence, Tuple

# Unicode-aware word tokenizer: keeps accented words and digits, which matter
# for the kind of exact-match queries BM25 is here to serve.
_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Very common words add noise and (for BM25) almost no signal.
_STOPWORDS = frozenset(
    """
    a an and are as at be been but by for from had has have if in into is it its
    of on or that the their then there these they this to was were which will with
    """.split()
)


def tokenize(text: str) -> List[str]:
    """Lowercase word tokenization with stopword removal."""
    if not text:
        return []
    return [t for t in _WORD_RE.findall(text.lower()) if t not in _STOPWORDS]


class BM25Index:
    """Okapi BM25 over an in-memory snapshot of the collection's chunks."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._ids: List[str] = []
        self._doc_len: List[int] = []
        self._postings: Dict[str, List[Tuple[int, int]]] = {}
        self._avg_len = 0.0
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return len(self._ids)

    def build(self, ids: Sequence[str], texts: Iterable[str]) -> None:
        """(Re)build the index from document IDs and their text."""
        ids_list = list(ids)
        doc_len: List[int] = []
        postings: Dict[str, List[Tuple[int, int]]] = {}

        for idx, text in enumerate(texts):
            tokens = tokenize(text)
            doc_len.append(len(tokens))
            if not tokens:
                continue
            for term, tf in Counter(tokens).items():
                postings.setdefault(term, []).append((idx, tf))

        with self._lock:
            self._ids = ids_list
            self._doc_len = doc_len
            self._postings = postings
            total = sum(doc_len)
            self._avg_len = (total / len(doc_len)) if doc_len else 0.0

    def add(self, ids: Sequence[str], texts: Iterable[str]) -> None:
        """Append documents to an existing index (cheaper than a full rebuild)."""
        ids_list = list(ids)
        with self._lock:
            start = len(self._ids)
            for offset, text in enumerate(texts):
                index = start + offset
                tokens = tokenize(text or '')
                self._doc_len.append(len(tokens))
                for term, tf in Counter(tokens).items():
                    self._postings.setdefault(term, []).append((index, tf))
            self._ids.extend(ids_list)
            total = sum(self._doc_len)
            self._avg_len = (total / len(self._doc_len)) if self._doc_len else 0.0

    def search(self, query: str, n_results: int = 10) -> List[Tuple[str, float]]:
        """Return up to ``n_results`` ``(chunk_id, score)`` pairs, best first."""
        terms = list(dict.fromkeys(tokenize(query)))  # dedupe, keep order
        if not terms or n_results <= 0:
            return []

        with self._lock:
            n_docs = len(self._ids)
            if not n_docs or not self._avg_len:
                return []

            scores: Dict[int, float] = {}
            for term in terms:
                posting = self._postings.get(term)
                if not posting:
                    continue
                # BM25 idf in its always-positive form (Robertson/Sparck Jones)
                idf = math.log(1 + (n_docs - len(posting) + 0.5) / (len(posting) + 0.5))
                for idx, tf in posting:
                    norm = 1 - self.b + self.b * (self._doc_len[idx] / self._avg_len)
                    scores[idx] = scores.get(idx, 0.0) + idf * (
                        tf * (self.k1 + 1) / (tf + self.k1 * norm)
                    )

            ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:n_results]
            return [(self._ids[idx], score) for idx, score in ranked]
