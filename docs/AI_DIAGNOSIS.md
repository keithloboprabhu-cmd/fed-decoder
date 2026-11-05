# Ask AI: diagnosis (November 5, 2026)

Done before changing any code. The five questions were run locally through `fed_decoder.chat.agent.answer()` with the cache off, using the real Gemini and Groq keys from `.env`.

**The live app was not checked.** There is no deployment yet: the README still says "deploy link goes here", so there are no Streamlit Cloud secrets to inspect. Everything below is from the local run, logs and code.

## Raw output

| Question | Provider | Tools called | Time | Answer | Verdict |
|---|---|---|---|---|---|
| Who's the current Fed chair? | Gemini | `fed_leadership` | 3.4 s | "The current Chair of the Federal Reserve is Kevin Warsh, who leads the Board of Governors." | Correct, but no source or date |
| What's the difference between the FOMC and the Board of Governors? | Gemini | none | 0.8 s | "The Board of Governors is a permanent, seven-member body in Washington… The FOMC is the specific group of twelve members—including all seven governors—that meets eight times a year…" | Correct from memory; no source |
| Why does the Fed exist? | Gemini | none | 0.8 s | "The Federal Reserve was created by Congress in 1913… dual mandate to pursue maximum employment and stable prices." | Correct from memory; no source |
| What's the fed funds rate right now? | Gemini | `get_series` ×2, `get_meeting` ×2 | **60.2 s** | "The Federal Reserve set the federal funds rate target range at "4-1/2 to 4-3/4 percent" at its November 2024 meeting…" | **Wrong.** It has been 3.75–4.00% since Oct 28, 2026, and `get_series` had returned that value. |
| Who votes on the FOMC this year? | Gemini | `fed_leadership` | 1.7 s | "The FOMC has 12 voting members: the seven members of the Board of Governors, the president of the New York Fed, and four regional bank presidents who serve on a rotating basis." | **Doesn't answer.** No names: no tool knows the 2026 voters. |

A second run of the rate question a minute later:

| Question | Provider | Answer |
|---|---|---|
| What's the fed funds rate right now? | **rules** (silent fallback) | "The Federal Reserve is the central bank of the United States, created in 1913. Its rate decisions are made by the FOMC: 12 voting members who hold 8 scheduled meetings a year…" |

This is the failure people actually see: a canned paragraph that ignores the question and looks like an answer. The "Automated answer (rules-based)" label had been removed from the UI in an earlier cleanup, so nothing on screen marks it as a fallback.

## Root causes

1. **Today's date is not in the prompt.** `SYSTEM` has no date, so "right now" means the model's training era. With current data in hand it still went looking for a 2024 meeting and quoted it. *Fix:* inject today's date and time (ET) into every request, and tell the model its memory is stale.

2. **Silent fallback to the FAQ/retrieval path.** `answer()` returns `rules_answer()` in three places: when `generate()` returns `None`, when `near_cap()` is true, and when the grounding retry fails. `rules_answer` matches keywords: anything with "fed" and "rate" gets the `FED_BASICS` paragraph, and anything else gets the closest statement paragraph. Neither says the AI was unavailable. *Fix:* no silent fallbacks. Show "The AI is temporarily unavailable" with clearly labelled saved content.

3. **The conversation is pinned to one provider after the first tool round.** After round 1 the loop sets `providers = [resp.provider]`, because Gemini tool messages carry provider-specific "thought signatures". If Gemini then returns a 429 (rate limit) or 503 (overloaded) in round 2, Groq is never tried; the log shows a Gemini 429 at 04:23:40 and no Groq attempt. *Fix:* on failure mid-loop, restart the turn on the next provider from the plain-text transcript (question plus tool results so far), which every provider can read.

