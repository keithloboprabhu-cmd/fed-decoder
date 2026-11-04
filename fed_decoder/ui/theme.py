"""Fed Decoder visual system.

Warm, restrained, editorial-but-friendly. One serif (Newsreader) for headlines
only, Inter for everything people read, IBM Plex Mono only for the few figures
people compare. Forest green = dovish / easing, terracotta = hawkish /
tightening; both always appear with a word, never as color alone.
Containers are rare: open layout, whitespace and the occasional tinted panel.
"""

IVORY = "#F8F7F3"     # page
SURFACE = "#FFFFFF"   # the few raised surfaces
TINT = "#EFEEE7"      # quiet panels (calculator, selected meeting)
INK = "#252923"
MUTED = "#686C64"
FAINT = "#9A9C94"
LINE = "#E4E1D8"
GREEN = "#647C68"     # main accent; dovish
GREEN_SOFT = "#E3E9E1"
TERRA = "#B0654A"     # supporting accent; hawkish
TERRA_SOFT = "#F3E3DB"
NEUTRAL = "#C9C5BA"   # midpoint of the tone scale
INS_BG = "#E3E9E1"    # additions in the redline (green tint)
DEL_INK = "#8E8A80"

CSS = f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --ivory:{IVORY}; --surface:{SURFACE}; --tint:{TINT}; --ink:{INK}; --muted:{MUTED}; --faint:{FAINT};
  --line:{LINE}; --green:{GREEN}; --green-soft:{GREEN_SOFT}; --terra:{TERRA}; --terra-soft:{TERRA_SOFT};
}}

/* ---------- page ---------- */
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{ background: var(--ivory) !important; color: var(--ink); }}
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer {{ display: none !important; }}
.block-container {{ max-width: 1040px; padding: 28px 32px 72px !important; }}
.stApp, .stApp div, .stApp span, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp select, .stApp td, .stApp th {{
  font-family: 'Inter', system-ui, -apple-system, sans-serif; letter-spacing: normal;
}}
.stApp p, .stApp li {{ font-size: 17px; line-height: 1.65; color: var(--ink); }}
[data-testid="stIconMaterial"], .material-symbols-rounded {{ font-family: 'Material Symbols Rounded' !important; }}
.stMarkdown p {{ margin-bottom: 0.6em; }}
a {{ color: var(--green); }}
@media (prefers-reduced-motion: no-preference) {{
  .reveal {{ animation: reveal .35s ease-out both; }}
  @keyframes reveal {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}
}}

/* ---------- type ---------- */
h1, h2, h3, .display {{ font-family: 'Newsreader', Georgia, serif !important; font-weight: 500 !important; color: var(--ink) !important; letter-spacing: normal !important; }}
.stApp h1 *, .stApp h2 *, .stApp h3 * {{ font-family: inherit !important; }}
h1 {{ font-size: 52px !important; line-height: 1.08 !important; padding: 0 !important; margin: 0 0 16px !important; }}
h2 {{ font-size: 34px !important; line-height: 1.18 !important; padding: 0 !important; margin: 0 0 12px !important; }}
h3 {{ font-size: 24px !important; line-height: 1.25 !important; padding: 0 !important; margin: 0 0 10px !important; }}
[data-testid="stHeaderActionElements"], .stApp h1 > a, .stApp h2 > a, .stApp h3 > a {{ display: none !important; }}
.stApp h3.gap {{ margin-top: 32px !important; }}
.lede {{ font-size: 20px !important; line-height: 1.55 !important; color: var(--muted) !important; max-width: 640px; }}
.muted, .muted * {{ color: var(--muted) !important; }}
.note {{ font-size: 14px !important; line-height: 1.55 !important; color: var(--muted) !important; }}
.fig {{ font-family: 'IBM Plex Mono', ui-monospace, monospace !important; font-variant-numeric: tabular-nums; letter-spacing: normal; }}
.dove {{ color: var(--green) !important; }} .hawk {{ color: var(--terra) !important; }}

