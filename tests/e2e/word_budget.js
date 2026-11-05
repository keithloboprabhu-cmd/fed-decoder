// Word budget: at 1440×900 the first viewport may show at most 60 words.
// A "word" is any whitespace-separated token that contains a letter, so numbers,
// arrows and dots are free; axis tick labels on the staircase are excluded.
// Usage: node tests/e2e/word_budget.js [base_url] [meeting ...]   (exit 1 on failure)
const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://localhost:8501';
const MEETINGS = process.argv.length > 3 ? process.argv.slice(3) : ['', '2026-07-29', '2024-09-18', '2008-09-16'];
const LIMIT = 60;
const W = 1440, H = 900;

function visibleWords([offsetY, viewH]) {
  const out = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement;
    if (!el || !n.textContent.trim()) continue;
    if (el.closest('script,style,noscript,.axis,[aria-hidden="true"]')) continue;
    if (el.checkVisibility && !el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) continue;
    const r = document.createRange(); r.selectNodeContents(n);
    const rects = [...r.getClientRects()].filter(b => b.width > 0 && b.height > 0);
    const er = el.getBoundingClientRect();
    if (er.width <= 1 || er.height <= 1) continue;  // visually-hidden helpers (skip links)
    // On screen and not covered by something else (e.g. the fixed ask bar).
    const seen = rects.some(b => {
      if (!(b.top + offsetY < viewH && b.bottom + offsetY > 0)) return false;
      const x = Math.min(Math.max(b.left + b.width / 2, 0), innerWidth - 1);
      const y = Math.min(Math.max(b.top + b.height / 2, 0), innerHeight - 1);
      const hit = document.elementFromPoint(x, y);
      if (!hit || hit === el || el.contains(hit) || hit.contains(el)) return true;
      // Covered only if the thing on top is a fixed layer (the ask bar) that el is not part of.
      for (let a = hit; a; a = a.parentElement)
        if (getComputedStyle(a).position === 'fixed') return a.contains(el);
      return true;
    });
    if (!seen) continue;
    for (const t of n.textContent.split(/\s+/)) if (/\p{L}/u.test(t)) out.push(t);
  }
  return out;
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: W, height: H } });
  let failed = false;
  for (const m of MEETINGS) {
    await page.goto(m ? `${BASE}/?m=${m}` : BASE);
    await page.waitForSelector('h1', { timeout: 60000 });
    await page.waitForTimeout(3000);
    let words = await page.evaluate(visibleWords, [0, H]);
    for (const f of page.frames()) {
      if (f === page.mainFrame()) continue;
      const handle = await f.frameElement().catch(() => null);
      const box = handle && await handle.boundingBox();
      if (!box || box.y > H || box.y + box.height < 0) continue;
      words = words.concat(await f.evaluate(visibleWords, [box.y, H]));
    }
    const ok = words.length <= LIMIT;
    failed ||= !ok;
    console.log(`${ok ? 'PASS' : 'FAIL'} ${m || 'latest'}: ${words.length} words above the fold (limit ${LIMIT})`);
    if (!ok || process.env.VERBOSE) console.log('  ' + words.join(' '));
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
