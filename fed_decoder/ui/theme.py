"""Calm, editorial styling: off-white paper, ink text, one accent, hairline rules.
Serif headlines, mono numbers, 17px body, nothing under 13px."""

PAPER = "#FAF8F3"
INK = "#1C1B19"
MUTED = "#5E5A52"
RULE = "#DDD8CC"
ACCENT = "#9E2A2B"  # oxblood: the one accent (hawk end of the dial)
DOVE = "#3A6EA5"    # cool pole of the diverging tone scale
NEUTRAL = "#B9B6AE"
INS_BG = "#F3E3C3"  # additions highlight
DEL_INK = "#8A8478"

CSS = f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=Inter:wght@400;500&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{ --paper:{PAPER}; --ink:{INK}; --muted:{MUTED}; --rule:{RULE}; --accent:{ACCENT}; }}
html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"], .stApp {{ background: var(--paper) !important; color: var(--ink); }}
[data-testid="stAppViewContainer"] *:not([data-testid="stIconMaterial"]):not(.material-symbols-rounded) {{ font-family: 'Inter', system-ui, sans-serif; }}
.stApp p, .stApp li, .stApp label, .stMarkdown, .stApp textarea, .stApp input {{ font-size: 17px; line-height: 1.6; color: var(--ink); }}
h1, h2, h3, .serif, .stApp h1 *, .stApp h2 *, .stApp h3 *, .redline, .redline *, .quote, .quote * {{ font-family: 'Source Serif 4', Georgia, serif !important; font-weight: 600; color: var(--ink); letter-spacing: -0.01em; }}
h1 {{ font-size: 40px !important; line-height: 1.15 !important; }}
h2 {{ font-size: 28px !important; }}
h3 {{ font-size: 21px !important; }}
.mono, .num, .mono *, .facts .v.mono, .card .n {{ font-family: 'IBM Plex Mono', ui-monospace, monospace !important; font-variant-numeric: tabular-nums; }}
.kicker {{ font-size: 13px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }}
.small {{ font-size: 14px; color: var(--muted); }}
hr, .rule {{ border: 0; border-top: 1px solid var(--rule); margin: 28px 0 20px; }}
.block-container {{ max-width: 980px; padding-top: 3rem; }}
[data-testid="stToolbar"], [data-testid="stDecoration"] {{ display: none; }}
.facts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0; border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule); }}
.facts div {{ padding: 14px 16px 14px 0; }}
.facts .v {{ font-size: 24px; }}
.redline, .redline *, .quote, .quote * {{ font-weight: 400; }}
.redline {{ font-family: 'Source Serif 4', Georgia, serif; font-size: 18px; line-height: 1.75; }}
.redline p {{ font-family: 'Source Serif 4', Georgia, serif !important; font-size: 18px !important; margin: 0 0 14px; }}
.redline del {{ color: {DEL_INK}; text-decoration: line-through; text-decoration-color: var(--accent); }}
.redline ins {{ background: {INS_BG}; text-decoration: none; padding: 0 2px; margin-left: 2px; }}
.quote .tag, .quote .tag * {{ font-family: 'Inter', sans-serif !important; }}
.chg {{ position: relative; border-bottom: 1px dotted var(--muted); cursor: help; }}
.chg .tip, .chg .tip * {{ font-family: 'Inter', sans-serif !important; }}
.chg .tip {{ visibility: hidden; opacity: 0; position: absolute; left: 0; top: 100%; z-index: 20; width: min(420px, 80vw);
  background: var(--ink); color: var(--paper); font-family: 'Inter', sans-serif; font-size: 14px; line-height: 1.45; padding: 10px 12px; border-radius: 4px; transition: opacity .12s; }}
.chg:hover .tip, .chg:focus .tip {{ visibility: visible; opacity: 1; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 16px; }}
.card {{ border: 1px solid var(--rule); border-radius: 4px; padding: 16px; background: #FFFEFB; }}
.card .t {{ font-size: 13px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }}
.card .n {{ font-family: 'IBM Plex Mono', monospace; font-size: 26px; margin: 6px 0 8px; }}
.card .s {{ font-size: 16px; line-height: 1.5; }}
.quote {{ font-family: 'Source Serif 4', Georgia, serif; font-size: 17px; border-left: 2px solid var(--rule); padding: 2px 0 2px 14px; margin: 10px 0; }}
.quote.hawkish {{ border-left-color: var(--accent); }}
.quote.dovish {{ border-left-color: {DOVE}; }}
.tag {{ font-size: 13px; color: var(--muted); }}
.prov {{ font-size: 13px; color: var(--muted); }}
.bar {{ height: 8px; background: var(--rule); border-radius: 4px; overflow: hidden; }}
.bar > span {{ display: block; height: 100%; background: var(--ink); border-radius: 4px; }}
.footer {{ border-top: 1px solid var(--rule); margin-top: 48px; padding-top: 14px; font-size: 13px; color: var(--muted); }}
[data-testid="stChatMessage"] {{ background: transparent; border-bottom: 1px solid var(--rule); border-radius: 0; }}
.stButton button, .stDownloadButton button {{ border-radius: 4px; border: 1px solid var(--rule); background: #FFFEFB; color: var(--ink); font-size: 15px; }}
.stButton button:hover {{ border-color: var(--ink); color: var(--ink); }}
[data-testid^="stChatMessageAvatar"] {{ display: none; }}
#MainMenu, footer {{ visibility: hidden; }}
@media (max-width: 640px) {{ h1 {{ font-size: 30px !important; }} .block-container {{ padding-left: 16px; padding-right: 16px; }} }}
</style>
"""
