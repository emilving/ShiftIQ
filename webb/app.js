/* NHL Game Score – startsidan. Läser data/sasong.json som byggs av bygg_sida.py. */
(function () {
  'use strict';
  var MAN = ['januari', 'februari', 'mars', 'april', 'maj', 'juni', 'juli', 'augusti', 'september', 'oktober', 'november', 'december'];
  var MAN_K = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];
  var DAG = ['söndag', 'måndag', 'tisdag', 'onsdag', 'torsdag', 'fredag', 'lördag'];
  var MIN = 3;

  var D = null;
  var formel = 'plus';
  var state = { lag: '', pos: '', min: true, q: '', sort: 'avg' };

  function $(s) { return document.querySelector(s); }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function f2(v) { return v == null || isNaN(v) ? '–' : (v < 0 ? '−' : '') + Math.abs(v).toFixed(2); }
  function tier(v) { return v < 0 ? 'var(--svag)' : v < 1 ? 'var(--godk)' : v < 2 ? 'var(--bra)' : 'var(--lys)'; }
  function datum(s, kort) {
    var d = new Date(s + 'T12:00:00');
    return kort ? d.getDate() + ' ' + MAN_K[d.getMonth()] : d.getDate() + ' ' + MAN[d.getMonth()];
  }
  function dagRubrik(s) {
    var d = new Date(s + 'T12:00:00');
    var t = DAG[d.getDay()];
    return t.charAt(0).toUpperCase() + t.slice(1) + ' ' + d.getDate() + ' ' + MAN[d.getMonth()];
  }
  function avg(p) { return formel === 'plus' ? p.pl : p.gs; }
  function sum(p) { return formel === 'plus' ? p.plS : p.gsS; }
  function td(tr, text, cls) { var c = el('td', cls, text); tr.appendChild(c); return c; }
  function barCell(tr, v, lo, hi, color) {
    var c = el('td', 'barc');
    var box = el('div', 'bar');
    var span = hi - lo || 1;
    var x = function (t) { return (t - lo) / span * 100; };
    var i = el('i');
    i.style.left = Math.min(x(0), x(v)) + '%';
    i.style.width = Math.max(0.6, Math.abs(x(v) - x(0))) + '%';
    i.style.background = color;
    i.style.borderRadius = v >= 0 ? '0 4px 4px 0' : '4px 0 0 4px';
    var z = el('b');
    z.style.left = x(0) + '%';
    box.appendChild(i); box.appendChild(z); c.appendChild(box); tr.appendChild(c);
  }
  function domain(vals) {
    var lo = 0, hi = 0.5;
    vals.forEach(function (v) { if (v < lo) lo = v; if (v > hi) hi = v; });
    return [lo, hi];
  }

  // ---------- flikar ----------
  var current = 'spelare';
  function show(id, scroll) {
    if (!document.getElementById(id)) return;
    current = id;
    document.querySelectorAll('.tab').forEach(function (t) { t.setAttribute('aria-selected', String(t.dataset.tab === id)); });
    document.querySelectorAll('.panel').forEach(function (p) { p.hidden = p.id !== id; });
    if (history.replaceState) history.replaceState(null, '', '#' + id);
    drawPanel();
    if (scroll) $('.tabs').scrollIntoView({ block: 'start', behavior: 'smooth' });
  }
  document.querySelectorAll('.tab').forEach(function (t) { t.addEventListener('click', function () { show(t.dataset.tab); }); });

  // ---------- formel ----------
  document.querySelectorAll('[data-formel]').forEach(function (b) {
    b.addEventListener('click', function () {
      if (b.disabled) return;
      formel = b.dataset.formel;
      document.querySelectorAll('[data-formel]').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
      drawAll();
    });
  });

  // ---------- filter ----------
  $('#f-lag').addEventListener('change', function (e) { state.lag = e.target.value; drawPlayers(); });
  document.querySelectorAll('#f-pos button').forEach(function (b) {
    b.addEventListener('click', function () {
      state.pos = b.dataset.pos;
      document.querySelectorAll('#f-pos button').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
      drawPlayers();
    });
  });
  $('#f-min').addEventListener('change', function (e) { state.min = e.target.checked; drawPlayers(); });
  $('#f-q').addEventListener('input', function (e) { state.q = e.target.value.trim().toLowerCase(); drawPlayers(); });
  document.querySelectorAll('#t-spelare th button').forEach(function (b) {
    b.addEventListener('click', function () { state.sort = b.dataset.sort; drawPlayers(); });
  });

  // ---------- huvud ----------
  function drawHead() {
    $('#title').textContent = 'NHL ' + D.sasong;
    $('#period').textContent = datum(D.forsta) + ' – ' + datum(D.sista);
    $('#updated').textContent = 'Uppdaterad ' + D.uppdaterad;
    var skaters = D.spelare.filter(function (p) { return p.gp >= MIN && avg(p) != null; }).sort(function (a, b) { return avg(b) - avg(a); });
    var goalie = D.mv.filter(function (p) { return p.gp >= MIN && avg(p) != null; }).sort(function (a, b) { return avg(b) - avg(a); })[0];
    var best = skaters[0];
    var w = D.vinnare[formel === 'plus' ? 'pl' : 'gs'];
    var take = $('#take');
    take.textContent = best
      ? best.n + ' (' + best.lag + ') har högst snitt i ligan, ' + f2(avg(best)) + ' per match. Laget med högst sammanlagd Game Score har vunnit ' + w[0] + ' av ' + w[1] + ' matcher.'
      : '';

    var stars = $('#stars');
    stars.textContent = '';
    function tile(rank, p, label) {
      var t = el('div', 'star');
      var r = el('div', rank === 'MV' ? 'rank mv' : 'rank', rank);
      r.style.color = tier(avg(p));
      var info = el('div'); info.style.minWidth = '0';
      if (label) info.appendChild(el('div', 'lbl', label));
      info.appendChild(el('div', 'nm', p.n));
      info.appendChild(el('div', 'sub', p.k + ', snitt ' + f2(avg(p)) + ', ' + p.gp + ' matcher'));
      t.appendChild(r); t.appendChild(info);
      return t;
    }
    skaters.slice(0, 3).forEach(function (p, i) { stars.appendChild(tile(String(i + 1), p, '')); });
    if (goalie) stars.appendChild(tile('MV', goalie, 'Bästa målvakt'));

    $('#f-matcher').textContent = String(D.matcher.length);
    $('#f-spelare').textContent = String(D.spelare.length + D.mv.length);
    $('#f-vinnare').textContent = w[1] ? Math.round(w[0] / w[1] * 100) + ' %' : '–';
    $('#sign').textContent = D.namn ? 'Design och statistik: ' + D.namn : '';
    if (D.excel) {
      var dl = $('#dl');
      dl.textContent = '';
      dl.appendChild(document.createTextNode('All statistik finns också som '));
      var a = el('a', null, 'Excel-fil');
      a.href = D.excel;
      dl.appendChild(a);
      dl.appendChild(document.createTextNode(', med en flik per tabell.'));
    }
  }

  // ---------- spelare ----------
  function drawPlayers() {
    var list = D.spelare.filter(function (p) {
      return (!state.lag || p.lag === state.lag) && (!state.pos || p.pos === state.pos) &&
        (!state.min || p.gp >= MIN) && avg(p) != null &&
        (!state.q || p.n.toLowerCase().indexOf(state.q) >= 0 || p.lag.toLowerCase().indexOf(state.q) >= 0);
    });
    var key = { avg: avg, sum: sum, gp: function (p) { return p.gp; }, p: function (p) { return p.p; } }[state.sort];
    list.sort(function (a, b) { return (key(b) - key(a)) || (avg(b) - avg(a)); });
    document.querySelectorAll('#t-spelare th button').forEach(function (b) {
      b.parentElement.setAttribute('aria-sort', b.dataset.sort === state.sort ? 'descending' : 'none');
    });
    var dom = domain(list.map(avg));
    var tb = $('#t-spelare tbody');
    tb.textContent = '';
    list.forEach(function (p, i) {
      var tr = el('tr');
      td(tr, String(i + 1), 'rk');
      td(tr, p.n, 'nm');
      td(tr, p.k, 'm hn');
      td(tr, p.pos, 'm hn');
      td(tr, String(p.gp), 'n hn');
      barCell(tr, avg(p), dom[0], dom[1], tier(avg(p)));
      td(tr, f2(avg(p)), 'n val');
      td(tr, f2(sum(p)), 'n hn');
      td(tr, String(p.p), 'n hn');
      tb.appendChild(tr);
    });
    if (!list.length) { var tr = el('tr'); var c = td(tr, 'Inga spelare matchar filtret.', 'empty'); c.colSpan = 9; tb.appendChild(tr); }
    $('#c-spelare').textContent = list.length ? list.length + ' spelare' : '';
  }

  // ---------- lag ----------
  function pickTeam(lag) {
    state.lag = lag;
    $('#f-lag').value = lag;
    show('spelare', true);
  }
  function drawTeams() {
    var best = {};
    D.spelare.forEach(function (p) {
      if (p.gp < MIN || avg(p) == null) return;
      if (!best[p.lag] || avg(p) > avg(best[p.lag])) best[p.lag] = p;
    });
    var list = D.lag.slice().sort(function (a, b) { return (b.pts - a.pts) || ((b.pts / b.gp) - (a.pts / a.gp)) || ((b.gf - b.ga) - (a.gf - a.ga)); });
    var dom = domain(list.map(avg));
    var tb = $('#t-lag tbody');
    tb.textContent = '';
    list.forEach(function (t, i) {
      var tr = el('tr', 'click');
      tr.tabIndex = 0;
      td(tr, String(i + 1), 'rk');
      td(tr, t.lag, 'nm');
      td(tr, String(t.gp), 'n');
      td(tr, String(t.w), 'n');
      td(tr, String(t.l), 'n hn');
      td(tr, String(t.otl), 'n hn');
      td(tr, String(t.pts), 'n val');
      td(tr, t.gf + '–' + t.ga, 'n hn');
      barCell(tr, avg(t), dom[0], dom[1], avg(t) >= 0 ? 'var(--bra)' : 'var(--svag)');
      td(tr, f2(avg(t)), 'n val');
      td(tr, best[t.lag] ? best[t.lag].n : '', 'm hn');
      tr.addEventListener('click', function () { pickTeam(t.lag); });
      tr.addEventListener('keydown', function (e) { if (e.key === 'Enter') pickTeam(t.lag); });
      tb.appendChild(tr);
    });
  }

  // ---------- målvakter ----------
  function drawGoalies() {
    $('#n-mv').textContent = formel === 'plus'
      ? 'Game Score+ för målvakter bygger på räddade mål över förväntan (GSAx). Noll är en normal insats.'
      : 'Originalformeln ger plus för varje räddning och minus för varje insläppt mål.';
    var list = D.mv.filter(function (p) { return avg(p) != null; }).sort(function (a, b) { return (avg(b) - avg(a)) || (b.gp - a.gp); });
    var dom = domain(list.map(avg));
    var tb = $('#t-mv tbody');
    tb.textContent = '';
    list.forEach(function (p, i) {
      var tr = el('tr');
      td(tr, String(i + 1), 'rk');
      td(tr, p.n, 'nm');
      td(tr, p.k, 'm hn');
      td(tr, String(p.gp), 'n');
      barCell(tr, avg(p), dom[0], dom[1], tier(avg(p)));
      td(tr, f2(avg(p)), 'n val');
      td(tr, p.sv == null ? '–' : (p.sv * 100).toFixed(1).replace('.', ','), 'n hn');
      td(tr, f2(p.gsax), 'n hn');
      tb.appendChild(tr);
    });
  }

  // ---------- matcher ----------
  function drawGames() {
    var box = $('#games');
    box.textContent = '';
    var byDay = {};
    D.matcher.forEach(function (g) { (byDay[g.d] = byDay[g.d] || []).push(g); });
    Object.keys(byDay).sort().reverse().forEach(function (day) {
      var sec = el('div', 'day');
      sec.appendChild(el('h3', null, dagRubrik(day)));
      var grid = el('div', 'games');
      byDay[day].forEach(function (g) {
        var a = el('a', 'game');
        a.href = 'kort.html?id=' + g.id + (formel === 'gs' ? '&formel=original' : '');
        var sc = el('div', 'score');
        var awayWin = g.bm > g.hm;
        var s1 = el('span', awayWin ? null : 'lose', g.bk + ' ' + g.bm);
        var s2 = el('span', null, ' – ');
        var s3 = el('span', awayWin ? 'lose' : null, g.hm + ' ' + g.hk);
        sc.appendChild(s1); sc.appendChild(s2); sc.appendChild(s3);
        a.appendChild(sc);
        a.appendChild(el('span', 'go', 'Matchkort'));
        var star = g.stj && g.stj[formel === 'plus' ? 'pl' : 'gs'];
        var extra = (g.avg !== 'Ordinarie' ? g.avg + '. ' : '') + (star ? 'Matchens stjärna: ' + star.n + ', ' + star.k + ', ' + f2(star.v) : '');
        a.appendChild(el('div', 'extra', extra));
        grid.appendChild(a);
      });
      sec.appendChild(grid);
      box.appendChild(sec);
    });
  }

  // ---------- bästa och sämsta ----------
  function drawTop() {
    var src = D.topp[formel === 'plus' ? 'pl' : 'gs'];
    [['#t-bast', src.bast], ['#t-samst', src.samst]].forEach(function (x) {
      var tb = $(x[0] + ' tbody');
      tb.textContent = '';
      var list = x[1];
      var vals = src.bast.concat(src.samst).map(function (r) { return r.v; });
      var dom = domain(vals);
      list.forEach(function (r, i) {
        var tr = el('tr', 'click');
        td(tr, String(i + 1), 'rk');
        td(tr, r.n, 'nm');
        td(tr, r.k + ' mot ' + r.mot + ', ' + datum(r.d, true), 'm hn');
        barCell(tr, r.v, dom[0], dom[1], tier(r.v));
        td(tr, f2(r.v), 'n val');
        tr.addEventListener('click', function () { location.href = 'kort.html?id=' + r.id + (formel === 'gs' ? '&formel=original' : ''); });
        tb.appendChild(tr);
      });
    });
  }

  function drawPanel() {
    if (!D) return;
    if (current === 'spelare') drawPlayers();
    else if (current === 'lag') drawTeams();
    else if (current === 'malvakter') drawGoalies();
    else if (current === 'matcher') drawGames();
    else if (current === 'topp') drawTop();
  }
  function drawAll() { drawHead(); drawPanel(); }

  fetch('data/sasong.json', { cache: 'no-store' })
    .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function (data) {
      D = data;
      if (!D.plus) {
        formel = 'gs';
        var b = document.querySelector('[data-formel="plus"]');
        b.disabled = true;
        b.title = 'Game Score+ visas när säsongen har tillräckligt många skott för xG-modellen.';
        b.setAttribute('aria-pressed', 'false');
        document.querySelector('[data-formel="gs"]').setAttribute('aria-pressed', 'true');
      }
      var lagSel = $('#f-lag');
      D.lag.map(function (t) { return t.lag; }).sort(function (a, b) { return a.localeCompare(b, 'sv'); })
        .forEach(function (l) { var o = el('option', null, l); o.value = l; lagSel.appendChild(o); });
      var h = location.hash.slice(1);
      if (h && document.getElementById(h) && document.getElementById(h).classList.contains('panel')) show(h);
      drawAll();
    })
    .catch(function (e) {
      $('#take').textContent = 'Statistiken kunde inte laddas (' + e.message + '). Försök igen om en stund.';
    });
})();
