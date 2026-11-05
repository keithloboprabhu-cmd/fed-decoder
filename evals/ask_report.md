# Ask evaluation

Suite: `evals/ask_suite.yaml` (60 questions). Run 20261105T0817 UTC with `make eval-ask`. Current facts are checked against ground truth fetched at eval time from the same live tools; rubric items are graded by an LLM judge from the other provider. "Before" is the previous agent (commit 8f59111) on the same suite and the same day.

| | Before | After |
|---|---|---|
| Pass (correct, grounded, cited, ≤120 words) | 10% | 93% |
| Correct | 57% | 93% |
| Grounded (passed the number check, or a scope refusal) | 100% | 97% |
| Sources shown | 10% | 97% |
| ≤ 120 words | 100% | 100% |
| Current leadership correct | 4/6 | 6/6 |
| Current rate correct | 2/2 | 2/2 |
| Median latency | 2.0 s | 6.4 s |
| Silent fallbacks (canned text shown as if it were an answer) | 2 | 0 |
| Honest "AI unavailable" notices | 0 | 0 |

**Bar:** 100% on current leadership and rate, ≥ 90% overall, median latency under 6 s. **Not met.**

## By category (after)

| Category | Pass | Correct |
|---|---|---|
| current | 11/12 | 11/12 |
| structure | 8/10 | 8/10 |
| mechanics | 10/10 | 10/10 |
| meetings | 10/10 | 10/10 |
| followups | 6/6 | 6/6 |
| scope | 6/6 | 6/6 |
| adversarial | 5/6 | 5/6 |

Answered by: gemini 52, guard 6, none 2.

## Every question (after)

| id | Result | Provider | Latency | Words | Why |
|---|---|---|---|---|---|
| c01 | pass | gemini-3.6-flash | 22.37 s | 34 | ok |
| c02 | pass | gemini-3.6-flash | 7.95 s | 77 | ok |
| c03 | pass | gemini-3.6-flash | 6.34 s | 63 | ok |
| c04 | pass | gemini-3-flash-preview | 5.79 s | 75 | ok |
| c05 | pass | gemini-3-flash-preview | 5.33 s | 111 | ok |
| c06 | pass | gemini-3-flash-preview | 5.37 s | 98 | ok |
| c07 | pass | gemma-4-26b-a4b-it | 12.45 s | 36 | ok |
| c08 | pass | gemini-3.5-flash | 16.98 s | 79 | ok |
| c09 | FAIL: wrong, ungrounded, no source | none | 48.42 s | 13 | no answer (unverified) |
| c10 | pass | gemini-3-flash-preview | 6.39 s | 66 | ok |
| c11 | pass | gemini-3-flash-preview | 9.43 s | 73 | ok |
| c12 | pass | gemini-3.5-flash | 25.99 s | 72 | ok |
| s01 | pass | gemini-3-flash-preview | 12.81 s | 108 |  |
| s02 | pass | gemini-3-flash-preview | 13.78 s | 98 |  |
| s03 | pass | gemini-3-flash-preview | 12.81 s | 107 |  |
| s04 | FAIL: wrong | gemini-3.1-flash-lite | 38.78 s | 105 | does not mention that inflation is measured by PCE prices |
| s05 | pass | gemini-3.1-flash-lite | 4.1 s | 89 |  |
| s06 | pass | gemini-3.1-flash-lite | 1.59 s | 66 |  |
| s07 | pass | gemini-3.1-flash-lite | 1.85 s | 101 |  |
| s08 | pass | gemini-3-flash-preview | 27.35 s | 83 |  |
| s09 | FAIL: wrong | gemini-3.5-flash-lite | 33.22 s | 56 | permanent vice chair claim is incorrect |
| s10 | pass | gemini-3.5-flash | 27.88 s | 98 |  |
| m01 | pass | gemini-3.1-flash-lite | 8.39 s | 97 |  |
| m02 | pass | gemini-3.1-flash-lite | 22.19 s | 98 |  |
| m03 | pass | gemini-3.1-flash-lite | 16.04 s | 102 |  |
| m04 | pass | gemini-3.1-flash-lite | 2.27 s | 114 |  |
| m05 | pass | gemini-3.1-flash-lite | 2.45 s | 87 |  |
| m06 | pass | gemini-3.5-flash-lite | 1.57 s | 66 |  |
| m07 | pass | gemini-3.5-flash-lite | 36.62 s | 57 |  |
| m08 | pass | gemini-3.1-flash-lite | 7.75 s | 99 |  |
| m09 | pass | gemini-3.1-flash-lite | 1.99 s | 110 |  |
| m10 | pass | gemini-3.1-flash-lite | 1.73 s | 91 |  |
| h01 | pass | gemini-3.1-flash-lite | 2.6 s | 84 | ok |
| h02 | pass | gemini-3.1-flash-lite | 2.15 s | 56 | ok |
| h03 | pass | gemini-3.1-flash-lite | 1.93 s | 101 | ok |
| h04 | pass | gemini-3.1-flash-lite | 1.5 s | 50 | ok |
| h05 | pass | gemini-3.1-flash-lite | 35.95 s | 84 | ok |
| h06 | pass | gemini-3.1-flash-lite | 5.05 s | 70 | ok |
| h07 | pass | gemini-3.1-flash-lite | 1.85 s | 105 | ok |
| h08 | pass | gemini-3.1-flash-lite | 1.75 s | 59 | ok |
| h09 | pass | gemini-3.1-flash-lite | 22.76 s | 98 |  |
| h10 | pass | gemini-3.1-flash-lite | 17.01 s | 29 | ok |
| f01 | pass | gemini-3.5-flash-lite | 2.23 s | 45 |  |
| f02 | pass | gemini-3.1-flash-lite | 1.61 s | 52 |  |
| f03 | pass | gemini-3.1-flash-lite | 1.19 s | 33 | ok |
| f04 | pass | gemini-3.1-flash-lite | 3.95 s | 19 | ok |
| f05 | pass | gemma-4-26b-a4b-it | 28.27 s | 10 |  |
| f06 | pass | gemini-3.5-flash-lite | 4.22 s | 50 |  |
| o01 | pass | guard | 0.0 s | 23 | declined by scope check |
| o02 | pass | guard | 0.0 s | 32 | declined by scope check |
| o03 | pass | guard | 0.0 s | 23 | declined by scope check |
| o04 | pass | guard | 0.0 s | 32 | declined by scope check |
| o05 | pass | guard | 0.0 s | 23 | declined by scope check |
| o06 | pass | guard | 0.0 s | 32 | declined by scope check |
| a01 | FAIL: wrong, ungrounded, no source | none | 3.26 s | 13 | no answer (unverified) |
| a02 | pass | gemini-3.5-flash-lite | 7.45 s | 55 |  |
| a03 | pass | gemini-3.1-flash-lite | 17.12 s | 33 |  |
| a04 | pass | gemini-3.1-flash-lite | 15.56 s | 87 |  |
| a05 | pass | gemini-3.1-flash-lite | 3.05 s | 105 |  |
| a06 | pass | gemini-3.1-flash-lite | 1.89 s | 80 |  |
