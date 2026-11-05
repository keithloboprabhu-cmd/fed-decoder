"""Fed Decoder visual system.

Warm and restrained. Newsreader carries the headlines and the Fed's own words
(statement text, quotes); Inter carries everything people read and every
interface label; figures use Inter's tabular numerals. Plex Mono is reserved
for the money columns people compare line by line.

Color has jobs, not moods: forest green = dovish / easing / the primary
action, terracotta = hawkish / removed text. Both always appear with a word.

Containers are rare on purpose. Structure comes from type scale, whitespace,
an occasional rule, and the left accent bar that marks a computed answer.
The only bordered shapes are the things you can press.
"""

IVORY = "#F8F7F3"     # page
SURFACE = "#FFFFFF"   # pressable things and the input
INK = "#252923"
MUTED = "#686C64"
FAINT = "#A2A49C"
LINE = "#E4E1D8"
GREEN = "#647C68"     # accent; dovish
GREEN_SOFT = "#E4EAE2"
TERRA = "#B0654A"     # supporting accent; hawkish
NEUTRAL = "#C9C5BA"   # midpoint of the tone scale
DEL_INK = "#8E8A80"

CSS = f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{ --ivory:{IVORY}; --surface:{SURFACE}; --ink:{INK}; --muted:{MUTED}; --faint:{FAINT}; --line:{LINE}; --green:{GREEN}; --green-soft:{GREEN_SOFT}; --terra:{TERRA}; }}

/* ---------- page ---------- */
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{ background: var(--ivory) !important; color: var(--ink); }}
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer {{ display: none !important; }}
[data-testid="stHeaderActionElements"], .stApp h1 > a, .stApp h2 > a, .stApp h3 > a {{ display: none !important; }}
.block-container {{ max-width: 1040px; padding: 28px 32px 72px !important; }}
.stApp, .stApp div, .stApp span, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp select, .stApp td, .stApp th, .stApp dt, .stApp dd {{
  font-family: 'Inter', system-ui, -apple-system, sans-serif; letter-spacing: normal; }}
[data-testid="stIconMaterial"], .material-symbols-rounded {{ font-family: 'Material Symbols Rounded' !important; }}
.stApp p, .stApp li {{ font-size: 17px; line-height: 1.65; color: var(--ink); }}
.stMarkdown p {{ margin-bottom: 0.6em; }}
a {{ color: var(--green); }}
@media (prefers-reduced-motion: no-preference) {{
  .reveal {{ animation: reveal .3s ease-out both; }}
  @keyframes reveal {{ from {{ opacity: 0; transform: translateY(4px); }} to {{ opacity: 1; transform: none; }} }}
}}

/* ---------- type ---------- */
h1, h2, h3, .say, .result .big {{ text-wrap: balance; }}
h1, h2, h3 {{ font-family: 'Newsreader', Georgia, serif !important; font-weight: 500 !important; color: var(--ink) !important; letter-spacing: normal !important; }}
.stApp h1 *, .stApp h2 *, .stApp h3 * {{ font-family: inherit !important; }}
h1 {{ font-size: 54px !important; line-height: 1.06 !important; padding: 0 !important; margin: 0 0 18px !important; max-width: 880px; }}
h2 {{ font-size: 32px !important; line-height: 1.2 !important; padding: 0 !important; margin: 0 0 12px !important; }}
h3 {{ font-size: 23px !important; line-height: 1.3 !important; padding: 0 !important; margin: 0 0 8px !important; }}
.stApp h3.gap {{ margin-top: 36px !important; }}
.lede {{ font-size: 20px !important; line-height: 1.55 !important; color: var(--muted) !important; max-width: 620px; }}
.muted, .muted * {{ color: var(--muted) !important; }}
.note {{ font-size: 14px !important; line-height: 1.55 !important; color: var(--muted) !important; }}
.fig, .tab {{ font-variant-numeric: tabular-nums; }}
.fig {{ font-family: 'IBM Plex Mono', ui-monospace, monospace !important; }}
.dove {{ color: var(--green) !important; }} .hawk {{ color: var(--terra) !important; }}

