from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .discover import normalize_text


USER_AGENT = "literature-review-agent/0.1"

# Canonical section headings we try to locate in extracted PDF text. The values
# are the regex alternatives that commonly introduce that section.
SECTION_PATTERNS = {
    "abstract": r"abstract",
    "introduction": r"introduction|1\.?\s+introduction",
    "method": r"method(?:s|ology)?|experimental design|data and methods|research design",
    "results": r"results|findings|empirical results|main results",
    "conclusion": r"conclusion(?:s)?|discussion|concluding remarks",
}


# --------------------------------------------------------------------------- #
# Pure helpers (no network, no pypdf) -- the unit-tested core.
# --------------------------------------------------------------------------- #
def looks_like_pdf(data: bytes) -> bool:
    """True if a byte blob begins with the PDF magic number."""
    return isinstance(data, (bytes, bytearray)) and data[:5] == b"%PDF-"


def clean_pdf_text(raw: str) -> str:
    """Normalize text pulled out of a PDF: join hyphenated line breaks, collapse
    whitespace, and drop bare page-number lines."""
    if not raw:
        return ""
    # Join words split across a line break: "reci-\nprocity" -> "reciprocity".
    text = re.sub(r"-\n\s*", "", raw)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Drop lines that are nothing but a page number.
        if re.fullmatch(r"\d{1,4}", stripped):
            continue
        lines.append(stripped)
    return normalize_text(" ".join(lines))


def split_into_sections(text: str) -> dict[str, str]:
    """Best-effort split of cleaned full text into canonical sections. Returns a
    dict keyed by section name; missing sections are simply absent."""
    clean = normalize_text(text)
    if not clean:
        return {}
    # Find the start offset of each known heading.
    marks: list[tuple[int, str]] = []
    for name, pattern in SECTION_PATTERNS.items():
        match = re.search(rf"(?:^|\.\s|\s)({pattern})[:.\s]", clean, flags=re.IGNORECASE)
        if match:
            marks.append((match.start(1), name))
    if not marks:
        return {}
    marks.sort()
    sections: dict[str, str] = {}
    for i, (start, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(clean)
        body = clean[start:end].strip()
        # Strip the heading word itself off the front of the body.
        body = re.sub(rf"^({SECTION_PATTERNS[name]})[:.\s]+", "", body, flags=re.IGNORECASE).strip()
        if body and name not in sections:
            sections[name] = body
    return sections


def split_sentences(text: str) -> list[str]:
    clean = normalize_text(text)
    if not clean:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", clean) if part.strip()]


def pick_relevant_excerpt(text: str, terms: list[str], max_chars: int = 600, max_sentences: int = 3) -> str:
    """Pick up to a few sentences that mention any of `terms`, falling back to the
    first sentences when nothing matches. Grounded summaries are built from this."""
    sentences = split_sentences(text)
    if not sentences:
        return ""
    lowered_terms = [t.lower() for t in terms if t]
    chosen: list[str] = []
    if lowered_terms:
        for sentence in sentences:
            low = sentence.lower()
            if any(term in low for term in lowered_terms):
                chosen.append(sentence)
            if len(chosen) >= max_sentences:
                break
    if not chosen:
        chosen = sentences[:max_sentences]
    excerpt = " ".join(chosen)
    return excerpt[:max_chars].strip()


def cache_name_for_url(url: str) -> str:
    """Stable, filesystem-safe cache filename for a PDF URL."""
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return f"{digest}.pdf"


# --------------------------------------------------------------------------- #
# IO / network layer -- isolated so tests can monkeypatch it. pypdf is an
# OPTIONAL dependency: the core package installs with PyYAML only, and these
# functions degrade to "" when pypdf is missing or extraction fails.
# --------------------------------------------------------------------------- #
def _download(url: str, mailto: str = "", timeout: int = 60) -> bytes:
    if mailto:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}mailto={urllib.parse.quote(mailto)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        return b""


def extract_text_from_bytes(data: bytes) -> str:
    """Extract text from PDF bytes using pypdf if available. Returns "" if pypdf
    is not installed, the blob is not a PDF, or extraction fails."""
    if not looks_like_pdf(data):
        return ""
    try:
        import io

        from pypdf import PdfReader  # optional dependency
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception:
        return ""
    return clean_pdf_text("\n".join(pages))


def fetch_pdf_text(
    source: str,
    mailto: str = "",
    cache_dir: str | Path | None = None,
) -> str:
    """Resolve `source` (a URL or local path) to cleaned full text.

    URLs are downloaded (and cached under cache_dir when given); local paths are
    read directly. Returns "" on any failure so callers can fall back to the
    abstract."""
    if not source:
        return ""
    text_source = normalize_text(source)
    is_url = text_source.lower().startswith(("http://", "https://"))

    if not is_url:
        path = Path(text_source)
        if not path.is_file():
            return ""
        try:
            return extract_text_from_bytes(path.read_bytes())
        except OSError:
            return ""

    cache_path: Path | None = None
    if cache_dir:
        cache_path = Path(cache_dir) / cache_name_for_url(text_source)
        if cache_path.is_file():
            try:
                return extract_text_from_bytes(cache_path.read_bytes())
            except OSError:
                pass

    data = _download(text_source, mailto=mailto)
    if not looks_like_pdf(data):
        return ""
    if cache_path is not None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(data)
        except OSError:
            pass
    return extract_text_from_bytes(data)
