"""
RAG (Retrieval Augmented Generation) Engine for Lithium IDE.

Indexes project files into text chunks, scores them against a query using
TF-IDF cosine similarity, and returns the most relevant snippets so they
can be injected into the AI prompt context.

No external ML dependencies — uses only the Python standard library.
"""

import math
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".htm", ".css", ".scss",
    ".less", ".json", ".jsonc", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".env", ".md", ".rst", ".txt", ".sh", ".bat", ".ps1", ".c", ".cpp",
    ".h", ".hpp", ".cs", ".java", ".go", ".rs", ".rb", ".php", ".swift",
    ".kt", ".lua", ".r", ".sql", ".xml", ".svg", ".gitignore", ".editorconfig",
    ".dockerfile", ".makefile",
}

_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", ".env",
    ".models", "dist", "build", ".pytest_cache", ".mypy_cache",
    ".tox", "coverage", ".idea", ".vscode",
}

_MAX_FILE_SIZE_BYTES = 150_000  # 150 KB — skip larger files
_CHUNK_LINES = 40               # lines per chunk
_CHUNK_OVERLAP = 8              # overlap between consecutive chunks
_MIN_CHUNK_TOKENS = 10          # skip tiny chunks


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FileChunk:
    """A slice of a source file with positional metadata."""
    file_path: str       # absolute path
    rel_path: str        # path relative to project root
    start_line: int      # 1-based
    end_line: int        # 1-based, inclusive
    content: str         # raw text

    def header(self) -> str:
        return f"# {self.rel_path}  (lines {self.start_line}–{self.end_line})"

    def formatted(self) -> str:
        return f"{self.header()}\n{self.content}"


# ---------------------------------------------------------------------------
# Tokeniser / TF-IDF helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> List[str]:
    """Lower-case word tokenizer; strips punctuation."""
    return re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text.lower())


def _tf(tokens: List[str]) -> Dict[str, float]:
    freq: Dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    total = max(len(tokens), 1)
    return {t: c / total for t, c in freq.items()}