/* ---------- top bar: wordmark and a quiet text nav (active = underline, not a chip) ---------- */
.wordmark {{ font-family: 'Newsreader', Georgia, serif !important; font-size: 25px; font-weight: 600; color: var(--ink); line-height: 44px; }}
.wordmark span {{ color: var(--green); font-family: inherit !important; }}
.st-key-nav [data-testid="stElementContainer"] {{ width: 100% !important; }}
.st-key-nav [data-testid="stRadioGroup"] {{ gap: 26px; justify-content: flex-end; flex-wrap: wrap; }}
.st-key-nav [data-testid="stRadioOption"] {{ padding: 10px 0 8px; margin: 0; min-height: 44px; cursor: pointer; border-bottom: 2px solid transparent; border-radius: 0; }}
.st-key-nav [data-testid="stRadioOption"] > div > div:first-child {{ display: none; }}
.st-key-nav [data-testid="stRadioOption"] p {{ font-size: 16px !important; color: var(--muted) !important; font-weight: 500; }}
.st-key-nav [data-testid="stRadioOption"]:hover p {{ color: var(--ink) !important; }}
.st-key-nav [data-testid="stRadioOption"][data-selected="true"] {{ border-bottom-color: var(--ink); }}
.st-key-nav [data-testid="stRadioOption"][data-selected="true"] p {{ color: var(--ink) !important; }}
.st-key-nav [data-testid="stRadioOption"]:has(input:focus-visible) {{ outline: 2px solid var(--green); outline-offset: 4px; }}

/* ---------- buttons ---------- */
.stButton button, .stFormSubmitButton button {{ border-radius: 10px; min-height: 46px; padding: 8px 22px; font-size: 16px; font-weight: 500;
  border: 1px solid var(--line); background: var(--surface); color: var(--ink); box-shadow: none; }}
