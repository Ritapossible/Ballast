/* Coverage lookup: "can Ballast protect the position I actually hold?"
 *
 * The site could say how MANY names have a hedgeable perp but never WHICH, so a
 * visitor holding one of the 1,173 rTokens had no way to ask about their own.
 * This reads docs/coverage.json -- rebuilt on a schedule from the live listing,
 * with every fit measured rather than asserted -- and answers for any of them.
 *
 * It deliberately does NOT answer "would Ballast hedge this tonight". That
 * question is only meaningful for a position in the book, and its answer is a
 * ledger entry written before the outcome was known. Inventing one on demand
 * here would look identical to a recorded decision and be worth nothing.
 */
(function () {
  "use strict";

  var root = document.getElementById("lookup");
  if (!root) return;

  var input = root.querySelector("[data-role=input]");
  var out = root.querySelector("[data-role=out]");
  var hint = root.querySelector("[data-role=hint]");
  var book = (root.getAttribute("data-book") || "")
    .split(",").filter(Boolean);

  var data = null;
  var covered = {};
  var uncovered = {};

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;",
               '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* Accepts TSLA, tsla, rTSLA, RTSLAUSDT -- whatever the holder has in front of
   * them. Strips the quote coin first so "RFUSDT" does not become "FUSD". */
  function normalise(raw) {
    var t = String(raw).trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (t.length > 4 && t.slice(-4) === "USDT") t = t.slice(0, -4);
    if (t.length > 1 && t.charAt(0) === "R" && covered[t] === undefined
        && uncovered[t] === undefined) {
      var stripped = t.slice(1);
      if (covered[stripped] !== undefined || uncovered[stripped] !== undefined) {
        return stripped;
      }
    }
    return t;
  }

  function tile(n, l) {
    return '<div class="tile"><div class="n">' + esc(n) +
           '</div><div class="l">' + esc(l) + "</div></div>";
  }

  function card(cls, title, body) {
    return '<div class="card ' + cls + '"><h3>' + title + "</h3>" + body + "</div>";
  }

  /* A perp that exists is not a hedge. 34 rTokens collide with a crypto perp of
   * the same ticker and were paired against it until 2026-09-15; the measured
   * R^2 is what exposes a pair like that, so it is shown, not hidden. */
  function quality(row) {
    if (row.r2 >= 0.9) {
      return "<p class=\"note\">The perp tracked this token closely over the " +
        "window, so a hedge would have removed most of the overnight move.</p>";
    }
    if (row.r2 >= 0.5) {
      return "<p class=\"note\"><strong>Tracking is loose.</strong> A hedge " +
        "would leave a material part of the move in place. Treat the cost as " +
        "certain and the protection as partial.</p>";
    }
    return "<p class=\"note\"><strong>This pair does not track.</strong> The " +
      "perp shares a ticker with the token but moves independently of it. " +
      "Ballast would not treat this as a hedge.</p>";
  }

  function renderCovered(t, row) {
    var inBook = book.indexOf(t) !== -1;
    var body = "";
    if (row.fit) {
      body += '<div class="tiles">' +
        tile("β " + row.beta.toFixed(2), "hedge ratio") +
        tile(row.r2.toFixed(3), "variance tracked") +
        tile(row.typical_bp.toFixed(0) + " bp", "typical overnight move") +
        tile(data.hedge_cost_bp.toFixed(1) + " bp", "cost to protect") +
        "</div>";
      body += quality(row);
      body += '<p class="note">Measured over ' + esc(row.nights) +
        " paired nights ending " + esc(data.measured_on) + ". " +
        esc(row.spot) + " against " + esc(row.perp) + ".</p>";
    } else {
      body += '<p class="note">A matching stock perp is listed (' +
        esc(row.perp) + '), but there are only ' + esc(row.nights) +
        " paired nights of history so far — not enough to measure how well it " +
        "tracks. Ballast will not hedge a pair it cannot measure.</p>";
    }
    body += inBook
      ? '<p class="note"><strong>This name is in tonight\'s book.</strong> ' +
        'Its call for tonight is on this page, above.</p>'
      : '<p class="note">Not in the demo book, so no decision is recorded for ' +
        'it. Ballast only ever acts on a position it did not open.</p>';
    return card("ok", "Ballast can hedge r" + esc(t), body);
  }

  function renderUncovered(t) {
    return card("no", "Ballast cannot hedge r" + esc(t),
      '<p class="note">Bitget lists <strong>r' + esc(t) + "</strong> on spot, " +
      "but there is no matching <em>stock</em> perpetual to short against it. " +
      "There is nothing to transfer the overnight risk to, so Ballast refuses " +
      "the position rather than approximating a hedge. " + esc(data.counts.uncovered) +
      " of the " + esc(data.counts.rtokens) + " listed rTokens are in this half.</p>");
  }

  function renderUnknown(t) {
    var near = Object.keys(covered).concat(Object.keys(uncovered))
      .filter(function (k) { return k.indexOf(t) === 0; }).sort().slice(0, 8);
    return card("no", "Not a listed tokenized stock",
      "<p class=\"note\">Bitget does not list <strong>r" + esc(t) +
      "</strong> as an rToken, so there is no position here for Ballast to " +
      "protect.</p>" + (near.length
        ? '<p class="note">Close matches: ' + near.map(function (k) {
            return "<strong>" + esc(k) + "</strong>";
          }).join(", ") + ".</p>"
        : ""));
  }

  function show(raw) {
    if (!data) return;
    var t = normalise(raw);
    if (!t) { out.innerHTML = ""; return; }
    if (covered[t]) out.innerHTML = renderCovered(t, covered[t]);
    else if (uncovered[t]) out.innerHTML = renderUncovered(t);
    else out.innerHTML = renderUnknown(t);
  }

  function ready() {
    covered = {};
    data.covered.forEach(function (row) { covered[row.ticker] = row; });
    uncovered = {};
    data.uncovered.forEach(function (t) { uncovered[t] = true; });
    input.disabled = false;
    input.placeholder = "TSLA, AAPL, F, RNVDAUSDT…";
    hint.textContent = data.counts.covered + " of " + data.counts.rtokens +
      " listed rTokens have a stock perp to hedge against, measured " +
      data.measured_on + ".";
    input.addEventListener("input", function () { show(input.value); });
    if (input.value) show(input.value);
  }

  /* No data, no guessing. A lookup that silently answers from a stale bundle is
   * worse than one that says it is offline. */
  function failed() {
    input.disabled = true;
    input.placeholder = "unavailable";
    hint.textContent =
      "The coverage index could not be loaded, so this lookup is offline. " +
      "Nothing else on this page depends on it.";
  }

  try {
    fetch("coverage.json", { credentials: "omit" })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (j) { data = j; ready(); })
      .catch(failed);
  } catch (e) { failed(); }
})();