def _cosine(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    dot = sum(vec_a.get(t, 0.0) * v for t, v in vec_b.items())
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Core RAG class
# ---------------------------------------------------------------------------

class ProjectRAG:
    """
    Indexes a project directory and retrieves the most relevant code chunks
    for a given natural-language or code query.

    Usage
    -----
    rag = ProjectRAG()
    rag.build_index("/path/to/project")          # call on folder open
    context = rag.get_context_for_prompt(query)  # inject into AI prompt
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._chunks: List[FileChunk] = []
        self._chunk_tfs: List[Dict[str, float]] = []
        self._idf: Dict[str, float] = {}
        self._root: Optional[str] = None
        self._indexed: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_indexed(self) -> bool:
        return self._indexed

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def build_index(self, root_path: str) -> None:
        """Scan *root_path* and build the in-memory TF-IDF index.

        Safe to call from a background thread.
        """
        chunks = _collect_chunks(root_path)
        tfs = [_tf(_tokenize(c.content)) for c in chunks]
        idf = _compute_idf(tfs)

        with self._lock:
            self._root = root_path
            self._chunks = chunks
            self._chunk_tfs = tfs
            self._idf = idf
            self._indexed = True

    def build_index_async(self, root_path: str) -> None:
        """Non-blocking version of :meth:`build_index`."""
        t = threading.Thread(
            target=self.build_index, args=(root_path,), daemon=True
        )
        t.start()

    def retrieve(
        self, query: str, top_k: int = 6, exclude_file: Optional[str] = None
    ) -> List[Tuple[FileChunk, float]]:
        """Return up to *top_k* (chunk, score) pairs most relevant to *query*.

        Args:
            query: The user's message or a derived search string.
            top_k: Maximum number of chunks to return.
            exclude_file: Absolute path of a file to exclude (the currently
                          open file — it's already in the prompt).
        """
        with self._lock:
            chunks = list(self._chunks)
            tfs = list(self._chunk_tfs)
            idf = dict(self._idf)

        if not chunks:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        query_tf = _tf(query_tokens)
        query_tfidf = {t: tf * idf.get(t, 0.0) for t, tf in query_tf.items()}

        results: List[Tuple[FileChunk, float]] = []
        for chunk, tf in zip(chunks, tfs):
            if exclude_file and chunk.file_path == exclude_file:
                continue
            chunk_tfidf = {t: v * idf.get(t, 0.0) for t, v in tf.items()}
            score = _cosine(query_tfidf, chunk_tfidf)
            if score > 0:
                results.append((chunk, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def get_context_for_prompt(
        self,
        query: str,
        max_chars: int = 3000,
        top_k: int = 6,
        exclude_file: Optional[str] = None,
    ) -> str:
        """Return a formatted multi-file context string ready to inject into
        a prompt, capped at *max_chars* characters.

        Returns an empty string when the index is empty or no relevant chunks
        were found (score > 0).
        """
        if not self._indexed:
            return ""

        hits = self.retrieve(query, top_k=top_k, exclude_file=exclude_file)
        if not hits:
            return ""

        parts: List[str] = []
        total_chars = 0
        seen_files: set = set()

        for chunk, _score in hits:
            block = chunk.formatted()
            if total_chars + len(block) > max_chars:
                remaining = max_chars - total_chars
                if remaining < 60:
                    break
                block = block[:remaining] + "\n... [truncated]"
            parts.append(block)
            seen_files.add(chunk.rel_path)
            total_chars += len(block)
            if total_chars >= max_chars:
                break

        if not parts:
            return ""

        header = (
            f"RELEVANT PROJECT FILES (RAG — {len(seen_files)} file(s), "
            f"{len(parts)} chunk(s) retrieved from the project index):\n"
        )
        return header + "\n\n".join(parts)

    def invalidate(self) -> None:
        """Clear the index (e.g., when the project is closed)."""
        with self._lock:
            self._chunks = []
            self._chunk_tfs = []
            self._idf = {}
            self._root = None
            self._indexed = False


# ---------------------------------------------------------------------------
# File collection & chunking helpers
# ---------------------------------------------------------------------------

def _is_text_file(path: str) -> bool:
    _, ext = os.path.splitext(path)
    if ext.lower() in _TEXT_EXTENSIONS:
        return True
    basename = os.path.basename(path).lower()
    # Files with no extension that are typically text
    no_ext_text = {"makefile", "dockerfile", "gemfile", "rakefile", "procfile"}
    return basename in no_ext_text


def _collect_chunks(root_path: str) -> List[FileChunk]:
    """Walk *root_path* and return all text chunks."""
    chunks: List[FileChunk] = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Prune unwanted directories in-place
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".") and d not in _SKIP_DIRS
        ]

        for filename in filenames:
            if filename.startswith("."):
                continue
            full_path = os.path.join(dirpath, filename)
            if not _is_text_file(full_path):
                continue
            try:
                file_size = os.path.getsize(full_path)
            except OSError:
                continue
            if file_size > _MAX_FILE_SIZE_BYTES:
                continue

            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as fh:
                    lines = fh.readlines()
            except OSError:
                continue

            rel_path = os.path.relpath(full_path, root_path).replace("\\", "/")
            chunks.extend(_chunk_lines(lines, full_path, rel_path))

    return chunks


def _chunk_lines(
    lines: List[str], abs_path: str, rel_path: str
) -> List[FileChunk]:
    """Split a list of lines into overlapping chunks."""
    result: List[FileChunk] = []
    total = len(lines)
    step = max(1, _CHUNK_LINES - _CHUNK_OVERLAP)
    i = 0
    while i < total:
        end = min(i + _CHUNK_LINES, total)
        content = "".join(lines[i:end]).rstrip()
        if len(_tokenize(content)) >= _MIN_CHUNK_TOKENS:
            result.append(
                FileChunk(
                    file_path=abs_path,
                    rel_path=rel_path,
                    start_line=i + 1,
                    end_line=end,
                    content=content,
                )
            )
        i += step
    return result


def _compute_idf(tfs: List[Dict[str, float]]) -> Dict[str, float]:
    """Compute inverse-document-frequency for every term in the corpus."""
    num_docs = len(tfs)
    if num_docs == 0:
        return {}

    doc_freq: Dict[str, int] = {}
    for tf in tfs:
        for term in tf:
            doc_freq[term] = doc_freq.get(term, 0) + 1

    idf: Dict[str, float] = {}
    for term, df in doc_freq.items():
        idf[term] = math.log((num_docs + 1) / (df + 1)) + 1.0  # smoothed IDF
    return idf