.stButton button:hover {{ border-color: var(--ink); color: var(--ink); background: var(--surface); }}
.stButton button:focus-visible, .stFormSubmitButton button:focus-visible {{ outline: 2px solid var(--green); outline-offset: 2px; }}
[data-testid^="stBaseButton-primary"] {{ background: var(--green) !important; border-color: var(--green) !important; color: #fff !important; }}
[data-testid^="stBaseButton-primary"] p {{ color: #fff !important; }}
[data-testid^="stBaseButton-primary"]:hover {{ background: #56695A !important; border-color: #56695A !important; }}
[data-testid="stBaseButton-tertiary"] {{ border: 0 !important; background: transparent !important; padding: 6px 0 !important; min-height: 40px; }}
[data-testid="stBaseButton-tertiary"] > div {{ overflow: visible; }}
[data-testid="stBaseButton-tertiary"] p {{ color: var(--green) !important; font-weight: 500; text-align: left; white-space: normal; overflow: visible; text-overflow: clip; }}
[data-testid="stBaseButton-tertiary"]:hover p {{ text-decoration: underline; text-underline-offset: 3px; }}
.st-key-pager [data-testid="stColumn"]:last-child [data-testid="stElementContainer"] {{ margin-left: auto; width: fit-content !important; }}
.st-key-pager {{ margin-top: 8px; }}

/* ---------- inputs: sized to what they hold ---------- */
[data-baseweb="select"] > div, .stNumberInput input, .stTextArea textarea, [data-baseweb="input"] {{ background: var(--surface) !important; border-color: var(--line) !important; border-radius: 10px !important; }}
.stNumberInput {{ max-width: 300px; }}
.stNumberInput button {{ display: none; }}
[data-testid="stWidgetLabel"] p {{ font-size: 15px !important; font-weight: 500; color: var(--ink) !important; }}
.st-key-ask_meeting textarea {{ font-size: 20px !important; line-height: 1.5 !important; padding: 16px 18px !important; }}

/* ---------- choice tiles (calculator): the one place boxes earn their keep, because you press them ---------- */
div[class*="st-key-tiles"] [data-testid="stElementContainer"] {{ width: 100% !important; }}
div[class*="st-key-tiles"] [data-testid="stRadioGroup"] {{ display: grid !important; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 8px; width: 100%; max-width: 820px; }}
div[class*="st-key-tiles"] [data-testid="stRadioOption"] {{ margin: 0; padding: 14px 16px; min-height: 58px; width: 100%; background: var(--surface); border: 1px solid var(--line);
  border-radius: 10px; cursor: pointer; display: flex; align-items: center; transition: border-color .12s, background .12s; }}
div[class*="st-key-tiles"] [data-testid="stRadioOption"] > div > div:first-child {{ display: none; }}
div[class*="st-key-tiles"] [data-testid="stRadioOption"] p {{ font-size: 16px !important; line-height: 1.35 !important; }}
div[class*="st-key-tiles"] [data-testid="stRadioOption"]:hover {{ border-color: var(--faint); }}
div[class*="st-key-tiles"] [data-testid="stRadioOption"][data-selected="true"] {{ border-color: var(--green); background: var(--green-soft); }}
div[class*="st-key-tiles"] [data-testid="stRadioOption"]:has(input:focus-visible) {{ outline: 2px solid var(--green); outline-offset: 2px; }}
div[class*="st-key-checks"] {{ max-width: 820px; }}
div[class*="st-key-checks"] [data-testid="stElementContainer"] {{ width: 100% !important; }}
div[class*="st-key-checks"] [data-testid="stCheckbox"] label {{ padding: 13px 14px; min-height: 52px; width: 100%; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; align-items: center; }}
div[class*="st-key-checks"] [data-testid="stCheckbox"] label:has(input:checked) {{ border-color: var(--green); background: var(--green-soft); }}
div[class*="st-key-checks"] [data-testid="stCheckbox"] {{ margin-bottom: 8px; }}

/* ---------- decoder narrative ---------- */
.step {{ padding: 56px 0 6px; }}
.step.first {{ padding-top: 34px; }}
.dateline {{ font-size: 15px; color: var(--muted); margin-bottom: 10px; }}
dl.facts {{ display: flex; flex-wrap: wrap; gap: 10px 48px; margin: 6px 0 26px; }}
dl.facts dt {{ font-size: 14px; color: var(--muted); font-weight: 400; }}
dl.facts dd {{ font-size: 21px; font-weight: 500; margin: 2px 0 0; font-variant-numeric: tabular-nums; }}
.prose {{ max-width: 660px; }}
.prose p {{ font-size: 18px !important; line-height: 1.7 !important; }}
.say, .say * {{ font-family: 'Newsreader', Georgia, serif !important; color: var(--ink) !important; }}
.say {{ max-width: 620px; margin: 22px 0 8px; font-size: 23px; line-height: 1.45; text-indent: -0.42em; }}
/* "Why it matters": an asymmetric side heading, not a card */
.aside {{ display: grid; grid-template-columns: 170px minmax(0, 520px); gap: 28px; margin: 34px 0 0; padding-top: 18px; border-top: 1px solid var(--line); max-width: 720px; }}
.aside-h {{ font-family: 'Newsreader', Georgia, serif !important; font-size: 20px; line-height: 1.4; }}
.aside p {{ margin: 0 !important; }}

/* glossary: tap, click or press Space on a term to see its meaning (no hover needed) */
label.term {{ cursor: pointer; }}
label.term input {{ position: absolute; opacity: 0; width: 1px; height: 1px; }}
label.term .w {{ border-bottom: 1.5px dotted var(--green); }}
label.term input:focus-visible + .w {{ outline: 2px solid var(--green); outline-offset: 2px; border-radius: 2px; }}
label.term input:checked + .w {{ color: var(--green); }}
label.term .d {{ display: none; }}
label.term input:checked ~ .d {{ display: block; margin: 8px 0 10px; padding: 2px 0 2px 14px; border-left: 2px solid var(--green); font-size: 15px; line-height: 1.5; color: var(--muted); font-weight: 400; }}

/* redline with margin notes */
.margin-notes {{ display: grid; grid-template-columns: minmax(0, 640px) minmax(0, 300px); gap: 44px; align-items: start; margin-top: 8px; }}
.redline p, .redline del, .redline ins, .redline span {{ font-family: 'Newsreader', Georgia, serif !important; }}
.redline p {{ font-size: 19px !important; line-height: 1.75 !important; margin: 0 0 16px; }}
.redline del, del.key {{ color: {DEL_INK}; text-decoration: line-through; text-decoration-color: var(--terra); text-decoration-thickness: 1.5px; }}
.redline ins, ins.key {{ background: var(--green-soft); text-decoration: none; padding: 1px 2px; border-radius: 3px; }}
.redline sup a {{ font-family: 'Inter', sans-serif !important; font-size: 12px; font-weight: 600; color: var(--green); text-decoration: none; padding: 0 2px; }}
.redline p.roster, .redline p.roster * {{ font-family: 'Inter', sans-serif !important; }}
.redline p.roster {{ font-size: 15px !important; line-height: 1.7 !important; color: var(--muted); }}
ol.notes {{ position: sticky; top: 24px; padding: 0 0 0 20px; margin: 4px 0 0; }}
ol.notes li {{ font-size: 15px !important; line-height: 1.55 !important; margin-bottom: 14px; padding-left: 2px; color: var(--ink); }}
ol.notes li::marker {{ color: var(--green); font-weight: 600; font-size: 13px; }}

/* tone: a plain line with five ticks; no gradient */
.scale {{ max-width: 560px; margin: 26px 0 30px; }}
.scale .read {{ display: flex; align-items: baseline; gap: 14px; margin-bottom: 16px; }}
.scale .read > span:first-child {{ font-family: 'Newsreader', Georgia, serif !important; font-size: 28px; }}
.scale .read .score {{ font-size: 16px; color: var(--muted); font-variant-numeric: tabular-nums; }}
.scale .track {{ position: relative; height: 2px; background: var(--ink); opacity: .9; }}
.scale .track i {{ position: absolute; top: -5px; width: 1px; height: 12px; background: var(--ink); }}
.scale .track i:last-of-type {{ margin-left: -1px; }}
.scale .pin {{ position: absolute; top: 50%; width: 16px; height: 16px; margin: -8px 0 0 -8px; border-radius: 50%; background: var(--ink); box-shadow: 0 0 0 4px var(--ivory); }}
.scale .pin.dove {{ background: var(--green); }} .scale .pin.hawk {{ background: var(--terra); }}
.scale .ends {{ display: flex; justify-content: space-between; font-size: 14px; color: var(--muted); margin-top: 12px; }}
.quotes {{ max-width: 640px; margin: 0 0 22px; }}
.quotes .qh {{ font-size: 15px; font-weight: 600; margin-bottom: 6px; }}
.quotes p, .quotes p * {{ font-family: 'Newsreader', Georgia, serif !important; }}
.quotes p {{ font-size: 19px !important; line-height: 1.55 !important; margin: 0 0 12px; }}

/* money rows: figure first, then what it is; no dividers */
.rows {{ max-width: 700px; margin: 18px 0 8px; }}
.row {{ display: grid; grid-template-columns: 136px 1fr; gap: 24px; align-items: baseline; padding: 10px 0 12px; }}
.row .n {{ font-family: 'IBM Plex Mono', ui-monospace, monospace !important; font-size: 17px; white-space: nowrap; font-variant-numeric: tabular-nums; }}
.row .t {{ font-weight: 600; font-size: 16px; margin-bottom: 2px; }}
.row .s {{ font-size: 16px; line-height: 1.55; color: var(--muted); }}

/* economy: a briefing with run-in topics */
.briefing {{ max-width: 660px; margin-top: 14px; }}
.briefing p {{ font-size: 17px !important; line-height: 1.7 !important; margin: 0 0 12px !important; }}
.briefing strong {{ font-weight: 600; }}

/* calculator: an open section introduced by a rule, not a tinted panel */
div[class*="st-key-calc"] {{ margin-top: 40px; padding-top: 30px; border-top: 1px solid var(--line); }}
.qa {{ font-family: 'Newsreader', Georgia, serif !important; font-size: 22px; margin: 26px 0 8px; }}
.qa-sub {{ font-size: 15px; color: var(--muted); margin: -4px 0 10px; }}
.result {{ margin: 34px 0 10px; padding-left: 22px; border-left: 3px solid var(--green); max-width: 720px; }}
.result .big {{ font-family: 'Newsreader', Georgia, serif !important; font-size: 46px; line-height: 1.1; margin: 4px 0 8px; font-variant-numeric: tabular-nums; }}
.result h4 {{ font-family: 'Inter', sans-serif !important; font-size: 14px; font-weight: 600; color: var(--muted) !important; margin: 26px 0 0; }}
.result .rows {{ margin-top: 4px; }}

/* forecast odds */
.odds {{ max-width: 520px; margin: 16px 0 14px; }}
.odds .o {{ display: grid; grid-template-columns: 64px 1fr 48px; gap: 14px; align-items: center; margin: 9px 0; font-size: 16px; }}
.odds .bar {{ height: 8px; border-radius: 4px; background: var(--line); overflow: hidden; }}
.odds .bar > i {{ display: block; height: 100%; border-radius: 4px; background: {NEUTRAL}; }}
.odds .top .bar > i {{ background: var(--green); }}
.odds .top span {{ font-weight: 600; }}
.odds .o > span:last-child {{ font-variant-numeric: tabular-nums; text-align: right; }}

/* timeline: the chosen meeting is marked with the accent bar, like every computed answer */
div[class*="st-key-picked"] {{ border-left: 3px solid var(--green); padding: 2px 0 6px 22px; margin: 8px 0 18px; }}

/* expanders: a line and a label */
[data-testid="stExpander"] details {{ border: 0 !important; border-top: 1px solid var(--line) !important; border-radius: 0 !important; background: transparent !important; }}
[data-testid="stExpander"] summary {{ padding-left: 0 !important; background: transparent !important; outline: none; }}
[data-testid="stExpander"] summary:focus-visible {{ outline: 2px solid var(--green) !important; outline-offset: 2px; }}
[data-testid="stExpander"] details, [data-testid="stExpander"] details:hover, [data-testid="stExpander"] details:focus-within {{ box-shadow: none !important; border-color: var(--line) !important; }}
[data-testid="stExpander"] summary p {{ font-size: 16px !important; font-weight: 500; }}
[data-testid="stExpander"] summary:hover p {{ color: var(--green) !important; }}

/* chat */
[data-testid="stChatMessage"] {{ background: transparent !important; padding: 10px 0 !important; }}
[data-testid^="stChatMessageAvatar"] {{ display: none !important; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p {{ font-family: 'Newsreader', Georgia, serif !important; font-size: 21px !important; }}
[data-testid="stChatInput"] > div {{ border-radius: 12px !important; border-color: var(--line) !important; background: var(--surface) !important; }}
.prov {{ font-size: 13px; color: var(--faint); margin-top: 4px; }}

/* footer */
.footer {{ margin-top: 72px; padding-top: 18px; border-top: 1px solid var(--line); font-size: 13px; color: var(--muted); }}

/* ---------- personal briefing ---------- */
.you-q {{ margin-top: 40px; }}
div[class*="st-key-you"] {{ margin-top: 34px; padding-left: 24px; border-left: 3px solid var(--green); max-width: 760px; }}
.who {{ font-size: 15px; color: var(--muted); }}
div[class*="st-key-you"] [data-testid="stColumn"]:last-child [data-testid="stElementContainer"] {{ margin-left: auto; width: fit-content !important; }}
.you-big {{ font-family: 'Newsreader', Georgia, serif !important; font-size: 38px; line-height: 1.15; margin: 2px 0 8px; text-wrap: balance; font-variant-numeric: tabular-nums; }}
.you-sub {{ font-size: 17px !important; color: var(--muted) !important; margin: 0 0 10px !important; }}
.ai-note {{ margin: 22px 0 0; max-width: 680px; padding-left: 16px; border-left: 3px solid var(--green); }}
.ai-note p {{ font-size: 16px !important; line-height: 1.6 !important; margin: 0 !important; color: var(--ink); }}
.next-you {{ display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 22px; margin: 18px 0 4px; max-width: 700px; }}
.next-you p {{ margin: 0 !important; font-size: 16px !important; }}
.bd-h {{ font-size: 14px; font-weight: 600; color: var(--muted); margin: 14px 0 0; }}
.short {{ margin-top: 56px; max-width: 760px; }}
.short.about {{ margin-top: 8px; }}
.short.about .short-row {{ padding: 14px 0; }}
.short h3 {{ margin-bottom: 14px !important; }}
.short-row {{ display: grid; grid-template-columns: 170px minmax(0, 1fr); gap: 28px; padding: 12px 0; }}
.short-row p {{ margin: 0 !important; font-size: 17px !important; }}
.say-inline {{ font-family: 'Newsreader', Georgia, serif !important; font-size: 20px; line-height: 1.45; }}
.ask {{ margin-top: 52px; }}
div[class*="st-key-live"] {{ margin-top: 18px; padding: 4px 0 4px 18px; border-left: 3px solid var(--terra); max-width: 760px; }}
.live-t {{ font-size: 17px; }}
div[class*="st-key-answer_"] {{ margin-top: 26px; max-width: 720px; }}
div[class*="st-key-answer_"] p, div[class*="st-key-answer_"] li {{ font-size: 17px !important; line-height: 1.65 !important; }}
div[class*="st-key-answer_"] strong {{ font-weight: 600; }}
.home-a {{ margin-top: 30px; max-width: 720px; }}
.home-a .qa-q {{ margin-top: 0; }}
.qa-q {{ font-family: 'Newsreader', Georgia, serif !important; font-size: 21px; margin: 18px 0 6px; max-width: 700px; }}
.qa-a {{ font-size: 17px; line-height: 1.65; max-width: 700px; white-space: pre-wrap; }}
div[class*="st-key-suggest"] [data-testid="stElementContainer"] {{ margin-bottom: -6px; }}
div[class*="st-key-ask_"] {{ max-width: 760px; }}
.stTextInput input {{ background: var(--surface) !important; border-radius: 10px !important; font-size: 17px !important; min-height: 46px; }}
.deeper-h {{ margin-top: 60px; }}
/* tabs: plain labels with an underline */
.stTabs [data-baseweb="tab-list"] {{ gap: 26px; border-bottom: 1px solid var(--line); }}
.stTabs [data-baseweb="tab"] {{ padding: 10px 0; background: transparent !important; }}
.stTabs [data-baseweb="tab"] p {{ font-size: 16px !important; font-weight: 500; color: var(--muted) !important; }}
.stTabs [aria-selected="true"] p {{ color: var(--ink) !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background: var(--ink) !important; height: 2px; }}
.stTabs [data-baseweb="tab-border"] {{ display: none; }}
.stTabs [data-baseweb="tab-panel"] {{ padding-top: 22px; }}
/* dialog */
[data-testid="stDialog"] [role="dialog"] {{ background: var(--ivory) !important; border-radius: 16px; }}
[data-testid="stDialog"] h2, [data-testid="stDialog"] [data-testid="stHeading"] * {{ font-family: 'Newsreader', Georgia, serif !important; }}
div[class*="st-key-tiles_dlg"] [data-testid="stRadioGroup"], div[class*="st-key-tiles_quick"] [data-testid="stRadioGroup"] {{ grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); }}
/* ---------- meeting at a glance ---------- */
.mhead {{ padding-top: 26px; }}
.mhead h1 {{ font-size: 46px !important; margin-bottom: 26px !important; }}
.tile {{ padding: 4px 0 0; }}
.tlab {{ font-size: 14px; color: var(--muted); margin-bottom: 4px; }}
.tbig {{ font-family: 'Newsreader', Georgia, serif !important; font-size: 34px; line-height: 1.1; margin-bottom: 10px; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.tcap {{ font-size: 14px; color: var(--muted); margin-top: 6px; font-variant-numeric: tabular-nums; }}
.mscale {{ width: 100%; max-width: 180px; margin-top: 16px; }}
.mtrack {{ position: relative; height: 2px; background: var(--ink); }}
.mtrack b {{ position: absolute; top: 50%; width: 14px; height: 14px; margin: -7px 0 0 -7px; border-radius: 50%; background: var(--ink); box-shadow: 0 0 0 3px var(--ivory); }}
.mtrack b.dove {{ background: var(--green); }} .mtrack b.hawk {{ background: var(--terra); }}
.mends {{ display: flex; justify-content: space-between; font-size: 13px; color: var(--muted); margin-top: 10px; }}
.obar {{ display: flex; height: 10px; border-radius: 5px; overflow: hidden; max-width: 200px; margin-top: 14px; gap: 2px; }}
.obar i {{ display: block; height: 100%; }}
.gap-l {{ height: 40px; }}
ol.three {{ max-width: 720px; margin: 0 0 26px; padding-left: 26px; counter-reset: none; }}
ol.three li {{ font-size: 19px !important; line-height: 1.5 !important; margin-bottom: 12px; padding-left: 6px; }}
ol.three li::marker {{ font-family: 'Newsreader', Georgia, serif; color: var(--green); font-size: 20px; }}
div[class*="st-key-suggest"] [data-testid="stBaseButton-tertiary"] p {{ font-size: 15px !important; }}
div[class*="st-key-suggest"] {{ margin-top: -8px; }}
[data-testid="stColumn"] [data-testid="stBaseButton-tertiary"] {{ justify-content: flex-start; text-align: left; }}
[data-testid="stColumn"] [data-testid="stBaseButton-tertiary"] p {{ font-size: 14px !important; }}
/* ---------- phones ---------- */
@media (max-width: 860px) {{
  .margin-notes {{ grid-template-columns: 1fr; gap: 4px; }}
  ol.notes {{ position: static; }}
}}
@media (max-width: 720px) {{
  .block-container {{ padding: 16px 16px 56px !important; }}
  h1 {{ font-size: 36px !important; }} h2 {{ font-size: 27px !important; }} h3 {{ font-size: 21px !important; }}
  .lede {{ font-size: 18px !important; }}
  .step {{ padding-top: 44px; }}
  .say {{ font-size: 20px; }}
  .aside, .short-row, .next-you {{ grid-template-columns: 1fr; gap: 4px; }}
  div[class*="st-key-you"] {{ padding-left: 16px; }}
  .you-big {{ font-size: 30px; }}
  .mhead h1 {{ font-size: 32px !important; margin-bottom: 18px !important; }}
  /* the four glance tiles sit two by two on phones */
  [data-testid="stHorizontalBlock"]:has(.tile) {{ flex-wrap: wrap !important; gap: 22px 16px !important; }}
  [data-testid="stHorizontalBlock"]:has(.tile) > [data-testid="stColumn"] {{ flex: 1 1 calc(50% - 8px) !important; width: calc(50% - 8px) !important; min-width: calc(50% - 8px) !important; }}
  .tile svg {{ width: 110px; height: 50px; }}
  .mscale, .obar {{ max-width: 150px; }}
  .tbig {{ font-size: 28px; }}
  ol.three li {{ font-size: 17px !important; }}
  .row {{ grid-template-columns: 1fr; gap: 2px; padding: 8px 0 14px; }}
  .result .big {{ font-size: 38px; }}
  .stNumberInput {{ max-width: none; }}
  .st-key-nav [data-testid="stRadioGroup"] {{ justify-content: flex-start; gap: 22px; }}
}}
</style>
"""

# Markdown ends an HTML block at a blank line, so the stylesheet must have none.
import re as _re  # noqa: E402

CSS = _re.sub(r"\n\s*\n", "\n", CSS)
