/* Drives the real coverage lookup in a real browser, under the real CSP.
 *
 *   NODE_PATH=$(npm root -g) node tools/check_lookup.mjs
 *
 * The unit tests can only see that the markup was rendered. They cannot see that
 * the script was allowed to run, that the fetch was allowed, or that a ticker
 * typed into the box produces the right verdict - and a `script-src` that forbids
 * the file fails silently, leaving a page that looks perfect and does nothing.
 * So this serves docs/ with the Content-Security-Policy taken from vercel.json,
 * not a copy of it, and asserts on what the page actually shows.
 */
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { createRequire } from "node:module";
import { execSync } from "node:child_process";

/* Playwright is a developer tool, not a dependency of the product, so this repo
 * has no package.json to pin it in. Take it from a local install if one exists
 * (CI does `npm install --no-save playwright`) and otherwise from the global
 * root, rather than adding it to the tree. */
const { chromium } = (() => {
  const roots = [import.meta.url];
  try { roots.push(`${execSync("npm root -g").toString().trim()}/`); } catch { /* no npm */ }
  for (const root of roots) {
    try { return createRequire(root)("playwright"); } catch { /* try the next */ }
  }
  throw new Error("playwright not found - run `npm install playwright`");
})();

/* SITE_DIR points at a tree built from the CURRENT source (see
 * tools/build_preview.py). Without it this serves docs/, which is the last
 * DEPLOYED build - useful for checking what is live, wrong for checking a change
 * that the scheduled rebuild has not published yet. CI always passes SITE_DIR. */
const ROOT = process.env.SITE_DIR
  ? `${process.env.SITE_DIR.replace(/\/?$/, "/")}`
  : new URL("../docs/", import.meta.url).pathname;
const VERCEL = new URL("../vercel.json", import.meta.url).pathname;

const TYPES = { ".html": "text/html", ".js": "text/javascript",
                ".json": "application/json", ".svg": "image/svg+xml",
                ".png": "image/png", ".ico": "image/x-icon" };

const csp = JSON.parse(await readFile(VERCEL, "utf8"))
  .headers.flatMap((h) => h.headers)
  .find((h) => h.key === "Content-Security-Policy").value;

const server = createServer(async (req, res) => {
  const rel = normalize(decodeURIComponent(req.url.split("?")[0]))
    .replace(/^(\.\.[/\\])+/, "");
  try {
    const body = await readFile(join(ROOT, rel));
    res.writeHead(200, {
      "Content-Type": TYPES[extname(rel)] ?? "application/octet-stream",
      "Content-Security-Policy": csp,
    });
    res.end(body);
  } catch {
    res.writeHead(404).end("not found");
  }
});
await new Promise((r) => server.listen(0, r));
const base = `http://127.0.0.1:${server.address().port}`;

/* CHROMIUM_PATH pins a browser already on the machine, for a sandbox whose
 * Playwright build differs from the one it shipped with. Unset, Playwright uses
 * its own download as usual. */
const browser = await chromium.launch(
  process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
const page = await browser.newPage();

const violations = [];
page.on("console", (m) => {
  const t = m.text();
  if (/Content Security Policy|Refused to/i.test(t)) violations.push(t);
});
page.on("pageerror", (e) => violations.push(`pageerror: ${e.message}`));

const failures = [];
const check = (name, ok, detail = "") =>
  ok ? console.log(`  ok    ${name}`)
     : failures.push(`${name}${detail ? ` -- ${detail}` : ""}`);

await page.goto(`${base}/tonight.html`, { waitUntil: "networkidle" });

const box = page.locator("#lookup [data-role=input]");
const out = page.locator("#lookup [data-role=out]");

/* The index has to actually arrive: a disabled box means the fetch was blocked,
 * which is the exact failure a CSP mistake produces. */
await box.waitFor({ state: "visible" });
check("the input is enabled once the index loads", !(await box.isDisabled()),
      await page.locator("#lookup [data-role=hint]").innerText());

const cases = [
  ["TSLA", /can hedge rTSLA/i, "a covered name in the book"],
  ["TSLA", /in tonight's book/i, "and is marked as being in the book"],
  ["AAPL", /can hedge rAAPL/i, "a covered name outside the book"],
  ["AAPL", /Not in the demo book/i, "and is marked as outside it"],
  ["F", /cannot hedge rF/i, "the Ford/crypto-F collision is refused"],
  ["SUI", /cannot hedge rSUI/i, "the SUI collision is refused"],
  ["RNVDAUSDT", /can hedge rNVDA/i, "a full spot symbol is accepted"],
  ["rmsft", /can hedge rMSFT/i, "lower case with the r prefix is accepted"],
  ["ZZQQ", /Not a listed tokenized stock/i, "an unlisted ticker says so"],
];
for (const [typed, want, name] of cases) {
  await box.fill(typed);
  await out.waitFor({ state: "visible" });
  const text = await out.innerText();
  check(name, want.test(text), `typed ${typed}, got: ${text.slice(0, 90)}`);
}

/* The measured figures must reach the card, not just the verdict. */
await box.fill("TSLA");
const tsla = await out.innerText();
check("the card shows a hedge ratio and tracking", /β\s*[\d.]/.test(tsla) && /variance tracked/i.test(tsla), tsla.slice(0, 120));

/* It must never imply a decision it did not record. */
check("no invented decision language",
      !/would hedge tonight|HEDGE tonight|recommends/i.test(tsla), tsla.slice(0, 120));

check("no CSP violations or page errors", violations.length === 0,
      violations.join(" | "));

await browser.close();
server.close();

if (failures.length) {
  console.error(`\n${failures.length} check(s) FAILED:`);
  for (const f of failures) console.error(`  FAIL  ${f}`);
  process.exit(1);
}
console.log("\nlookup ok");
