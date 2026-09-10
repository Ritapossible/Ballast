"""Visual system and page shell for the public site.

Dark, editorial, centred display type over atmospheric backdrops - the house style
of the reference design - with Bitget's cyan as the single accent.

The backdrops are pure CSS gradients rather than photography. That is a deliberate
constraint, not a compromise: the site ships as self-contained HTML with no CDN, no
web fonts, no scripts and no external images, so nothing can 404, hang or be
rate-limited when a judge opens it. Tests assert the absence of external hosts.
"""

ACCENT = "#00d9ec"
ACCENT_DIM = "#0a8fa0"
REPO = "https://github.com/Ritapossible/Ballast"

CSS = f"""
:root{{
  --bg:#070708; --surface:#101012; --raised:#16161a; --line:#242429;
  --fg:#fafafa; --mid:#a6a6ad; --dim:#6c6c75;
  --accent:{ACCENT}; --accent-dim:{ACCENT_DIM};
  --pos:#4ade80; --neg:#fb7185;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;
}}
*{{box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%;scroll-behavior:smooth}}
body{{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);
  font-size:16px;line-height:1.65;-webkit-font-smoothing:antialiased;
  overflow-wrap:break-word}}
html{{overflow-x:clip}}
img,svg,table,pre{{max-width:100%}}
.wrap,.narrow,.docs,.prose{{min-width:0}}
section[id]{{scroll-margin-top:112px}}
a{{color:inherit}}

/* ---- chrome ---- */
.chrome{{position:sticky;top:0;z-index:30;background:rgba(7,7,8,.94);
  backdrop-filter:blur(14px)}}
.top{{border-bottom:1px solid var(--line)}}
.top-in{{max-width:1120px;margin:0 auto;padding:15px 22px;
  display:flex;align-items:center;justify-content:space-between;gap:16px}}
.brand{{display:flex;align-items:center;gap:11px;font-weight:700;
  letter-spacing:-.01em;font-size:20px;text-decoration:none}}
.mark{{width:24px;height:24px;flex:none}}
.nav{{border-bottom:1px solid var(--line);
  overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none}}
.nav::-webkit-scrollbar{{display:none}}
.nav-in{{max-width:1120px;margin:0 auto;padding:0 22px;display:flex;gap:30px;white-space:nowrap}}
.nav a{{color:var(--mid);text-decoration:none;font-size:15px;padding:14px 0;
  border-bottom:2px solid transparent}}
.nav a:hover{{color:var(--fg)}}
.nav a.on{{color:var(--fg);border-bottom-color:var(--accent)}}

.wrap{{max-width:1120px;margin:0 auto;padding:0 22px}}
.narrow{{max-width:780px;margin:0 auto}}
section{{padding:88px 0;border-bottom:1px solid var(--line);position:relative}}
section:last-of-type{{border-bottom:0}}

/* ---- atmospheric backdrops (pure CSS, no images) ---- */
.bd{{position:relative;isolation:isolate;border-bottom:1px solid var(--line)}}
.bd::before{{content:"";position:absolute;inset:0;z-index:-1;
  background:
    radial-gradient(120% 90% at 50% -20%,rgba(0,217,236,.13),transparent 62%),
    radial-gradient(80% 70% at 15% 110%,rgba(0,217,236,.06),transparent 60%),
    linear-gradient(180deg,#0b0b0f 0%,#070708 100%);}}
.bd::after{{content:"";position:absolute;inset:0;z-index:-1;opacity:.5;
  background-image:linear-gradient(rgba(255,255,255,.03) 1px,transparent 1px),
    linear-gradient(90deg,rgba(255,255,255,.03) 1px,transparent 1px);
  background-size:64px 64px;
  -webkit-mask-image:radial-gradient(90% 70% at 50% 30%,#000,transparent 78%);
  mask-image:radial-gradient(90% 70% at 50% 30%,#000,transparent 78%)}}
.bd-deep::before{{background:
    radial-gradient(100% 80% at 50% 0%,rgba(0,217,236,.09),transparent 58%),
    linear-gradient(180deg,#0a0a0d 0%,#070708 70%)}}

/* ---- type ---- */
.eyebrow{{font-size:11.5px;text-transform:uppercase;letter-spacing:.24em;
  color:var(--dim);margin:0 0 20px}}
h1{{font-size:clamp(38px,7.4vw,66px);line-height:1.04;letter-spacing:-.035em;
  font-weight:700;margin:0 0 24px}}
h2{{font-size:clamp(28px,5vw,46px);line-height:1.1;letter-spacing:-.032em;
  font-weight:700;margin:0 0 20px}}
h3{{font-size:19px;letter-spacing:-.015em;font-weight:650;margin:0 0 10px}}
h4{{font-size:15px;font-weight:650;margin:30px 0 8px;letter-spacing:-.005em}}
.lede{{font-size:clamp(16px,2.1vw,19.5px);color:var(--mid);margin:0 0 32px}}
.note{{color:var(--dim);font-size:14px}}
.hl{{color:var(--accent)}}
.center{{text-align:center}}
.center .lede{{margin-left:auto;margin-right:auto;max-width:62ch}}
.center .row{{justify-content:center}}
p{{margin:0 0 16px}}

/* ---- buttons ---- */
.row{{display:flex;flex-wrap:wrap;gap:12px}}
.btn{{display:inline-block;padding:13px 24px;border-radius:9px;font-size:15px;
  font-weight:600;text-decoration:none;border:1px solid transparent;transition:.15s}}
.btn-p{{background:var(--fg);color:#07070a}}
.btn-p:hover{{background:var(--accent)}}
.btn-s{{background:rgba(255,255,255,.04);color:var(--fg);border-color:var(--line)}}
.btn-s:hover{{border-color:var(--accent);color:var(--accent)}}

/* ---- terminal ---- */
.term{{background:rgba(16,16,18,.82);border:1px solid var(--line);border-radius:14px;
  overflow:hidden;margin:40px auto 0;max-width:720px;text-align:left}}
.term-bar{{display:flex;align-items:center;gap:9px;padding:13px 17px;
  border-bottom:1px solid var(--line);font-family:var(--mono);font-size:12.5px;color:var(--dim)}}
.dot{{width:9px;height:9px;border-radius:50%;background:#2b2b31;flex:none}}
.live{{margin-left:auto;display:flex;align-items:center;gap:7px;
  color:var(--accent);font-size:11px;letter-spacing:.16em}}
.pulse{{width:7px;height:7px;border-radius:50%;background:var(--accent);
  animation:p 2.2s ease-in-out infinite}}
@keyframes p{{0%,100%{{opacity:1}}50%{{opacity:.2}}}}
.term-b{{padding:8px 17px 14px;font-family:var(--mono);font-size:13.5px}}
.term-r{{display:flex;justify-content:space-between;gap:14px;padding:10px 0;
  border-bottom:1px solid var(--line)}}
.term-r:last-child{{border-bottom:0}}

/* ---- tiles / cards ---- */
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
  gap:1px;background:var(--line);border:1px solid var(--line);border-radius:14px;
  overflow:hidden;margin:36px 0;text-align:left}}
.tile{{background:var(--surface);padding:22px 20px}}
.tile .n{{font-size:30px;font-weight:700;letter-spacing:-.035em;line-height:1.1;
  font-variant-numeric:tabular-nums}}
.tile .l{{font-size:11.5px;text-transform:uppercase;letter-spacing:.14em;
  color:var(--dim);margin-top:8px}}
.stack{{display:flex;flex-direction:column;gap:16px;margin-top:40px;text-align:left}}
.card{{background:rgba(16,16,18,.72);border:1px solid var(--line);
  border-radius:14px;padding:28px}}
.card p:last-child{{margin-bottom:0}}
.card p{{color:var(--mid);font-size:15.5px}}
.bul{{list-style:none;padding:0;margin:26px 0 0;text-align:left}}
.bul li{{position:relative;padding:8px 0 8px 24px;color:var(--mid);font-size:15.5px}}
.bul li::before{{content:"";position:absolute;left:2px;top:19px;
  width:6px;height:6px;border-radius:50%;background:var(--accent)}}

/* ---- tables ---- */
.scroll{{overflow-x:auto;-webkit-overflow-scrolling:touch;
  border:1px solid var(--line);border-radius:14px;margin-top:30px;text-align:left}}
table{{border-collapse:collapse;width:100%;min-width:560px;font-size:14.5px}}
th{{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.14em;
  color:var(--dim);font-weight:600;padding:14px 17px;background:var(--raised);
  border-bottom:1px solid var(--line);white-space:nowrap}}
td{{padding:14px 17px;border-bottom:1px solid var(--line);vertical-align:top}}
tr:last-child td{{border-bottom:0}}
.num{{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}}
.pos{{color:var(--pos)}} .neg{{color:var(--neg)}} .dim{{color:var(--dim)}} .mid{{color:var(--mid)}}
.tag{{display:inline-block;font-size:11px;font-family:var(--mono);padding:3px 9px;
  border-radius:5px;border:1px solid var(--line);color:var(--dim);
  white-space:nowrap;text-transform:uppercase;letter-spacing:.08em}}
.tag.on{{color:var(--accent);border-color:var(--accent-dim);background:rgba(0,217,236,.08)}}
.empty{{padding:46px 22px;text-align:center;color:var(--dim);font-size:14.5px}}

pre{{background:var(--surface);border:1px solid var(--line);border-radius:14px;
  padding:22px;overflow-x:auto;font-family:var(--mono);font-size:13.5px;
  line-height:1.75;color:var(--mid);margin:26px 0;text-align:left}}
pre b{{color:var(--fg);font-weight:400}}
code{{font-family:var(--mono);font-size:.9em;background:var(--surface);
  border:1px solid var(--line);border-radius:5px;padding:1px 6px;color:var(--fg)}}

/* ---- docs ---- */
.docs{{display:grid;grid-template-columns:216px 1fr;gap:56px;
  align-items:start;padding:60px 0}}
.toc{{position:sticky;top:120px;font-size:14px}}
.toc a{{display:block;color:var(--dim);text-decoration:none;padding:6px 0;
  border-left:2px solid var(--line);padding-left:14px}}
.toc a:hover{{color:var(--fg);border-left-color:var(--accent)}}
.toc .h{{font-size:11px;text-transform:uppercase;letter-spacing:.18em;
  color:var(--dim);margin:22px 0 10px;padding-left:14px}}
.toc .h:first-child{{margin-top:0}}
.prose h2{{font-size:26px;margin:56px 0 14px;scroll-margin-top:130px}}
.prose h2:first-child{{margin-top:0}}
.prose p,.prose li{{color:var(--mid);font-size:15.5px}}
.prose strong{{color:var(--fg);font-weight:620}}
.prose ul{{padding-left:20px}}
.prose li{{margin:7px 0}}
.callout{{border-left:3px solid var(--accent);background:rgba(0,217,236,.05);
  border-radius:0 10px 10px 0;padding:18px 22px;margin:24px 0}}
.callout p:last-child{{margin-bottom:0}}
@media(max-width:860px){{
  .docs{{grid-template-columns:1fr;gap:0;padding:34px 0}}
  .toc{{position:sticky;top:104px;z-index:20;display:flex;gap:8px;
    overflow-x:auto;scrollbar-width:none;margin:0 0 30px;padding:12px 0;
    background:rgba(7,7,8,.96);backdrop-filter:blur(14px);
    border-bottom:1px solid var(--line)}}
  .toc::-webkit-scrollbar{{display:none}}
  .toc .h{{display:none}}
  .toc a{{border-left:0;border:1px solid var(--line);border-radius:99px;
    padding:7px 15px;white-space:nowrap;font-size:13.5px}}
  .toc a:hover{{border-color:var(--accent)}}
  .prose h2{{scroll-margin-top:170px;font-size:23px;margin:44px 0 12px}}
}}
@media(max-width:700px){{
  .tiles{{grid-template-columns:1fr 1fr}}
  .tiles .tile:last-child:nth-child(odd){{grid-column:1/-1}}
  .tile .n{{font-size:25px}}
}}
@media(max-width:640px){{
  section{{padding:56px 0}}
  .top-in{{padding:12px 18px}}
  .nav-in{{padding:0 18px;gap:22px}}
  .wrap{{padding:0 18px}}
  .brand{{font-size:18px}}
  .btn{{padding:11px 18px;font-size:14.5px}}
  h1{{letter-spacing:-.03em}}
  .card{{padding:22px 20px}}
  .term{{margin-top:32px}}
  section[id]{{scroll-margin-top:104px}}
}}
@media(max-width:380px){{
  .top-in .btn{{padding:9px 14px;font-size:13.5px}}
  .nav-in{{gap:18px}}
}}

footer{{padding:48px 0 76px;color:var(--dim);font-size:13.5px}}
footer a{{color:var(--mid)}}
"""

