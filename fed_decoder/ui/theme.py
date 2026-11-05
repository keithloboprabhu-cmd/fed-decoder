"""Fed Decoder visual system: "The Staircase".

Color carries meaning only: red = hike / hawkish, blue = cut / dovish, gray = hold /
neutral. Nothing else is colored. Numbers are the stars: every rate, percent and
vote is set in JetBrains Mono. Words use Inter Tight. Both fonts are self-hosted
from /app/static/fonts (Streamlit static serving).

Shapes: 1px hairlines, 6px radius maximum, no shadows, 48px between bands.
Motion: only where it means something (marker glide, card expand), and off when
the reader asks for reduced motion.
"""

BG = "#FAFAF7"
INK = "#141414"
SUB = "#5C5C58"     # secondary text (passes 4.5:1 on BG)
FAINT = "#8E8C86"
RULE = "#E6E4DE"
HIKE = "#C8402A"    # red: hike / hawkish
CUT = "#2B5FAF"     # blue: cut / dovish
HOLD = "#6E6E6A"    # gray: hold / neutral
HIKE_BG = "#FBEDEA"
CUT_BG = "#EAF0FA"

CSS = f"""
<style>
@font-face {{ font-family: 'Inter Tight'; src: url('/app/static/fonts/InterTight.woff2') format('woff2'); font-weight: 100 900; font-display: swap; }}
@font-face {{ font-family: 'JetBrains Mono'; src: url('/app/static/fonts/JetBrainsMono.woff2') format('woff2'); font-weight: 100 800; font-display: swap; }}
:root {{ --bg:{BG}; --ink:{INK}; --sub:{SUB}; --faint:{FAINT}; --rule:{RULE}; --hike:{HIKE}; --cut:{CUT}; --hold:{HOLD};
  --sans: 'Inter Tight', system-ui, -apple-system, 'Segoe UI', sans-serif; --mono: 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace; }}

/* ---------- chrome off, one centered column ---------- */
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stBottom"] > div {{ background: var(--bg) !important; color: var(--ink); }}
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"], #MainMenu, footer {{ display: none !important; }}
[data-testid="stHeaderActionElements"], .stApp h1 > a, .stApp h2 > a, .stApp h3 > a {{ display: none !important; }}
.block-container {{ max-width: 1100px !important; padding: 18px 28px 140px !important; }}
.stApp, .stApp div, .stApp span, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp td, .stApp th {{
  font-family: var(--sans); letter-spacing: normal; }}
[data-testid="stIconMaterial"], .material-symbols-rounded {{ font-family: 'Material Symbols Rounded' !important; }}
.stApp p, .stApp li {{ font-size: 17px; line-height: 1.55; color: var(--ink); }}
.stMarkdown p {{ margin: 0 0 .5em; }}
h1, h2, h3 {{ font-family: var(--sans) !important; color: var(--ink) !important; letter-spacing: -0.01em !important; padding: 0 !important; }}
.stApp .mono, .stApp .num, .stApp .rate, .stApp .chip, .stApp .vcap, .stApp .live, .stApp .live *, .stApp .dateline, .stApp .slegend,
.stApp .mine .v, .stApp .sig .v, .stApp .res-date, .stApp .res-move, .stApp .tilebox .big, .stApp .tilebox .cap, .stApp .ctitle .tog, .stApp .reason .spk {{
  font-family: var(--mono) !important; font-variant-numeric: tabular-nums; letter-spacing: 0; }}
.stApp .vcap small, .stApp .live .pop {{ font-family: var(--sans) !important; }}
.sub {{ color: var(--sub) !important; }}
.hike {{ color: var(--hike) !important; }} .cut {{ color: var(--cut) !important; }} .hold {{ color: var(--hold) !important; }}
@media (prefers-reduced-motion: no-preference) {{
  .glide {{ animation: glide .3s ease-out both; }}
  @keyframes glide {{ from {{ opacity: 0; transform: translateY(3px); }} to {{ opacity: 1; transform: none; }} }}
}}

/* ---------- top bar ---------- */
.brand {{ font-family: var(--sans); font-weight: 800; font-size: 19px; letter-spacing: -0.02em; line-height: 40px; }}
.brand img {{ display: block; height: 32px; width: auto; margin: 4px 0; }}
@media (max-width: 760px) {{ .brand img {{ height: 26px; margin: 7px 0; }} }}
.brand span {{ font-family: var(--mono); font-weight: 500; font-size: 15px; color: var(--sub); margin-left: 6px; }}
div[class*="st-key-topbar"] [data-testid="stBaseButton-tertiary"] p {{ color: var(--ink) !important; font-size: 15px !important; font-weight: 500; }}
div[class*="st-key-topbar"] [data-testid="stColumn"]:last-child [data-testid="stElementContainer"] {{ margin-left: auto; width: fit-content !important; }}

/* ---------- live strip ---------- */
.live {{ display: flex; flex-wrap: wrap; gap: 6px 18px; align-items: center; font-family: var(--mono); font-size: 13px; color: var(--sub);
  border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule); padding: 7px 0; margin: 4px 0 6px; }}
.live .it {{ position: relative; cursor: default; white-space: nowrap; }}
.live .it b {{ color: var(--ink); font-weight: 500; }}
.live .it .pop {{ display: none; position: absolute; top: 22px; left: 0; z-index: 30; background: #fff; border: 1px solid var(--rule); border-radius: 6px;
  padding: 8px 10px; width: 210px; white-space: normal; color: var(--sub); }}
.live .it:hover .pop, .live .it:focus .pop, .live .it:focus-within .pop {{ display: block; }}
.live .new {{ color: var(--ink); font-weight: 500; }}

/* ---------- jargon: dotted underline, one-line definition on hover or tap ---------- */
.term {{ border-bottom: 1.5px dotted currentColor; cursor: help; position: relative; outline: none; }}
.term::after {{ content: attr(data-def); display: none; position: absolute; left: 0; top: calc(100% + 6px); z-index: 40; width: max-content; max-width: 260px;
  background: var(--ink); color: #fff; font-family: var(--sans); font-size: 13px; font-weight: 400; line-height: 1.4; padding: 7px 9px; border-radius: 6px;
  white-space: normal; letter-spacing: 0; text-transform: none; }}
.term:hover::after, .term:focus::after {{ display: block; }}

/* ---------- verdict ---------- */
.verdict {{ margin: 14px 0 0; }}
.dateline {{ font-family: var(--mono); font-size: 14px; color: var(--sub); margin-bottom: 6px; }}
.verdict h1 {{ font-size: 50px !important; line-height: 1.04 !important; font-weight: 800 !important; letter-spacing: -0.025em !important; margin: 0 0 14px !important; }}
.facts3 {{ display: grid; grid-template-columns: 1.25fr 1fr 1.1fr; gap: 36px; align-items: start; }}
.fact .lab {{ font-size: 13px; color: var(--sub); margin-bottom: 8px; }}
.rate {{ font-family: var(--mono); font-size: 42px; line-height: 1; font-weight: 500; letter-spacing: -0.02em; white-space: nowrap; }}
.chip {{ display: inline-block; font-family: var(--mono); font-size: 14px; font-weight: 500; padding: 3px 8px; border-radius: 6px; border: 1px solid var(--rule); margin-top: 12px; }}
.chip.hike {{ border-color: var(--hike); }} .chip.cut {{ border-color: var(--cut); }}
.dots {{ display: flex; flex-wrap: wrap; gap: 4px; max-width: 300px; margin-top: 8px; }}
.dot {{ width: 12px; height: 12px; border-radius: 50%; background: var(--ink); position: relative; outline: none; }}
.dot.dhike {{ background: transparent; box-shadow: inset 0 0 0 2.5px var(--hike); }}
.dot.dcut {{ background: transparent; box-shadow: inset 0 0 0 2.5px var(--cut); }}
.dot.dother {{ background: transparent; box-shadow: inset 0 0 0 2.5px var(--hold); }}
.dot[data-tip]:hover::after, .dot[data-tip]:focus::after {{ content: attr(data-tip); position: absolute; left: 50%; top: 22px; transform: translateX(-50%); z-index: 40;
  width: max-content; max-width: 220px; background: var(--ink); color: #fff; font-size: 13px; line-height: 1.35; padding: 6px 8px; border-radius: 6px; }}
.vcap {{ font-family: var(--mono); font-size: 32px; font-weight: 500; margin-top: 12px; line-height: 1; }}
.vcap small {{ font-family: var(--sans); font-size: 14px; color: var(--sub); font-weight: 400; margin-left: 8px; }}
.stripe {{ position: relative; height: 10px; border-radius: 5px; margin: 12px 0 0; max-width: 300px;
  background: linear-gradient(90deg, var(--cut) 0%, #C9C7C1 50%, var(--hike) 100%); }}
.stripe i {{ position: absolute; top: -3px; width: 2px; height: 16px; background: var(--ink); opacity: .22; margin-left: -1px; }}
.stripe b {{ position: absolute; top: -7px; width: 6px; height: 24px; background: var(--ink); border: 2px solid var(--bg); border-radius: 3px; margin-left: -5px; }}
.stripe-ends {{ display: flex; justify-content: space-between; max-width: 300px; font-size: 13px; color: var(--sub); margin-top: 8px; }}
.tcap {{ font-size: 20px; font-weight: 600; margin-top: 12px; }}
div[class*="st-key-nextchip"] [data-testid="stBaseButton-secondary"] {{ border: 1px solid var(--rule) !important; border-radius: 6px !important; background: #fff !important;
  min-height: 34px !important; padding: 4px 10px !important; }}
div[class*="st-key-nextchip"] [data-testid="stBaseButton-secondary"] p {{ font-family: var(--mono) !important; font-size: 14px !important; white-space: normal; text-align: left; }}
div[class*="st-key-nextchip"] [data-testid="stBaseButton-secondary"]:hover {{ border-color: var(--ink) !important; }}

/* ---------- four answers ---------- */
.band {{ height: 14px; }}
div[class*="st-key-card_"], div[class*="st-key-cardopen_"] {{ border: 1px solid var(--rule); border-radius: 6px; background: #fff; padding: 12px 18px 10px; }}
div[class*="st-key-card_"]:hover {{ border-color: #CFCCC4; }}
div[class*="st-key-cardopen_"] {{ border-color: var(--ink); }}
div[class*="st-key-cardh_"] {{ position: relative; min-height: 84px; }}
.ctitle {{ font-size: 13px; color: var(--sub); display: flex; justify-content: space-between; }}
.ctitle .tog {{ font-family: var(--mono); color: var(--ink); font-size: 16px; line-height: 1; }}
.csent {{ font-size: 20px; font-weight: 600; line-height: 1.3; margin: 4px 0 8px; letter-spacing: -0.01em; }}
.csent del {{ color: var(--hike); text-decoration-thickness: 1.5px; font-weight: 500; }}
.csent ins {{ text-decoration: none; background: {CUT_BG}; color: var(--ink); padding: 0 3px; border-radius: 3px; }}
div[class*="st-key-hit_"] {{ position: absolute !important; inset: 0; z-index: 5; }}
div[class*="st-key-hit_"] [data-testid="stElementContainer"], div[class*="st-key-hit_"] .stButton {{ width: 100% !important; height: 100% !important; }}
div[class*="st-key-hit_"] button {{ width: 100% !important; height: 100% !important; opacity: 0; cursor: pointer; }}
div[class*="st-key-hit_"] button:focus-visible {{ opacity: 1; background: transparent !important; outline: 2px solid var(--ink); border-radius: 6px; }}
div[class*="st-key-hit_"] button:focus-visible p {{ visibility: hidden; }}
.cbody {{ border-top: 1px solid var(--rule); margin-top: 12px; padding-top: 14px; }}
@media (prefers-reduced-motion: no-preference) {{ .cbody {{ animation: glide .2s ease-out both; }} }}
.reason {{ display: grid; grid-template-columns: 1fr 130px; gap: 16px; align-items: center; padding: 8px 0; }}
.reason p {{ font-size: 15px !important; margin: 0 !important; }}
.reason .spk {{ text-align: right; font-family: var(--mono); font-size: 13px; color: var(--sub); }}
.chg {{ padding: 8px 0; }}
.chg p {{ font-size: 15px !important; margin: 0 0 2px !important; }}
.chg del {{ color: var(--hike); text-decoration-thickness: 1.5px; }}
.chg ins {{ text-decoration: none; background: {CUT_BG}; padding: 0 2px; border-radius: 3px; }}
.chg .note {{ font-size: 13px; color: var(--sub); }}
.mine {{ display: grid; grid-template-columns: 1fr auto; gap: 4px 14px; padding: 8px 0; border-top: 1px solid var(--rule); align-items: baseline; }}
.mine:first-child {{ border-top: 0; }}
.mine .k {{ font-size: 15px; }}
.mine .v {{ font-family: var(--mono); font-size: 16px; font-weight: 500; text-align: right; white-space: nowrap; }}
.mine .s {{ grid-column: 1 / -1; font-size: 13px; color: var(--sub); }}
.sbar {{ display: flex; height: 12px; border-radius: 4px; overflow: hidden; gap: 2px; max-width: 320px; }}
.sbar i {{ display: block; height: 100%; }}
.slegend {{ font-family: var(--mono); font-size: 13px; color: var(--sub); margin-top: 8px; }}
.sig {{ display: grid; grid-template-columns: 1fr auto; gap: 6px 14px; font-size: 15px; padding: 4px 0; }}
.sig .v {{ font-family: var(--mono); }}
.mini {{ font-size: 13px; color: var(--sub); }}
div[class*="st-key-mypills"] [data-testid="stButtonGroup"] button {{ border-radius: 6px !important; border-color: var(--rule) !important; min-height: 34px; }}
div[class*="st-key-mypills"] [data-testid="stButtonGroup"] button[aria-checked="true"], div[class*="st-key-mypills"] [data-testid="stButtonGroup"] button[kind*="Active"] {{
  border-color: var(--ink) !important; background: var(--ink) !important; color: #fff !important; }}
div[class*="st-key-mypills"] [data-testid="stButtonGroup"] button[kind*="Active"] p {{ color: #fff !important; }}

/* ---------- ask: fixed slim bar, chips on focus, answers in a side panel ---------- */
[data-testid="stBottom"] {{ border-top: 1px solid var(--rule); }}
[data-testid="stBottomBlockContainer"] {{ max-width: 1100px !important; padding: 8px 28px 12px !important; }}
div[class*="st-key-askbar"] [data-baseweb="input"], [data-testid="stBottom"] [data-baseweb="input"] {{ border-radius: 6px !important; border: 1px solid var(--rule) !important; background: #fff !important; }}
[data-testid="stBottom"] input {{ font-size: 16px !important; min-height: 44px; background: #fff !important; }}
[data-testid="stBottom"] [data-baseweb="input"] > div {{ background: #fff !important; }}
[data-testid="stBottom"] [data-testid="stFormSubmitButton"] button {{ min-height: 46px; border-radius: 6px; }}
[data-testid="stBottom"] [data-testid="stForm"] {{ border: 0 !important; padding: 0 !important; }}
div[class*="st-key-facts"] {{ margin-top: 2px; }}
.csent .mono {{ letter-spacing: -0.04em; }}
div[class*="st-key-askchips"] {{ display: none; }}
[data-testid="stBottomBlockContainer"]:focus-within div[class*="st-key-askchips"], [data-testid="stBottomBlockContainer"]:hover div[class*="st-key-askchips"] {{ display: block; }}
div[class*="st-key-askchips"] [data-testid="stHorizontalBlock"] {{ gap: 8px !important; flex-wrap: wrap; }}
div[class*="st-key-askchips"] [data-testid="stColumn"] {{ width: auto !important; flex: 0 0 auto !important; min-width: 0 !important; }}
div[class*="st-key-askchips"] button {{ min-height: 30px !important; padding: 2px 10px !important; border-radius: 6px !important; border: 1px solid var(--rule) !important; background: #fff !important; }}
div[class*="st-key-askchips"] button p {{ font-size: 14px !important; }}
[data-testid="stDialog"] [role="dialog"] {{ position: fixed !important; top: 0 !important; right: 0 !important; left: auto !important; bottom: 0 !important; margin: 0 !important;
  width: min(480px, 100vw) !important; max-width: 480px !important; height: 100vh !important; max-height: 100vh !important; border-radius: 0 !important;
  border-left: 1px solid var(--rule); background: var(--bg) !important; box-shadow: none !important; overflow-y: auto; transform: none !important; }}
@media (prefers-reduced-motion: no-preference) {{ [data-testid="stDialog"] [role="dialog"] {{ animation: slidein .2s ease-out both; }}
  @keyframes slidein {{ from {{ transform: translateX(24px); opacity: 0; }} to {{ transform: none; opacity: 1; }} }} }}
[data-testid="stDialog"] div, [data-testid="stDialog"] span, [data-testid="stDialog"] p, [data-testid="stDialog"] li, [data-testid="stDialog"] button {{ font-family: var(--sans); }}
[data-testid="stDialog"] .res-date, [data-testid="stDialog"] .res-move, [data-testid="stDialog"] .mono, [data-testid="stDialog"] .num, [data-testid="stDialog"] .tilebox .big {{ font-family: var(--mono) !important; }}
[data-testid="stDialog"] [role="dialog"] h2 {{ padding: 22px 0 0 24px !important; }}
[data-testid="stDialog"] [role="dialog"] h2 p {{ font-size: 13px !important; font-weight: 500 !important; color: var(--sub) !important; text-transform: uppercase; letter-spacing: .08em !important; margin: 0 !important; }}
@media (max-width: 760px) {{ [data-testid="stDialog"] [role="dialog"] {{ top: auto !important; height: 82vh !important; max-height: 82vh !important; width: 100vw !important; max-width: 100vw !important;
  border-left: 0; border-top: 1px solid var(--rule); border-radius: 6px 6px 0 0 !important; }} }}
.aq {{ font-size: 19px; font-weight: 600; margin: 4px 0 10px; }}
.res-row {{ display: flex; gap: 14px; align-items: baseline; flex-wrap: wrap; font-size: 15px; padding: 4px 0; }}
.res-date {{ font-family: var(--mono); font-weight: 500; min-width: 108px; }}
.res-move {{ font-family: var(--mono); min-width: 80px; }}
.res-quote p {{ font-size: 15px !important; margin: 2px 0 8px !important; }}
.res-people {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 18px; margin: 8px 0; }}
.res-people div {{ display: flex; flex-direction: column; font-size: 15px; }}
.res-people span {{ font-size: 13px; color: var(--sub); }}
.tilebox {{ border: 1px solid var(--rule); border-radius: 6px; padding: 10px 12px; margin: 8px 0; background: #fff; }}
.tilebox .lab {{ font-size: 13px; color: var(--sub); }}
.tilebox .big {{ font-family: var(--mono); font-size: 28px; font-weight: 500; }}
.tilebox .cap {{ font-family: var(--mono); font-size: 13px; color: var(--sub); }}

/* ---------- buttons, inputs, misc ---------- */
.stButton button {{ border-radius: 6px; border: 1px solid var(--rule); background: #fff; color: var(--ink); box-shadow: none; min-height: 40px; }}
.stButton button:hover {{ border-color: var(--ink); color: var(--ink); }}
[data-testid="stBaseButton-tertiary"] {{ border: 0 !important; background: transparent !important; padding: 4px 0 !important; min-height: 32px; }}
[data-testid="stBaseButton-tertiary"] p {{ color: var(--ink) !important; text-decoration: underline; text-underline-offset: 3px; text-decoration-color: var(--rule); }}
[data-testid="stBaseButton-tertiary"]:hover p {{ text-decoration-color: var(--ink); }}
[data-testid^="stBaseButton-primary"] {{ background: var(--ink) !important; border-color: var(--ink) !important; }}
[data-testid^="stBaseButton-primary"] p {{ color: #fff !important; }}
[data-testid="stExpander"] details {{ border: 0 !important; border-top: 1px solid var(--rule) !important; border-radius: 0 !important; background: transparent !important; }}
[data-testid="stExpander"] summary {{ padding-left: 0 !important; }}
[data-testid="stExpander"] summary p {{ font-size: 14px !important; }}
.redline p {{ font-size: 15px !important; line-height: 1.65 !important; }}
.redline del {{ color: var(--hike); }} .redline ins {{ text-decoration: none; background: {CUT_BG}; }}
.about-row {{ display: grid; grid-template-columns: 220px 1fr; gap: 24px; padding: 14px 0; border-top: 1px solid var(--rule); max-width: 820px; }}
.about-row h3 {{ font-size: 17px !important; font-weight: 600 !important; margin: 0 !important; }}
.about-row p {{ margin: 0 !important; }}
.byline {{ margin-top: 30px !important; font-size: 14px !important; color: var(--sub) !important; }}
.foot {{ margin-top: 60px; padding-top: 12px; border-top: 1px solid var(--rule); font-size: 13px; color: var(--sub); }}
iframe[title*="staircase"] {{ display: block; }}

/* ---------- phones ---------- */
@media (max-width: 760px) {{
  .block-container {{ padding: 10px 16px 150px !important; }}
  div[class*="st-key-facts"] [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap !important; gap: 18px 16px !important; }}
  div[class*="st-key-facts"] [data-testid="stColumn"] {{ flex: 1 1 calc(50% - 8px) !important; min-width: calc(50% - 8px) !important; width: calc(50% - 8px) !important; }}
  div[class*="st-key-facts"] [data-testid="stColumn"]:first-child, div[class*="st-key-facts"] [data-testid="stColumn"]:last-child {{ flex-basis: 100% !important; min-width: 100% !important; width: 100% !important; }}
  div[class*="st-key-nextchip"] [data-testid="stBaseButton-secondary"] p {{ white-space: normal; }}
  div[class*="st-key-topbar"] [data-testid="stHorizontalBlock"], [data-testid="stBottom"] [data-testid="stForm"] [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; }}
  div[class*="st-key-topbar"] [data-testid="stColumn"], [data-testid="stBottom"] [data-testid="stForm"] [data-testid="stColumn"] {{ min-width: 0 !important; width: auto !important; }}
  [data-testid="stBottom"] [data-testid="stForm"] [data-testid="stColumn"]:last-child {{ flex: 0 0 56px !important; }}
  [data-testid="stBottomBlockContainer"] {{ padding: 8px 12px 10px !important; }}
  .verdict {{ margin-top: 20px; }}
  .verdict h1 {{ font-size: 32px !important; margin-bottom: 18px !important; }}
  .facts3 {{ grid-template-columns: 1fr 1fr; gap: 22px 18px; }}
  .facts3 .fact.tone {{ grid-column: 1 / -1; }}
  .rate {{ font-size: 32px; }}
  .vcap {{ font-size: 24px; }}
  .dots {{ gap: 5px; }} .dot {{ width: 14px; height: 14px; }}
  .about-row {{ grid-template-columns: 1fr; gap: 4px; }}
  .reason {{ grid-template-columns: 1fr; }} .reason .spk {{ text-align: left; }}
}}
</style>
"""

# Markdown ends an HTML block at a blank line, so the stylesheet must have none.
import re as _re  # noqa: E402

CSS = _re.sub(r"\n\s*\n", "\n", CSS)
