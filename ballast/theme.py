"""Visual system for the public report.

Dark, editorial, high-contrast — the house style of the reference design — with
Bitget's cyan as the single accent. Deliberately self-contained: no CDN, no web
fonts, no scripts. A judge opening a dead page on the day is unrecoverable, so
every byte the page needs travels with it.
"""

ACCENT = "#00d9ec"          # Bitget cyan
ACCENT_DIM = "#0a8fa0"

CSS = f"""
:root{{
  --bg:#080809; --surface:#111113; --raised:#17171a; --line:#252529;
  --fg:#fafafa; --mid:#a8a8ae; --dim:#6e6e76;
  --accent:{ACCENT}; --accent-dim:{ACCENT_DIM};
  --pos:#4ade80; --neg:#fb7185;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;
}}
*{{box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);
  font-size:16px;line-height:1.65;-webkit-font-smoothing:antialiased}}
a{{color:inherit}}

/* ---- chrome ---- */
.top{{position:sticky;top:0;z-index:20;background:rgba(8,8,9,.88);
  backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}}
.top-in{{max-width:1080px;margin:0 auto;padding:16px 22px;
  display:flex;align-items:center;justify-content:space-between;gap:16px}}
.brand{{display:flex;align-items:center;gap:10px;font-weight:700;
  letter-spacing:-.02em;font-size:19px}}
.mark{{width:22px;height:22px;flex:none}}
.nav{{border-bottom:1px solid var(--line);overflow-x:auto;-webkit-overflow-scrolling:touch}}
.nav-in{{max-width:1080px;margin:0 auto;padding:0 22px;display:flex;gap:28px;
  white-space:nowrap}}
.nav a{{color:var(--mid);text-decoration:none;font-size:14.5px;padding:14px 0;
  border-bottom:2px solid transparent}}
.nav a:hover{{color:var(--fg)}}
.nav a.on{{color:var(--fg);border-bottom-color:var(--accent)}}

.wrap{{max-width:1080px;margin:0 auto;padding:0 22px}}
section{{padding:76px 0;border-bottom:1px solid var(--line)}}
section:last-of-type{{border-bottom:0}}

/* ---- type ---- */
.eyebrow{{font-size:11.5px;text-transform:uppercase;letter-spacing:.2em;
  color:var(--dim);margin:0 0 18px}}
h1{{font-size:clamp(38px,7.5vw,64px);line-height:1.05;letter-spacing:-.035em;
  font-weight:700;margin:0 0 22px}}
h2{{font-size:clamp(27px,4.6vw,40px);line-height:1.12;letter-spacing:-.03em;
  font-weight:700;margin:0 0 18px}}
h3{{font-size:17px;letter-spacing:-.01em;font-weight:650;margin:0 0 8px}}
.lede{{font-size:clamp(16px,2.1vw,19px);color:var(--mid);max-width:60ch;margin:0 0 30px}}
.note{{color:var(--dim);font-size:14px;max-width:68ch}}
.hl{{color:var(--accent)}}

/* ---- buttons ---- */
.row{{display:flex;flex-wrap:wrap;gap:12px}}
.btn{{display:inline-block;padding:12px 22px;border-radius:8px;font-size:15px;
  font-weight:600;text-decoration:none;border:1px solid transparent;transition:.15s}}
.btn-p{{background:var(--fg);color:#08080a}}
.btn-p:hover{{background:var(--accent)}}
.btn-s{{background:var(--surface);color:var(--fg);border-color:var(--line)}}
.btn-s:hover{{border-color:var(--accent);color:var(--accent)}}

/* ---- terminal card ---- */
.term{{background:var(--surface);border:1px solid var(--line);border-radius:12px;
  overflow:hidden;margin-top:34px}}
.term-bar{{display:flex;align-items:center;gap:9px;padding:12px 16px;
  border-bottom:1px solid var(--line);font-family:var(--mono);font-size:12.5px;
  color:var(--dim)}}
.dot{{width:9px;height:9px;border-radius:50%;background:#2c2c31;flex:none}}
.live{{margin-left:auto;display:flex;align-items:center;gap:7px;
  color:var(--accent);font-size:11.5px;letter-spacing:.14em}}
.pulse{{width:7px;height:7px;border-radius:50%;background:var(--accent);
  animation:p 2s ease-in-out infinite}}
@keyframes p{{0%,100%{{opacity:1}}50%{{opacity:.25}}}}
.term-b{{padding:18px 16px;font-family:var(--mono);font-size:13.5px}}
.term-r{{display:flex;justify-content:space-between;gap:14px;padding:9px 0;
  border-bottom:1px solid var(--line)}}
.term-r:last-child{{border-bottom:0}}

/* ---- tiles & cards ---- */
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));
  gap:1px;background:var(--line);border:1px solid var(--line);border-radius:12px;
  overflow:hidden;margin:32px 0}}
.tile{{background:var(--surface);padding:20px 18px}}
.tile .n{{font-size:29px;font-weight:700;letter-spacing:-.035em;line-height:1.1;
  font-variant-numeric:tabular-nums}}
.tile .l{{font-size:11.5px;text-transform:uppercase;letter-spacing:.14em;
  color:var(--dim);margin-top:7px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(268px,1fr));gap:14px;margin-top:28px}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:22px}}
.card p{{color:var(--mid);font-size:14.5px;margin:0}}
.bul{{list-style:none;padding:0;margin:24px 0 0}}
.bul li{{display:flex;gap:13px;padding:7px 0;color:var(--mid);font-size:15px}}
.bul li::before{{content:"";width:6px;height:6px;border-radius:50%;
  background:var(--accent);flex:none;margin-top:10px}}

/* ---- tables ---- */
.scroll{{overflow-x:auto;-webkit-overflow-scrolling:touch;
  border:1px solid var(--line);border-radius:12px;margin-top:28px}}
table{{border-collapse:collapse;width:100%;min-width:620px;font-size:14.5px}}
th{{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.14em;
  color:var(--dim);font-weight:600;padding:14px 16px;background:var(--raised);
  border-bottom:1px solid var(--line);white-space:nowrap}}
td{{padding:14px 16px;border-bottom:1px solid var(--line);vertical-align:top}}
tr:last-child td{{border-bottom:0}}
.num{{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums;
  white-space:nowrap}}
.pos{{color:var(--pos)}} .neg{{color:var(--neg)}} .dim{{color:var(--dim)}}
.mid{{color:var(--mid)}}
.tag{{display:inline-block;font-size:11px;font-family:var(--mono);
  padding:3px 9px;border-radius:5px;border:1px solid var(--line);
  color:var(--dim);white-space:nowrap;text-transform:uppercase;letter-spacing:.08em}}
.tag.on{{color:var(--accent);border-color:var(--accent-dim);
  background:rgba(0,217,236,.07)}}
.empty{{padding:44px 22px;text-align:center;color:var(--dim);font-size:14.5px}}

pre{{background:var(--surface);border:1px solid var(--line);border-radius:12px;
  padding:20px;overflow-x:auto;font-family:var(--mono);font-size:13.5px;
  line-height:1.75;color:var(--mid);margin-top:28px}}
pre b{{color:var(--fg);font-weight:400}}

footer{{padding:44px 0 72px;color:var(--dim);font-size:13.5px}}
footer a{{color:var(--mid)}}
@media(max-width:640px){{section{{padding:54px 0}}}}
"""

MARK = (
    '<svg class="mark" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    f'<path d="M4 7h16M4 12h16M4 17h16" stroke="{ACCENT}" stroke-width="1.6" '
    'stroke-linecap="round" opacity=".35"/>'
    f'<path d="M12 3v18" stroke="{ACCENT}" stroke-width="1.8" stroke-linecap="round"/>'
    f'<circle cx="12" cy="12" r="3.4" fill="{ACCENT}"/></svg>'
)