/* ---------- top bar & navigation ---------- */
.wordmark {{ font-family: 'Newsreader', Georgia, serif !important; font-size: 25px; font-weight: 600; color: var(--ink); line-height: 40px; }}
.wordmark span {{ color: var(--green); font-family: inherit !important; }}
.st-key-nav [data-testid="stRadioGroup"] {{ gap: 2px; justify-content: flex-end; flex-wrap: wrap; }}
.st-key-nav [data-testid="stRadioOption"] {{ padding: 8px 14px; margin: 0; border-radius: 10px; min-height: 42px; cursor: pointer; }}
.st-key-nav [data-testid="stRadioOption"] > div > div:first-child {{ display: none; }}
.st-key-nav [data-testid="stRadioOption"] p {{ font-size: 16px !important; color: var(--muted) !important; font-weight: 500; }}
.st-key-nav [data-testid="stRadioOption"]:hover p {{ color: var(--ink) !important; }}
.st-key-nav [data-testid="stRadioOption"][data-selected="true"] {{ background: var(--surface); box-shadow: 0 0 0 1px var(--line); }}
.st-key-nav [data-testid="stRadioOption"][data-selected="true"] p {{ color: var(--ink) !important; }}
.st-key-nav [data-testid="stRadioOption"]:has(input:focus-visible) {{ outline: 2px solid var(--green); outline-offset: 2px; }}
.st-key-nav [data-testid="stElementContainer"] {{ width: 100% !important; }}
/* ---------- buttons ---------- */
.stButton button, .stFormSubmitButton button {{ border-radius: 10px; min-height: 44px; padding: 8px 18px; font-size: 16px; font-weight: 500;
  border: 1px solid var(--line); background: var(--surface); color: var(--ink); box-shadow: none; }}
