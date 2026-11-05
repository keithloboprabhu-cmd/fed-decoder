PY ?= python

.PHONY: test eval eval-ask primer

test:
	$(PY) -m pytest -q tests

eval:
	$(PY) evals/run.py

# Ask suite (live: uses the free-tier API keys and live data). Writes evals/ask_report.md.
eval-ask:
	$(PY) evals/ask_eval.py --label after

primer:
	$(PY) scripts/build_primer.py
