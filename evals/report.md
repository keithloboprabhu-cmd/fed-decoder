# Fed Decoder eval report

Generated 2026-11-04 00:31 UTC. Keys available: Gemini=no, Groq=no. Cards in `cards/`: {'rules': 227}.

> **No LLM keys were available for this run.** Every section that needs Gemini or Groq is marked *not run*. Add free-tier keys to `.env`, run `python scripts/build_cards.py` and then `python evals/run.py` to fill them in.

## 1. Extraction vs ground truth

Ground truth: decision and range from FRED target series; votes and dissenters parsed from each statement's voting paragraph.

| Extractor | Meetings | Direction | Size (bp) | Target range | Vote count | Dissenters |
|---|---|---|---|---|---|---|
| Rules-based (regex) | 227 | 100.0% | 100.0% | 98.7% | 100.0% | 100.0% |
| LLM cards | 0 | not run | | | | |

Vote and dissenter accuracy for the rules extractor is not independent: it uses the same vote parser that builds the answer key. Range misses are statements that state no target (liquidity or balance-sheet announcements).

## 2. Tone validity

| Check | Result |
|---|---|
| Dictionary tone vs next meeting's rate change | Pearson 0.45, Spearman 0.42 (n=226) |
| LLM card tone vs next meeting's rate change | not run |
| Agreement with hand labels (30 statements) | pending: fill `evals/hand_labels_tone.csv` |
| Gemini vs Groq | not run |
| LLM vs dictionary model | not run |

## 3. Consistency (20 statements x 3 runs)

- Dictionary model: deterministic, spread 0.00 on 20 statements.
- LLM: not run

## 4. Grounding

| Cards | n | Number check pass | Quote check pass |
|---|---|---|---|
| llm | 0 | n/a | n/a |
| rules | 227 | 43.6% | 100.0% |

LLM judge (Groq judging Gemini claims): not run (needs Gemini cards and a Groq key)

## 5. Impact math

400 cases (mortgage, auto, HELOC, credit card across balances, rates and moves) vs an independent closed-form amortization: max absolute error $0.0000. Exact to the cent: yes.

## 6. Forecast backtest

Walk-forward, 2004-09-21 to 2026-09-16, 186 meetings.

| Model | Hit rate |
|---|---|
| Logistic (Taylor gap, SEP gap, tone, momentum) | 75.3% |
| Baseline: always "no change" | 69.9% |

The model beats the baseline. On meetings where the Fed actually moved, the model called the direction 64.3% of the time (the baseline gets 0% of those).

## 7. Chat (30 known-answer questions, 10 adversarial)

| Mode | Accuracy | Adversarial pass | Mean latency | Fell back to rules |
|---|---|---|---|---|
| rules | 100.0% | 100.0% | 0.08s | n/a |

## 8. Provider comparison

| Provider | n | Direction | Size | Range | Votes | Grounding pass | Mean latency | Fell back |
|---|---|---|---|---|---|---|---|---|
| gemini | not run | | | | | | | |
| groq | not run | | | | | | | |
| rules | 20 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.00s | 0.0% |

## Before / after

**Rules extractor: pick the action sentence, accept spaced fractions ("1 3/4"), infer direction from a changed range.** Before = commit `e670b22`, scored on the same 227 meetings.

| Version | Direction | Size (bp) | Target range |
|---|---|---|---|
| Before | 98.7% | 97.8% | 85.5% |
| After | 100.0% | 100.0% | 98.7% |

**Rules baseline: drop the voting paragraph before tone scoring** (dissenters' reasons, e.g. "preferred to lower the target range", were being scored as the Committee's tone).

| Version | Spearman vs next rate change | Pearson |
|---|---|---|
| Before (whole statement) | 0.438 | 0.462 |
| After (voting paragraph excluded) | 0.423 | 0.453 |

This change made the predictive correlation slightly *worse*: dissenters' stated preferences carry information about the next move. It is kept because the tone quotes shown to users must be the Committee's own words, not a dissenter's.

**LLM cards: add the code-computed diff to the card inputs.**

Not run (needs an LLM key).