MARK = (
    '<svg class="mark" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    f'<path d="M5 8h14M5 16h14" stroke="{ACCENT}" stroke-width="1.5" '
    'stroke-linecap="round" opacity=".38"/>'
    f'<path d="M12 2.5v19" stroke="{ACCENT}" stroke-width="1.7" stroke-linecap="round"/>'
    f'<circle cx="12" cy="12" r="3.6" fill="{ACCENT}"/></svg>'
)


NAV = [("Overview", "index.html"), ("Tonight", "tonight.html"),
       ("Settled", "settled.html"), ("Evidence", "evidence.html"),
       ("Docs", "docs.html"), ("Repo", REPO)]


def nav(active: str, prefix: str = "") -> str:
    items = [(label, href if href.startswith("http") else f"{prefix}{href}")
             for label, href in NAV]
    links = "".join(
        f'<a class="{"on" if label == active else ""}" href="{href}">{label}</a>'
        for label, href in items)
    return (f'<div class="chrome"><header class="top"><div class="top-in">'
            f'<a class="brand" href="{prefix}index.html">{MARK}BALLAST</a>'
            f'<a class="btn btn-p" href="{prefix}tonight.html">See tonight</a>'
            f'</div></header><nav class="nav"><div class="nav-in">{links}</div></nav></div>')


def page(title: str, description: str, active: str, body: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{title}</title><meta name="description" content="{description}">'
        '<link rel="icon" href="favicon.ico" sizes="32x32">'
        '<link rel="icon" href="favicon.svg" type="image/svg+xml">'
        '<link rel="apple-touch-icon" href="apple-touch-icon.png">'
        '<link rel="manifest" href="site.webmanifest">'
        '<meta name="theme-color" content="#070708">'
        f'<style>{CSS}</style></head><body>{nav(active)}<main>{body}</main>'
        f'<footer><div class="wrap">Ballast - overnight risk transfer for tokenized '
        f'US stocks.<br><a href="{REPO}">source</a> · paper trading only, '
        f'not financial advice.</div></footer></body></html>')
