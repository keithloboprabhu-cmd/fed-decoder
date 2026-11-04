"""TF-IDF search over statements (paragraph level). Local, free, fast."""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from fed_decoder.data import store


@lru_cache(maxsize=1)
def _index():
    from sklearn.feature_extraction.text import TfidfVectorizer

    stm = store.statements()
    rows = []
    for d, t in zip(stm["meeting_date"], stm["statement_text"]):
        for k, para in enumerate(t.split("\n\n")):
            if len(para) > 40:
                rows.append({"meeting_date": d, "para": k, "text": para})
    df = pd.DataFrame(rows)
    vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english", min_df=1)
    X = vec.fit_transform(df["text"])
    doc_vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
    D = doc_vec.fit_transform(stm["statement_text"])
    return df, vec, X, doc_vec, D


def search_statements(query: str, k: int = 5, year: int | None = None) -> list[dict]:
    df, vec, X, _, _ = _index()
    q = vec.transform([query])
    sims = (X @ q.T).toarray().ravel()
    if year:
        sims = np.where(df["meeting_date"].dt.year == year, sims, -1)
    top = np.argsort(-sims)[:k]
    return [
        {"meeting_date": str(df["meeting_date"].iloc[i].date()), "score": round(float(sims[i]), 3), "text": df["text"].iloc[i]}
        for i in top
        if sims[i] > 0
    ]


def most_similar_statement(text: str, exclude_date=None) -> tuple[pd.Timestamp, float]:
    """For pasted statements: the closest past statement to diff against."""
    _, _, _, doc_vec, D = _index()
    stm = store.statements()
    sims = (D @ doc_vec.transform([text]).T).toarray().ravel()
    if exclude_date is not None:
        sims = np.where(stm["meeting_date"] == pd.Timestamp(exclude_date), -1, sims)
    i = int(np.argmax(sims))
    return stm["meeting_date"].iloc[i], float(sims[i])
