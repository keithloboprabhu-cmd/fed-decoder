# Fed Decoder eval report

Generated 2026-11-04 13:49 UTC. Keys available: Gemini=yes, Groq=yes. Cards in `cards/`: {'gemini': 227}.

## 1. Extraction vs ground truth

Ground truth: decision and range from FRED target series; votes and dissenters parsed from each statement's voting paragraph.

| Extractor | Meetings | Direction | Size (bp) | Target range | Vote count | Dissenters |
|---|---|---|---|---|---|---|
| Rules-based (regex) | 227 | 100.0% | 100.0% | 98.7% | 100.0% | 100.0% |
| LLM cards | 227 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |

Vote and dissenter accuracy for the rules extractor is not independent: it uses the same vote parser that builds the answer key. Range misses are statements that state no target (liquidity or balance-sheet announcements).

## 2. Tone validity

| Check | Result |
|---|---|
| Dictionary tone vs next meeting's rate change | Pearson 0.45, Spearman 0.42 (n=226) |
| LLM card tone vs next meeting's rate change | Pearson 0.59, Spearman 0.58 (n=226) |
| Agreement with hand labels (30 statements) | dictionary Spearman 0.54, LLM Spearman 0.64 (n=30) |
| Gemini vs Groq | Pearson 0.97, mean abs diff 0.58, within 0.5: 66.7% (n=6) |
| LLM vs dictionary model | Pearson 0.70, sign agreement 63.4% (n=227) |

## 3. Consistency (20 statements x 3 runs)

- Dictionary model: deterministic, spread 0.00 on 20 statements.
- LLM: mean range 0.28, max range 1.00, mean std 0.13, identical across runs 50.0% (n=20, temperature 0.7)

## 4. Grounding

| Cards | n | Number check pass | Quote check pass |
|---|---|---|---|
| llm | 227 | 100.0% | 100.0% |
| rules | 0 | n/a | n/a |

LLM judge (Groq judging Gemini claims): 100.0% of 3 sampled claims supported; hand-label validation pending (`evals/hand_labels_claims.csv`)

## 5. Impact math

400 cases (mortgage, auto, HELOC, credit card across balances, rates and moves) vs an independent closed-form amortization: max absolute error $0.0000. Exact to the cent: yes.

## 6. Forecast backtest

Walk-forward, 2004-09-21 to 2026-09-16, 186 meetings.

| Model | Hit rate |
|---|---|
| Logistic (Taylor gap, SEP gap, tone, momentum) | 76.9% |
| Baseline: always "no change" | 69.9% |

The model beats the baseline. On meetings where the Fed actually moved, the model called the direction 64.3% of the time (the baseline gets 0% of those).

## 7. Chat (30 known-answer questions, 10 adversarial)

| Mode | Accuracy | Adversarial pass | Mean latency | Fell back to rules |
|---|---|---|---|---|
| rules | 100.0% | 100.0% | 0.07s | n/a |
| gemini | 93.3% | 100.0% | 15.04s | 10.0% |
| groq | not measured: 100.0% of answers fell back to rules (free quota exhausted) | | | 100.0% |

An LLM mode's accuracy includes answers that fell back to rules; a mode is reported only when most answers came from the model.

## 8. Provider comparison

Extraction and grounding are scored only on the cards a provider actually produced ("cards made").

| Provider | Cards made / asked | Direction | Size | Range | Votes | Grounding pass | Mean latency | Fell back |
|---|---|---|---|---|---|---|---|---|
| gemini | 20 / 20 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 31.00s | 0.0% |
| groq | 5 / 20 | 100.0% | 100.0% | 100.0% | 100.0% | 80.0% | 100.39s | 75.0% |
| rules | 20 / 20 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.00s | 0.0% |

Logged LLM calls this far: 638 ok ({'gemini': 552, 'groq': 86}), Gemini-to-Groq fallbacks 0.0% (evals pin one provider per call), 221 rate-limit events, 43 guardrail failures.


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

| Version | Cards | Change-quote precision | Validation pass |
|---|---|---|---|
| before_no_diff | 19 | 83.3% | 100.0% |
| after_with_diff | 20 | 100.0% | 100.0% |
