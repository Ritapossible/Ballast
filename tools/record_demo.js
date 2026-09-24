// Records a silent screen capture of the published site, for the submission demo.
//
//   cd docs && python3 -m http.server 8731 &
//   PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node tools/record_demo.js
//
// It serves docs/ over plain HTTP on purpose. Recording the live HTTPS URL from
// inside a proxied container fails TLS verification, and the fix is not to turn
// verification off - docs/ holds the exact pages the nightly publishes and
// Vercel serves, and Playwright records the viewport with no browser chrome, so
// the result is visually identical.
//
// Output: ./demo/*.webm, 1280x720, about 60 seconds. Silent and uncut - add a
// voiceover or captions afterwards if you want them.
const { chromium } = require('playwright');
const BASE = 'http://127.0.0.1:8731';

// Smooth, readable scrolling. A judge watching this has to be able to read the
// numbers, so every pause is deliberate rather than a transition effect.
async function glide(p, to, ms = 2200) {
  await p.evaluate(async ([to, ms]) => {
    const start = window.scrollY;
    const dist = to - start;
    const t0 = performance.now();
    await new Promise(res => {
      function step(now) {
        const k = Math.min(1, (now - t0) / ms);
        const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        window.scrollTo(0, start + dist * e);
        k < 1 ? requestAnimationFrame(step) : res();
      }
      requestAnimationFrame(step);
    });
  }, [to, ms]);
}

async function section(p, path, stops) {
  // Resilient on purpose: the video is only written when the context closes, so
  // one slow page must not throw away the whole recording.
  try {
    await p.goto(BASE + path, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await p.waitForLoadState('load', { timeout: 20000 }).catch(() => {});
    await p.waitForTimeout(1800);
    for (const [y, hold] of stops) { await glide(p, y); await p.waitForTimeout(hold); }
    console.log('  ok ' + (path || '/'));
  } catch (e) {
    console.log('  SKIPPED ' + (path || '/') + ' - ' + e.message.split('\n')[0]);
  }
}

(async () => {
  const b = await chromium.launch();
  const c = await b.newContext({
    recordVideo: { dir: './demo', size: { width: 1280, height: 720 } },
    viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2,
  });
  const p = await c.newPage();

  // 1. The claim.
  await section(p, '/index.html', [[520, 2600], [1150, 2400]]);
  // 2. Tonight - the refusals, and the execution line that says nothing was sent.
  await section(p, '/tonight.html', [[420, 2800], [1000, 2600]]);
  // 3. Settled - the metrics the track scores, and how each hedge was filled.
  await section(p, '/settled.html', [[600, 2600], [1250, 3000], [1900, 3000]]);
  // 4. Evidence - the measurement behind the claim.
  await section(p, '/evidence.html', [[500, 2600], [1100, 2400]]);
  // 5. Docs - the Bitget toolchain, stated rather than implied.
  await section(p, '/docs.html', [[700, 2600], [1400, 2800]]);

  await c.close();
  await b.close();
  console.log('DONE');
})().catch(e => { console.log('FATAL', e.message.split('\n')[0]); process.exit(1); });
