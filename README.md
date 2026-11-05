# Fed Decoder

Federal Reserve decisions in plain English. Pick any FOMC meeting since 2000 (or paste a statement) and get the decision, a redline against the previous statement, a hawkish-to-dovish tone reading with the quotes behind it, what it means for borrowers, savers and workers, what it means for the economy, and a light, backtested forecast of the next move.

![Fed Decoder: the rate staircase and the verdict for the July 29, 2026 meeting](docs/screenshot.png)

**Live app:** _deploy link goes here once published on Streamlit Community Cloud (see [Deploy](#deploy-free))._

## How it feels to use

One screen, read top to bottom in about five seconds:

1. **The rate staircase.** The Fed's target rate since 2000 as a step chart: hikes are red up-steps, cuts blue down-steps, holds flat gray. Click, drag or use the arrow keys to pick a meeting; presets jump to the 2000s, 2008, 2020, the 2022 hikes, or the last three years (the default).
2. **The verdict.** An eight-word headline ("Held at 3.50–3.75%. Three wanted a hike."), then three facts: the rate with its move, the vote as dots (dissenters hollow, hover for who wanted what), and the tone on a dovish-to-hawkish stripe with the previous six meetings as faint ticks. For past meetings, a chip jumps to what the Fed did next.
3. **Four answers**, one sentence and one small picture each, opening one at a time: *Why* (the data the Fed cited), *What changed* (the redline against the last statement), *For you* (pick credit card, savings, car loan, mortgage or job hunting; computed in code, never stored, never sent to an AI), and *What's next* (backtested odds for the next meeting).
4. **Ask**, a slim bar at the bottom. Suggested questions appear when you focus it, and answers open in a side panel (a bottom sheet on phones), drawn from tools over the statements and data with every number checked.

On the latest meeting a live strip shows the days to the next decision and the latest CPI, unemployment and 10-year yield (tap for a sparkline). Meetings are shareable with `?m=YYYY-MM-DD`.

The design is deliberately plain: off-white, ink, and color only where it means something (red = hike or hawkish, blue = cut or dovish, always paired with an arrow, a shape or a word). JetBrains Mono for every rate, percent and vote; Inter Tight for words. Jargon gets a dotted underline with a one-line definition. The first 1440×900 screen shows at most 60 words, and a Playwright check in CI enforces it (`tests/e2e/word_budget.js`). See [docs/REDESIGN.md](docs/REDESIGN.md) for before and after.

## How the AI works

Ask is a small tool-using agent (`fed_decoder/chat/agent.py`), not a search box over saved answers.

1. **Every request** carries today's date and time (Eastern), a note that the model's memory is out of date, and a 1,500-word primer (`knowledge/primer.md`). The primer is written from 26 official Fed pages, snapshotted in `knowledge/sources/`, cites them section by section, and holds no current names or rates. A monthly workflow re-fetches those pages and opens a pull request when one changes.
2. **The model plans and calls tools**, up to 4 rounds, several at once. Leadership, rates, data and recent events must come from a tool:

   | Tool | Source | Cache |
   |---|---|---|
   | `fed_leadership` | federalreserve.gov Board and FOMC pages: chair, vice chairs, governors, this year's voters and alternates, rotation | 12 h |
   | `fomc_calendar` | federalreserve.gov FOMC calendar | 24 h |
   | `get_meeting`, `search_statements`, `diff_statements`, `notable_meetings` | the statement archive and decoder cards | — |
   | `fred_search`, `fred_series` | FRED, any series (full search needs a free `FRED_API_KEY`) | 1 h |
   | `bls_latest` | BLS API v2 (FRED fallback when BLS's keyless limit runs out) | 1 h |
   | `treasury_yields` | Treasury daily par yield curve | 1 h |
   | `fed_feed` | Fed RSS: monetary releases, speeches, testimony | 15 min |
   | `web_search` | Google Search grounding (Gemma 4 / Gemini), then Groq browser search, then Wikipedia | 1 h |
   | `fetch_page` | allowlisted official sites and major outlets only | 6 h |
   | `calc`, `payment_impact`, `forecast_next` | code (the model never does arithmetic) | — |

3. **Providers:** Gemini Flash models, then Gemma 4 on the same free key, then Groq `gpt-oss-120b`. A provider that fails mid-answer hands its tool results to the next one.
4. **Checks before anything is shown:** every number must appear in a tool result or the primer, and quotes must be verbatim. A failure gets one correction pass that can call tools again. Links the model made up are removed.
5. **The answer** is at most 120 words (300 with "More detail"), answer-first. Current facts carry "as of" dates and links, with up to 3 source chips, 3 follow-up questions, and "Using live data · model · N sources". The last 6 turns are kept for follow-ups.
6. **Never silent:** if no AI can answer, the panel says "The AI is temporarily unavailable" (or "Daily AI limit reached; showing saved answers"), and anything shown instead is labelled saved content. A hidden Status page (footer link, `?page=status`) shows provider health, quota use, cache hit rate and the last 20 errors.

### Ask eval (60 questions, `make eval-ask`)

Current facts are checked against ground truth fetched at eval time from the same live tools, meetings against the archive, and rubric items by an LLM judge from the other provider. Full table: [`evals/ask_report.md`](evals/ask_report.md); diagnosis of the old version: [`docs/AI_DIAGNOSIS.md`](docs/AI_DIAGNOSIS.md).

| | Before (old agent) | After |
|---|---|---|
| Pass (correct, grounded, sourced, ≤ 120 words) | 10% | **93%** |
| Correct | 57% | 93% |
| Sources shown | 10% | 97% |
| Current leadership | 4/6 | **6/6** |
| Current rate | 2/2 | **2/2** |
| Median latency | 2.0 s | 6.4 s |

Bar: 100% on leadership and rate (met), ≥ 90% overall (met), median latency under 6 s (**not met: 6.4 s**). The free Flash models allow 20 requests a day each, so after the first ~50 questions of a day, answers come from slower models (Gemma 4, Flash-Lite). The old agent was faster because it mostly answered from memory without tools, which is how it got the chair, the voters and the next meeting date wrong.

## What it does

- **Decode a meeting.** 227 statements, February 2000 to October 2026, each with a pre-built decoder card (`cards/`). Viewing a past meeting makes zero API calls.
  - *Decision:* direction, size in basis points, target range, vote, dissenters.
  - *What changed:* a word-level redline against the previous statement. Deletions are struck, additions highlighted, and hovering a change shows what it means.
  - *Tone:* a dial from dove (−2) to hawk (+2), with the sentences that drive it.
  - *For you:* one sentence and one computed number each for borrowers, mortgages, savers and workers. The mortgage card says that mortgages track the 10-year Treasury, not fed funds.
  - *For you:* your housing situation, balances, savings, income range and state give your own monthly impact, the share of income, your local unemployment rate, and what the next move would mean. Computed in code; the answers stay in your browser tab and are never stored or logged. Amounts, income and state are never sent to an AI; the opt-in AI note sees only broad labels. No login. Gender isn't asked because no effect computed here depends on it.
  - *For the country:* inflation, jobs, growth, markets and the dollar, from FRED.
  - *What's next:* model probabilities for hold, cut or hike, shown next to the backtest against a "no change" baseline.
- **Ask about a meeting.** The bottom bar, answered with tools over the corpus and the data: `get_meeting`, `search_statements` (TF-IDF), `diff_statements`, `get_series`, `payment_impact` and `forecast_next`. Every number in an answer is checked against the tool results.
- **Rate staircase.** The fed funds target since 2000 as a navigable step chart (`fed_decoder/ui/staircase/`, a small hand-written Streamlit component).

## Three findings

1. **Mortgages don't follow the Fed on decision day.** On the 75 days since 2000 when the Fed moved rates, the 10-year Treasury moved in the same direction only 41% of the time. Its median move was 4 bp against a median policy move of 25 bp. The 2-year, the most Fed-sensitive market rate, matched the direction 56% of the time. Markets usually price the move in before the meeting, which is why the mortgage card points to the 10-year.
2. **A small model beats "no change", but only on accuracy.** The walk-forward logistic forecast (Taylor-rule gap, SEP gap, statement tone, momentum) calls the next decision right 77% of the time, against 70% for always predicting "no change". It gets the direction right on 64% of the meetings where the Fed actually moved. A class-balanced version catches more moves (80%) but loses to the baseline overall (65%), so it was dropped.
3. **The LLM reads tone better than the word list, and dissents carry signal too.** Gemini's tone scores predict the next meeting's rate change noticeably better than the dictionary model (Spearman 0.58 vs 0.42 across 226 meetings), and the two agree in sign only 63% of the time. For the dictionary model, leaving dissenters' stated preferences out of the score (so the dial reflects only the Committee's words) slightly *lowers* the correlation (0.438 to 0.423). An explicit "dissent lean" feature did not improve the forecast, though (75% vs 77%), so that extra signal is real but small.

## How it runs for $0

| Piece | Free service | How we stay inside the limits |
|---|---|---|
| LLM, primary | Google Gemini API free tier (AI Studio key, no card): Flash models, then Gemma 4 on the same key | Per-model rotation: a model that hits its daily cap is skipped until midnight Pacific, one that hits a per-minute limit or a 503 rests for a minute; 15 s timeout per chat call |
| LLM, fallback | Groq free tier, `openai/gpt-oss-120b` | Token-per-minute budget under the 8,000 TPM cap; short tool results and a trimmed primer for Groq |
| No AI available | Decoder cards and Ask say so plainly | Cards fall back to rules-based text; Ask shows "The AI is temporarily unavailable" plus clearly labelled saved archive content |
| Decoder cards | Pre-generated once by `scripts/build_cards.py` (about 230 calls, resumable) | Viewing a meeting makes zero calls |
| Ask | Live, tool-using | Answer cache (6 hours for anything time-sensitive), live-tool caches (15 min to 24 h), 15 questions per visit, per-provider daily budgets (`GEMINI_DAILY_BUDGET`, `GROQ_DAILY_BUDGET`) after which it shows "Daily AI limit reached; showing saved answers", last 6 turns kept |
| Data | federalreserve.gov, FRED, BLS, Treasury yield-curve XML, Fed RSS feeds (no keys needed; optional free FRED and BLS keys) | Polite scraper (1 s delay, cached HTML); every live tool has a timeout and a cache |
| Refresh | GitHub Actions every 2 hours, watching the Fed's official RSS feed (`/feeds/press_monetary.xml`) | Full update only when a new statement appears (scheduled or emergency); FRED data once a day; at most 10 new cards per run |
| Hosting | Streamlit Community Cloud | Keys in Streamlit secrets |

Never enable billing on either provider. Model IDs and rate settings live in `fed_decoder/config.py` and can be overridden with environment variables (`ASK_GEMINI_MODELS`, `GEMINI_MODEL`, `GROQ_MODEL`, `GEMINI_RPM`, `GROQ_RPM`, `GEMINI_DAILY_BUDGET`, `GROQ_DAILY_BUDGET`). Free-tier limits change, so check them in each console before deploying.

**Privacy.** Gemini's free tier may use inputs to improve Google's models, so the app sends only public text: Fed statements, data, and questions about the Fed. The Ask bar says "Don't enter personal information."

## Design rules

- **Numbers come from code.** Rates, dates, votes, payments, forecasts and statistics are computed in Python. The displayed decision always comes from the ground truth. The model's own extraction is stored separately (`llm_decision`) and used only for evals.
- **Every claim is grounded.** Any number in LLM output that isn't in the context or tool results fails the guardrail (`fed_decoder/llm/guardrail.py`). A failure gets one retry with the error fed back. If the retry also fails, a decoder card uses rules-based text, and Ask says it couldn't verify an answer rather than show one. Quotes must appear verbatim in the statement.
- **Never fail silently.** Gemini, then Groq. When neither can answer, the reader is told so, and anything shown instead is labelled as saved content, not an AI answer. `FORCE_PROVIDER_FAIL=gemini,groq` demonstrates it.
- **Scope.** The chat refuses personal investment advice and off-topic questions. Pasted text is fenced as data, and the system prompt says to ignore instructions inside it.

## Status of the LLM parts

- **Cards:** all 227 meetings have a validated Gemini-written card. Most come from `gemini-3.5-flash-lite`, which had by far the largest free daily quota; a few come from `gemini-3.5-flash`, `gemini-3.6-flash`, `gemini-3-flash-preview` and `gemini-flash-lite-latest`. Each card records its model. The displayed decision numbers are always the code-computed ones.
- **Live chat:** verified against the live Gemini API, including multi-turn function calling (Gemini 3 thought signatures are replayed).
- **Groq:** verified live (strict JSON-schema output and tool calls), but its free tier caps `gpt-oss-120b` at 8,000 tokens per minute and **200,000 tokens per day**, about 30 decoder cards a day. Groq rows in the report are therefore partial; rerun `python evals/run.py` on a later day to fill them in (successful outputs are cached in `evals/runs/`, so nothing is spent twice).
- **Hand labels pending:** fill `evals/hand_labels_tone.csv` (30 statements) and `evals/hand_labels_claims.csv` (20 claims), then rerun the evals.
- **In-sample caveat:** the regex extractor and the chat scope check were fixed against the same meetings and questions they are scored on, so their 100% means "no known misses", not a generalization estimate. Rules-based vote and dissenter accuracy is also not independent of the answer key, because both use the same vote parser.

### Free-tier limits we hit (checked November 2026)

| Provider | Limit that binds | What the app does |
|---|---|---|
| Gemini | 20 requests per day **per model** for the Flash models (Flash-Lite allows far more); 503 "high demand" comes and goes | Tries `gemini-3.5-flash`, then `3.6-flash`, `3-flash-preview`, `3.5-flash-lite`, `flash-lite-latest`; a model out of daily quota is skipped until midnight Pacific |
| Groq `gpt-oss-120b` | 8,000 tokens/min, 200,000 tokens/day, 1,000 requests/day | Sliding token-per-minute budget, low reasoning effort |
| Both | | App-wide daily chat budget (`DAILY_LLM_BUDGET`, default 80 calls) before switching to cached and rules-based answers |

`gemini-2.5-flash` is closed to new API users, so it is no longer the default.

To rebuild cards with your own keys:

```bash
cp .env.example .env
```

Add free-tier keys to `.env`, then:

```bash
python scripts/build_cards.py
```

It stops when every provider is out of quota and resumes on the next run.

## Staying current

New meetings arrive on their own:

1. **Every 2 hours** a GitHub Action reads the Fed's official press-release RSS feed. A new FOMC statement (scheduled or emergency) triggers the full update: statement, FRED data, answer key, forecast and an AI-written card. It commits to this branch, and Streamlit Community Cloud redeploys the app.
2. **Between runs**, the app itself checks the feed every 30 minutes. If a statement is newer than the archive, the live strip says so and decodes it on the spot.
3. **Once a day** the economic data (inflation, jobs, yields, loan rates) refreshes even without a new statement.

For the Action to write AI cards, add `GEMINI_API_KEY` and `GROQ_API_KEY` under the repo's **Settings → Secrets and variables → Actions** (otherwise it writes rules-based cards). Run it by hand from the **Actions** tab with "Run workflow".

## Data

| File | Contents | Source |
|---|---|---|
| `data/statements.parquet` | `meeting_date, statement_text, url` for 227 statements (scheduled and unscheduled) | federalreserve.gov calendars and historical pages |
| `data/ground_truth.parquet` | Decision, size, range, votes, dissenters per meeting (the eval answer key) | FRED target series for decisions; vote paragraph parsed in code |
| `data/fred.parquet` | 18 series: target bounds, EFFR, CPI, core PCE, unemployment, payrolls, 2y/10y, 30y mortgage, credit card, auto loan, SEP median, GDP, potential GDP, dollar, S&P 500 | FRED (every ID verified on download) |
| `data/sep_vintages.parquet` | SEP median fed funds path as published at each meeting since December 2015 | ALFRED vintages (no look-ahead) |
| `data/forecast_backtest.parquet` | Walk-forward predictions | computed |

Monthly and quarterly data are lagged by about one release when describing "the data at the time" of a meeting.

**Forecast details.** The Taylor rule is the Taylor (1993) variant: `i* = r* + π + 0.5(π − 2) + 0.5·gap`, with r* = 2.0, π = core PCE year over year, and gap = CBO output gap from `GDPC1`/`GDPPOT`. The SEP gap is the SEP median for the relevant year-end minus the current midpoint, set to 0 with a flag before 2016. The model is multinomial logistic regression with scikit-learn defaults. In the walk-forward backtest, each prediction is trained only on meetings whose outcome was already known. It is educational, not financial advice.

## Run locally

```bash
pip install -r requirements.txt
```

```bash
streamlit run app.py
```

Rebuild everything from scratch:

```bash
python scripts/fetch_statements.py && python scripts/fetch_fred.py && python scripts/build_data.py && python scripts/build_cards.py
```

Tests and evals:

```bash
python -m pytest -q tests
```

```bash
python evals/run.py
```

## Deploy (free)

1. Push this repo to GitHub (public).
2. On [share.streamlit.io](https://share.streamlit.io), create an app from the repo with main file `app.py`.
3. In the app's **Settings → Secrets**, add:
   ```toml
   GEMINI_API_KEY = "..."
   GROQ_API_KEY = "..."
   ```
4. In the GitHub repo's **Settings → Secrets and variables → Actions**, add the same keys so the refresh workflow can build cards for new meetings.

The app works with no keys at all: every page then runs in rules-based mode.

## Layout

```
app.py                     Streamlit app (one meeting screen + About)
fed_decoder/
  config.py                model names, limits, series IDs
  data/                    scraper, FRED client, ground truth, Parquet access
  analysis/                diff, tone dictionary, impact math, forecast, search
  llm/                     generate() interface, Gemini + Groq providers, router, guardrails
  cards/                   schema, context builder, LLM builder, rules builder, store
  chat/                    tools and agent (scope, cache, quota, fallback)
  ui/                      theme, components (verdict, votes, tone stripe, redline) and the staircase component
scripts/                   fetch_statements, fetch_fred, build_data, build_cards
evals/                     run.py, chat questions, hand-label templates, report.md
tests/                     unit tests, fake-provider tests, and the e2e word-budget check
```

## Eval report

<!-- EVAL-REPORT:START -->
Generated 2026-11-05 02:32 UTC. Keys available: Gemini=yes, Groq=yes. Cards in `cards/`: {'gemini': 227}.

### 1. Extraction vs ground truth

Ground truth: decision and range from FRED target series; votes and dissenters parsed from each statement's voting paragraph.

| Extractor | Meetings | Direction | Size (bp) | Target range | Vote count | Dissenters |
|---|---|---|---|---|---|---|
| Rules-based (regex) | 227 | 100.0% | 100.0% | 98.7% | 100.0% | 100.0% |
| LLM cards | 227 | 100.0% | 100.0% | 100.0% | 99.5% | 99.5% |

**Caveat on the LLM row:** the card prompt includes the code-computed decision facts, so this mostly measures whether the model copies them faithfully, not whether it can read the statement unaided. When the answer key itself was wrong (a heading parsed as two dissenters on 2014-09-17, since fixed), the model copied the error.


Vote and dissenter accuracy for the rules extractor is not independent: it uses the same vote parser that builds the answer key. Range misses are statements that state no target (liquidity or balance-sheet announcements).

### 2. Tone validity

| Check | Result |
|---|---|
| Dictionary tone vs next meeting's rate change | Pearson 0.45, Spearman 0.42 (n=226) |
| LLM card tone vs next meeting's rate change | Pearson 0.59, Spearman 0.58 (n=226) |
| Agreement with hand labels (30 statements) | dictionary Spearman 0.54, LLM Spearman 0.64 (n=30) |
| Gemini vs Groq | Pearson 0.97, mean abs diff 0.58, within 0.5: 66.7% (n=6) |
| LLM vs dictionary model | Pearson 0.70, sign agreement 63.4% (n=227) |

### 3. Consistency (20 statements x 3 runs)

- Dictionary model: deterministic, spread 0.00 on 20 statements.
- LLM: mean range 0.28, max range 1.00, mean std 0.13, identical across runs 50.0% (n=20, temperature 0.7)

### 4. Grounding

| Cards | n | Number check pass | Quote check pass |
|---|---|---|---|
| llm | 227 | 100.0% | 100.0% |
| rules | 0 | n/a | n/a |

LLM judge (Groq judging Gemini claims): 94.7% of 19 sampled claims supported; agreement with hand labels 100.0% (n=2)

### 5. Impact math

400 cases (mortgage, auto, HELOC, credit card across balances, rates and moves) vs an independent closed-form amortization: max absolute error $0.0000. Exact to the cent: yes.

### 6. Forecast backtest

Walk-forward, 2004-09-21 to 2026-09-16, 186 meetings.

| Model | Hit rate |
|---|---|
| Logistic (Taylor gap, SEP gap, tone, momentum) | 76.9% |
| Baseline: always "no change" | 69.9% |

The model beats the baseline. On meetings where the Fed actually moved, the model called the direction 64.3% of the time (the baseline gets 0% of those).

### 7. Chat (30 known-answer questions, 10 adversarial)

| Mode | Accuracy | Adversarial pass | Mean latency | Fell back to rules |
|---|---|---|---|---|
| rules | 100.0% | 100.0% | 0.07s | n/a |
| gemini | 93.3% | 100.0% | 15.04s | 10.0% |
| groq | not measured: 100.0% of answers fell back to rules (free quota exhausted) | | | 100.0% |

An LLM mode's accuracy includes answers that fell back to rules; a mode is reported only when most answers came from the model.

### 8. Provider comparison

Extraction and grounding are scored only on the cards a provider actually produced ("cards made").

| Provider | Cards made / asked | Direction | Size | Range | Votes | Grounding pass | Mean latency | Fell back |
|---|---|---|---|---|---|---|---|---|
| gemini | 20 / 20 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 31.00s | 0.0% |
| groq | 5 / 20 | 100.0% | 100.0% | 100.0% | 100.0% | 80.0% | 100.39s | 75.0% |
| rules | 20 / 20 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.00s | 0.0% |

Logged LLM calls this far: 638 ok ({'gemini': 552, 'groq': 86}), Gemini-to-Groq fallbacks 0.0% (evals pin one provider per call), 221 rate-limit events, 43 guardrail failures.


### Before / after

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
<!-- EVAL-REPORT:END -->

---

Not financial advice. Data: Federal Reserve, FRED. AI: Gemini / Groq free tiers.
