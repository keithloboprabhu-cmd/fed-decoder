"""Statement redlines, computed with difflib (no LLM)."""
from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass

_TOKEN = re.compile(r"\s+|[^\s]+")
# Sentence boundary: ., ? or ! then a capital, but not after an initial
# ("Michelle W. Bowman"), "U.S.", "Jr." and similar abbreviations.
_SENT = re.compile(r"(?<=[.?!])(?<!\s[A-Z]\.)(?<!U\.S\.)(?<!Jr\.)(?<!Mr\.)(?<!Ms\.)(?<!Dr\.)(?<!St\.)\s+(?=[A-Z\"\u201c])")


@dataclass
class DiffOp:
    op: str  # equal | delete | insert
    text: str


@dataclass
class Change:
    """A sentence-level change; quotes come verbatim from the statements."""

    kind: str  # added | removed | modified
    old: str
    new: str

    def to_dict(self) -> dict:
        return asdict(self)


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text)


def redline(old: str, new: str) -> list[DiffOp]:
    """Word-level diff. Deletions are struck, insertions highlighted in the UI."""
    a, b = tokenize(old), tokenize(new)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops: list[DiffOp] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            ops.append(DiffOp("equal", "".join(a[i1:i2])))
        else:
            if i2 > i1:
                ops.append(DiffOp("delete", "".join(a[i1:i2])))
            if j2 > j1:
                ops.append(DiffOp("insert", "".join(b[j1:j2])))
    # merge adjacent ops of the same type and absorb whitespace-only changes
    merged: list[DiffOp] = []
    for op in ops:
        if op.op != "equal" and not op.text.strip():
            op = DiffOp("equal", op.text) if op.op == "insert" else None  # drop deleted whitespace
            if op is None:
                continue
        if merged and merged[-1].op == op.op:
            merged[-1].text += op.text
        else:
            merged.append(op)
    return merged


def sentences(text: str) -> list[str]:
    out = []
    for para in text.split("\n"):
        out.extend(s.strip() for s in _SENT.split(para) if s.strip())
    return out


def sentence_changes(old: str, new: str, min_ratio: float = 0.5) -> list[Change]:
    """Align sentences and report what was added, removed, or reworded."""
    a, b = sentences(old), sentences(new)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    changes: list[Change] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        olds, news = a[i1:i2], b[j1:j2]
        used = set()
        for n in news:
            best, best_r = None, 0.0
            for k, o in enumerate(olds):
                if k in used:
                    continue
                r = difflib.SequenceMatcher(None, o, n).ratio()
                if r > best_r:
                    best, best_r = k, r
            if best is not None and best_r >= min_ratio:
                used.add(best)
                changes.append(Change("modified", olds[best], n))
            else:
                changes.append(Change("added", "", n))
        for k, o in enumerate(olds):
            if k not in used:
                changes.append(Change("removed", o, ""))
    return changes


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, tokenize(a), tokenize(b), autojunk=False).ratio()


def changed_fraction(old: str, new: str) -> float:
    return round(1.0 - similarity(old, new), 3)