4. **429s are swallowed, and the quota is far smaller than the code assumes.**
   - The Gemini free tier is **20 requests per day per model** (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, quotaValue 20, confirmed from the 429 body today).
   - Card building, evals and chat all share that one project. By 04:23 UTC every model in our fallback list (`3.5-flash`, `3.6-flash`, `3-flash-preview`, `3.5-flash-lite`, `flash-lite-latest`) was exhausted until about 08:00 UTC. `gemini-3.7-flash` and `3.8-flash` return 503 "high demand"; `gemini-2.5-flash-lite` returns 404 (retired).
   - Our `daily_counter.json` said 12, because it counts app-level calls and not per-model project use, so `near_cap()` never fired.
   - Over the log's lifetime: 228 Groq rate-limit events and 214 Groq failures (8,000 tokens per minute; one chat round with all tool specs is about 3–4k tokens), plus 24 Gemini 429/503 failures. Every one ended in the rules paragraph.
   - *Fix:* add the Gemma 4 models to the rotation. `gemma-4-26b-a4b-it` and `gemma-4-31b-it` are on separate quotas and support function calling (tested today: `gemma-4-26b-a4b-it` called `fed_leadership` in 1.9 s). Track quota per model from 429s, surface the failures on a status page, and send shorter tool specs to Groq.

5. **The backoff makes failures slow.** `_call_with_backoff` sleeps up to 12 s on every 429 before trying again, so each failing round costs 12 s or more. That is the main reason the rate question took 60 s. *Fix:* on a daily-quota 429, skip straight to the next model (the reset is hours away); only back off briefly on per-minute limits.

6. **Missing tools, and tools that reject obvious arguments.** Tools are called; there's no case of tools defined but never used.
   - No tool knows this year's FOMC voters: `fed_leadership` only scrapes the Board page.
   - `get_meeting("latest")` errors ("use YYYY-MM-DD").
   - `get_series` accepts only 18 hard-coded IDs.
   - There is no calendar tool, no BLS or Treasury data, no Fed speeches or testimony, no web search and no page fetch.
   - *Fix:* the Section 2 tool set.

7. **No sources, no primer.** Background answers (questions 2 and 3) come from model memory, with no citation and no "as of" date. *Fix:* a curated primer built from fetched federalreserve.gov pages, plus source chips on every answer.

8. **Keys on Streamlit Cloud: not verifiable here.** No deployment exists. `config._secret()` reads the environment, then `.env`, then `st.secrets`, so the keys will work once they're added to the app's secrets. To do at deploy time: add `GEMINI_API_KEY`, `GROQ_API_KEY` and `FRED_API_KEY` under the app's Settings → Secrets.

9. **No FRED API key.** `api.stlouisfed.org` returns 400 without one, so FRED search (any series, not a fixed list) needs a free key: https://fredaccount.stlouisfed.org/apikey. Until then, `fred_series` falls back to the keyless `fredgraph.csv` download for a known ID.

## Search grounding, tested today

| Model | Google Search grounding | Function calling | Both in one call |
|---|---|---|---|
| gemini-3.5 / 3.6 / 3-flash-preview / 3.5-flash-lite / flash-lite-latest | 429 (daily cap reached) | 429 | 429 |
| gemini-3.7-flash, gemini-3.8-flash | 429 | 503 (overloaded) | 429 |
| gemini-3.1-flash-lite | 429 (search has its own small quota) | OK (44 s) | 429 |
| gemma-4-26b-a4b-it | **OK: "Kevin Warsh", 8 sources** | **OK (1.9 s)** | 400 (not supported) |
| gemma-4-31b-it | 500 | OK (55 s) | 400 |
| Groq `openai/gpt-oss-20b` + `browser_search` | OK: "Kevin Warsh" (2.6 s, 2.6k tokens) | OK | n/a |
| Groq `openai/gpt-oss-120b` + `browser_search` | **Stale: "Jerome Powell"** (27k tokens) | OK | n/a |

Conclusions:
- Search grounding cannot share a call with our function tools on the free tier. `web_search` is its own tool that makes a separate grounded call: Gemma 4 or Gemini with Google Search first, then Groq `gpt-oss-20b` with `browser_search`, then Wikipedia.
- Web search can be stale (the 120B model above). Leadership, rates and data must come from official-source tools, and search is only for news and background.
