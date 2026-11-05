"""Force each provider to fail and show what a reader gets. Live: uses the real keys.

    python evals/failover_check.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fed_decoder.chat import agent  # noqa: E402

Q = "What's the fed funds rate right now?"
for forced in ["", "gemini", "groq", "gemini,groq"]:
    os.environ["FORCE_PROVIDER_FAIL"] = forced
    a = agent.answer(Q, use_cache=False)
    shown = a.text.replace("\n", " ")[:110]
    print(f"| {forced or 'none'} | {a.status} | {a.provider} {a.model} | {shown} | {(a.saved or '').replace(chr(10), ' ')[:90]} |")