.stButton button:hover {{ border-color: var(--ink); color: var(--ink); background: var(--surface); }}
.stButton button:focus-visible {{ outline: 2px solid var(--green); outline-offset: 2px; }}
.stButton button[kind="primary"], [data-testid^="stBaseButton-primary"] {{ background: var(--green) !important; border-color: var(--green) !important; color: #fff !important; }}
.stButton button[kind="primary"] p, [data-testid^="stBaseButton-primary"] p {{ color: #fff !important; }}
.stButton button[kind="primary"]:hover, [data-testid^="stBaseButton-primary"]:hover {{ background: #56695A !important; border-color: #56695A !important; }}
.stButton button[kind="tertiary"], [data-testid="stBaseButton-tertiary"] {{ border: 0 !important; background: transparent !important; padding: 6px 0 !important; min-height: 36px; }}
.stButton button[kind="tertiary"] p {{ color: var(--green) !important; font-weight: 500; text-align: left; white-space: normal; overflow: visible; text-overflow: clip; }}
[data-testid="stBaseButton-tertiary"] > div {{ overflow: visible; }}
.stButton button[kind="tertiary"]:hover p {{ text-decoration: underline; }}

/* ---------- form controls ---------- */
[data-baseweb="select"] > div, .stNumberInput input, .stTextArea textarea, [data-baseweb="input"] {{ background: var(--surface) !important; border-color: var(--line) !important; border-radius: 10px !important; }}
[data-testid="stWidgetLabel"] p {{ font-size: 15px !important; font-weight: 500; color: var(--ink) !important; }}
.stNumberInput button {{ display: none; }}

/* Large choice tiles (calculator questions) */
div[class*="st-key-tiles"] [data-testid="stElementContainer"] {{ width: 100% !important; }}
div[class*="st-key-tiles"] [data-testid="stRadioGroup"] {{ display: grid !important; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 10px; width: 100%; }}
div[class*="st-key-tiles"] [data-testid="stRadioOption"] {{ margin: 0; padding: 14px 16px; min-height: 62px; width: 100%; background: var(--surface); border: 1px solid var(--line);
  border-radius: 12px; cursor: pointer; display: flex; align-items: center; transition: border-color .15s, background .15s; }}
div[class*="st-key-tiles"] [data-testid="stRadioOption"] > div > div:first-child {{ display: none; }}
div[class*="st-key-tiles"] [data-testid="stRadioOption"] p {{ font-size: 16px !important; line-height: 1.35 !important; }}
div[class*="st-key-tiles"] [data-testid="stRadioOption"]:hover {{ border-color: var(--faint); }}
div[class*="st-key-tiles"] [data-testid="stRadioOption"][data-selected="true"] {{ border-color: var(--green); background: var(--green-soft); box-shadow: inset 0 0 0 1px var(--green); }}
div[class*="st-key-tiles"] [data-testid="stRadioOption"]:has(input:focus-visible) {{ outline: 2px solid var(--green); outline-offset: 2px; }}
div[class*="st-key-checks"] [data-testid="stCheckbox"] label {{ padding: 12px 14px; min-height: 52px; width: 100%; background: var(--surface); border: 1px solid var(--line); border-radius: 12px; align-items: center; }}
div[class*="st-key-checks"] [data-testid="stCheckbox"] label:has(input:checked) {{ border-color: var(--green); background: var(--green-soft); }}
div[class*="st-key-checks"] [data-testid="stCheckbox"] {{ margin-bottom: 8px; }}
div[class*="st-key-checks"] [data-testid="stRadioOption"] {{ padding: 6px 0; }}
/* ---------- hero (home) ---------- */
.hero {{ padding: 40px 0 8px; }}
.hero h1 {{ max-width: 760px; }}
.latest {{ display: grid; grid-template-columns: 1.35fr 1fr; gap: 40px; align-items: end; padding: 36px 0 8px; }}
.latest .when {{ font-size: 15px; color: var(--muted); margin-bottom: 6px; }}
.latest .rate {{ border-left: 3px solid var(--green); padding: 4px 0 4px 20px; }}
.latest .rate .fig {{ font-size: 44px; line-height: 1.1; color: var(--ink); }}
.latest .rate .lab {{ font-size: 15px; color: var(--muted); }}
.why {{ background: var(--surface); border-radius: 14px; padding: 22px 24px; margin: 24px 0 8px; max-width: 720px; }}
.why .q {{ font-family: 'Newsreader', Georgia, serif !important; font-size: 21px; margin-bottom: 4px; }}

/* ---------- decoder narrative ---------- */
.step {{ padding: 40px 0 8px; }}
.step .kick {{ font-size: 15px; font-weight: 500; color: var(--green); margin-bottom: 6px; }}
.facts {{ display: flex; flex-wrap: wrap; gap: 12px 44px; margin: 18px 0 6px; }}
.facts .k {{ font-size: 14px; color: var(--muted); }}
.facts .v {{ font-size: 22px; margin-top: 2px; }}
.prose {{ max-width: 680px; }}
.prose p {{ font-size: 18px !important; line-height: 1.7 !important; }}
.say, .say * {{ font-family: 'Newsreader', Georgia, serif !important; color: var(--ink) !important; }}
.say {{ margin: 18px 0; padding: 2px 0 2px 18px; border-left: 3px solid var(--line); font-size: 20px; line-height: 1.5; }}

/* glossary: tap, click or press Space on a term to see its meaning (no hover needed) */
label.term {{ cursor: pointer; }}
label.term input {{ position: absolute; opacity: 0; width: 1px; height: 1px; }}
label.term .w {{ border-bottom: 1.5px dotted var(--green); }}
label.term input:focus-visible + .w {{ outline: 2px solid var(--green); outline-offset: 2px; border-radius: 2px; }}
label.term input:checked + .w {{ color: var(--green); }}
label.term .d {{ display: none; }}
label.term input:checked ~ .d {{ display: block; margin: 8px 0 10px; padding: 10px 14px; background: var(--green-soft); border-radius: 10px; font-size: 15px; line-height: 1.5; color: var(--ink); font-weight: 400; }}
/* redline */
.redline {{ max-width: 720px; }}
.redline p, .redline del, .redline ins, .redline span {{ font-family: 'Newsreader', Georgia, serif !important; }}
.redline p {{ font-family: 'Newsreader', Georgia, serif !important; font-size: 19px !important; line-height: 1.75 !important; margin: 0 0 16px; }}
.redline del {{ color: {DEL_INK}; text-decoration: line-through; text-decoration-color: var(--terra); text-decoration-thickness: 1.5px; }}
.redline ins {{ background: {INS_BG}; text-decoration: none; padding: 1px 2px; border-radius: 3px; }}
.redline sup a {{ font-family: 'Inter', sans-serif !important; font-size: 12px; font-weight: 600; color: var(--green); text-decoration: none; padding: 0 3px; }}
.legend {{ display: flex; gap: 22px; flex-wrap: wrap; font-size: 14px; color: var(--muted); margin: 8px 0 18px; }}
.legend del {{ color: {DEL_INK}; text-decoration-color: var(--terra); }}
.legend ins {{ background: {INS_BG}; text-decoration: none; padding: 0 3px; }}
ol.notes {{ max-width: 720px; padding-left: 22px; margin: 6px 0 0; }}
ol.notes li {{ font-size: 16px !important; line-height: 1.6 !important; margin-bottom: 10px; padding-left: 4px; }}
ol.notes li::marker {{ color: var(--green); font-weight: 600; font-size: 14px; }}
ol.notes .was {{ display: block; font-size: 14px; color: var(--muted); margin-top: 2px; }}

/* tone scale */
.scale {{ max-width: 620px; margin: 20px 0 8px; }}
.scale .track {{ position: relative; height: 8px; border-radius: 8px; background: linear-gradient(90deg, {GREEN} 0%, {NEUTRAL} 50%, {TERRA} 100%); opacity: .85; }}
.scale .pin {{ position: absolute; top: 50%; width: 22px; height: 22px; margin: -11px 0 0 -11px; border-radius: 50%; background: var(--surface); border: 3px solid var(--ink); }}
.scale .ends {{ display: flex; justify-content: space-between; font-size: 14px; color: var(--muted); margin-top: 10px; }}
.scale .read {{ font-size: 18px; margin-bottom: 14px; }}
.quote {{ max-width: 680px; margin: 0 0 18px; }}
.quote p, .quote p * {{ font-family: 'Newsreader', Georgia, serif !important; }}
.quote p {{ font-family: 'Newsreader', Georgia, serif !important; font-size: 19px !important; line-height: 1.55 !important; margin: 0 0 2px; }}
.quote .why {{ all: unset; display: block; font-size: 14px; color: var(--muted); }}
.quote .mark {{ font-weight: 600; }}

/* impact rows: an open list, not a grid of cards */
.rows {{ max-width: 760px; margin: 8px 0; }}
.row {{ display: grid; grid-template-columns: 150px 1fr auto; gap: 20px; align-items: baseline; padding: 14px 0; border-top: 1px solid var(--line); }}
.row:last-child {{ border-bottom: 1px solid var(--line); }}
.row .t {{ font-weight: 600; font-size: 15px; }}
.row .s {{ font-size: 16px; line-height: 1.55; color: var(--ink); }}
.row .n {{ font-size: 17px; white-space: nowrap; text-align: right; }}

/* calculator */
div[class*="st-key-calc"] {{ background: var(--tint); border-radius: 18px; padding: 28px 28px 20px; margin-top: 24px; }}
.qa {{ font-family: 'Newsreader', Georgia, serif !important; font-size: 22px; margin: 18px 0 4px; }}
.qa-sub {{ font-size: 15px; color: var(--muted); margin-bottom: 10px; }}
.result {{ background: var(--surface); border-radius: 14px; padding: 24px; margin: 22px 0 10px; }}
.result .big {{ font-size: 40px; line-height: 1.1; margin: 4px 0 6px; }}
.result h4 {{ font-family: 'Inter', sans-serif; font-size: 15px; font-weight: 600; margin: 18px 0 2px; color: var(--ink); }}

/* forecast */
.odds {{ max-width: 560px; margin: 14px 0; }}
.odds .o {{ display: grid; grid-template-columns: 70px 1fr 52px; gap: 14px; align-items: center; margin: 10px 0; font-size: 16px; }}
.odds .bar {{ height: 10px; border-radius: 6px; background: var(--line); overflow: hidden; }}
.odds .bar > i {{ display: block; height: 100%; border-radius: 6px; background: var(--ink); }}
.odds .top .bar > i {{ background: var(--green); }}

/* selected meeting (timeline) */
div[class*="st-key-picked"] {{ background: var(--surface); border-radius: 16px; padding: 22px 24px; }}

/* expanders: quiet */
[data-testid="stExpander"] details {{ border: 0 !important; border-top: 1px solid var(--line) !important; border-radius: 0 !important; background: transparent !important; }}
[data-testid="stExpander"] summary {{ padding-left: 0 !important; }}
[data-testid="stExpander"] summary p {{ font-size: 16px !important; font-weight: 500; }}

/* chat */
[data-testid="stChatMessage"] {{ background: transparent !important; padding: 10px 0 !important; }}
[data-testid^="stChatMessageAvatar"] {{ display: none !important; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{ justify-content: flex-end; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {{
  background: var(--surface); border-radius: 16px; padding: 10px 16px; max-width: 75%; flex: 0 1 auto; }}
[data-testid="stChatInput"] > div {{ border-radius: 14px !important; border-color: var(--line) !important; background: var(--surface) !important; }}
.prov {{ font-size: 13px; color: var(--faint); margin-top: 4px; }}

/* footer */
.footer {{ margin-top: 64px; padding-top: 18px; border-top: 1px solid var(--line); font-size: 13px; color: var(--muted); }}

/* ---------- phones ---------- */
@media (max-width: 720px) {{
  .block-container {{ padding: 16px 16px 56px !important; }}
  h1 {{ font-size: 36px !important; }} h2 {{ font-size: 28px !important; }} h3 {{ font-size: 22px !important; }}
  .lede {{ font-size: 18px !important; }}
  .latest {{ grid-template-columns: 1fr; gap: 20px; padding-top: 24px; }}
  .latest .rate .fig {{ font-size: 36px; }}
  .row {{ grid-template-columns: 1fr auto; gap: 4px 14px; }}
  .row .t {{ grid-column: 1; }} .row .n {{ grid-column: 2; grid-row: 1; }} .row .s {{ grid-column: 1 / -1; }}
  div[class*="st-key-calc"] {{ padding: 20px 16px 14px; border-radius: 14px; }}
  .st-key-nav div[role="radiogroup"] {{ justify-content: flex-start; }}
  .st-key-nav div[role="radiogroup"] > label {{ padding: 8px 10px; }}
}}
</style>
"""

# Markdown ends an HTML block at a blank line, so the stylesheet must have none.
import re as _re  # noqa: E402

CSS = _re.sub(r"\n\s*\n", "\n", CSS)
