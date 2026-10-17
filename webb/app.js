/* Slotline – webbsidan. Läser data/sasong.json som byggs av bygg_sida.py. */
(function () {
  'use strict';
  var MAN = ['januari', 'februari', 'mars', 'april', 'maj', 'juni', 'juli', 'augusti', 'september', 'oktober', 'november', 'december'];
  var MAN_K = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];
  var DAG = ['söndag', 'måndag', 'tisdag', 'onsdag', 'torsdag', 'fredag', 'lördag'];
  var MIN = 3;
  var PAGES = ['oversikt', 'vinstchans', 'matcher', 'spelare', 'lag', 'malvakter', 'tur', 'om'];
  var GS_PAGES = { oversikt: 1, matcher: 1, spelare: 1, lag: 1, malvakter: 1 };

  var FARG = window.LAGFARG || {};

  var D = null;
  var formel = 'plus';
  var page = 'oversikt';
  var state = { lag: '', pos: '', min: MIN, rookie: false, q: '', sort: 'avg' };
  var mvState = { min: 1, rookie: false };
  var turState = { min: MIN, rookie: false, pos: '', vy: 'otur' };

  // ---------- små hjälpare ----------
  function $(s) { return document.querySelector(s); }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function f2(v) { return v == null || isNaN(v) ? '–' : (v < 0 ? '−' : '') + Math.abs(v).toFixed(2); }
  function f1(v) { return v == null || isNaN(v) ? '–' : (v < 0 ? '−' : '') + Math.abs(v).toFixed(1); }
  function pct(v) { return Math.round(v * 100) + ' %'; }
  function tier(v) { return v < 0 ? 'var(--svag)' : v < 1 ? 'var(--godk)' : v < 2 ? 'var(--bra)' : 'var(--lys)'; }
  function datum(s, kort) { var d = new Date(s + 'T12:00:00'); return d.getDate() + ' ' + (kort ? MAN_K : MAN)[d.getMonth()]; }
  function dagRubrik(s) { var d = new Date(s + 'T12:00:00'); var t = DAG[d.getDay()]; return t.charAt(0).toUpperCase() + t.slice(1) + ' ' + d.getDate() + ' ' + MAN[d.getMonth()]; }
  var TID = (function () {
    try { return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Stockholm', weekday: 'short', hour: '2-digit', minute: '2-digit' }); } catch (e) { return null; }
  })();
  function starttid(iso) {
    if (!iso || !TID) return '';
    var d = new Date(iso);
    return isNaN(d) ? '' : TID.format(d).replace(':', '.');
  }
  function varumarke(node, namn) {
    node.textContent = '';
    // Sista delen av namnet får accentfärg: Slot + line.
    var m = /^(.+?)(line|IQ)$/i.exec(namn || '');
    if (m) {
      node.appendChild(document.createTextNode(m[1]));
      node.appendChild(el('span', 'accent', m[2]));
    } else node.textContent = namn;
  }
  function avg(p) { return formel === 'plus' ? p.pl : p.gs; }
  function sum(p) { return formel === 'plus' ? p.plS : p.gsS; }
  function td(tr, content, cls) {
    var c = el('td', cls);
    if (content instanceof Node) c.appendChild(content); else c.textContent = content;
    tr.appendChild(c);
    return c;
  }
  function prick(abbr, size) {
    var s = el('span', 'lagprick');
    s.style.width = size + 'px'; s.style.height = size + 'px';
    s.style.setProperty('--c', (FARG[abbr] || ['#9AA8B6'])[0]);
    s.setAttribute('aria-hidden', 'true');
    s.appendChild(el('i'));
    return s;
  }
  function logo(abbr, size) {
    var info = D && D.lagInfo && D.lagInfo[abbr];
    if (!info || !info.logo) return prick(abbr, size);
    var img = el('img', 'logo');
    img.alt = '';
    img.width = size; img.height = size;
    img.decoding = 'async';
    img.addEventListener('error', function () { if (img.parentNode) img.parentNode.replaceChild(prick(abbr, size), img); });
    img.src = info.logo;
    return img;
  }
  function team(abbr, size, text) {
    var s = el('span', 'tt');
    s.appendChild(logo(abbr, size || 22));
    s.appendChild(el('span', null, text || abbr));
    return s;
  }
  function lagNamn(abbr, size, full) {
    var s = el('span', 'tt');
    s.appendChild(logo(abbr, size));
    s.appendChild(el('span', 'full', full));
    s.appendChild(el('span', 'kort', abbr));
    return s;
  }
  function barCell(tr, v, lo, hi, color, extra) {
    var c = el('td', 'barc' + (extra ? ' ' + extra : ''));
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
  function spelarLank(p) {
    var a = el('a', 'sp-lank', p.n);
    a.href = 'spelare.html?id=' + p.id;
    if (p.rook) { var r = el('span', 'rookie', 'R'); r.title = 'Rookie'; a.appendChild(r); }
    return a;
  }
  function domain(vals) {
    var lo = 0, hi = 0.5;
    vals.forEach(function (v) { if (v < lo) lo = v; if (v > hi) hi = v; });
    return [lo, hi];
  }
  function emptyRow(tb, cols, text) {
    var tr = el('tr'); var c = td(tr, text, 'empty'); c.colSpan = cols; tb.appendChild(tr);
  }

  // ---------- lagfärger: två lag ska aldrig få nästan samma färg ----------
  function lab(hex) {
    var h = hex.replace('#', '');
    var rgb = [0, 2, 4].map(function (i) {
      var c = parseInt(h.substr(i, 2), 16) / 255;
      return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    var X = (rgb[0] * 0.4124 + rgb[1] * 0.3576 + rgb[2] * 0.1805) / 0.95047;
    var Y = (rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722);
    var Z = (rgb[0] * 0.0193 + rgb[1] * 0.1192 + rgb[2] * 0.9505) / 1.08883;
    var f = function (t) { return t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116; };
    return [116 * f(Y) - 16, 500 * (f(X) - f(Y)), 200 * (f(Y) - f(Z))];
  }
  function dE(a, b) { var p = lab(a), q = lab(b); return Math.sqrt(Math.pow(p[0] - q[0], 2) + Math.pow(p[1] - q[1], 2) + Math.pow(p[2] - q[2], 2)); }
  function matchFarger(borta, hemma) {
    var b = FARG[borta] || ['#86A7D2', '#4E5D6C'];
    var h = FARG[hemma] || ['#1B4A8A', '#4E5D6C'];
    var cb = b[0];
    if (dE(cb, h[0]) < 28) { cb = b[1]; if (dE(cb, h[0]) < 28) cb = '#9AA8B6'; }
    return [cb, h[0]];
  }

  // ---------- navigering ----------
  function show(p) {
    if (PAGES.indexOf(p) < 0) p = 'oversikt';
    page = p;
    PAGES.forEach(function (x) { document.getElementById(x).hidden = x !== p; });
    document.querySelectorAll('.nav a, .tabbar a').forEach(function (a) {
      if (a.dataset.page === p || (a.dataset.also || '').split(' ').indexOf(p) >= 0) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    var om = $('.site-om');
    if (p === 'om') om.setAttribute('aria-current', 'page'); else om.removeAttribute('aria-current');
    var sb = $('#subbar');
    if (GS_PAGES[p]) {
      var head = document.querySelector('#' + p + ' .page-head');
      head.parentNode.insertBefore(sb, head.nextSibling);
      sb.hidden = false;
    } else {
      sb.hidden = true;
    }
    var act = document.querySelector('.nav a[aria-current]');
    if (act) { var nav = $('.nav-in'); nav.scrollLeft = Math.max(0, act.offsetLeft - nav.clientWidth / 2 + act.offsetWidth / 2); }
    draw();
    window.scrollTo(0, 0);
  }
  window.addEventListener('hashchange', function () { show(location.hash.slice(1)); });

  // ---------- formel ----------
  document.querySelectorAll('[data-formel]').forEach(function (b) {
    b.addEventListener('click', function () {
      if (b.disabled) return;
      formel = b.dataset.formel;
      document.querySelectorAll('[data-formel]').forEach(function (x) { x.setAttribute('aria-pressed', String(x.dataset.formel === formel)); });
      draw();
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
  $('#f-min').addEventListener('input', function (e) { state.min = +e.target.value; drawPlayers(); });
  $('#f-rookie').addEventListener('change', function (e) { state.rookie = e.target.checked; drawPlayers(); });
  $('#t-min').addEventListener('input', function (e) { turState.min = +e.target.value; drawTur(); });
  $('#t-rookie').addEventListener('change', function (e) { turState.rookie = e.target.checked; drawTur(); });
  [['#t-vy', 'vy'], ['#t-pos', 'pos']].forEach(function (x) {
    document.querySelectorAll(x[0] + ' button').forEach(function (b) {
      b.addEventListener('click', function () {
        turState[x[1]] = b.dataset[x[1]];
        document.querySelectorAll(x[0] + ' button').forEach(function (y) { y.setAttribute('aria-pressed', String(y === b)); });
        drawTur();
      });
    });
  });
  $('#g-min').addEventListener('input', function (e) { mvState.min = +e.target.value; drawGoalies(); });
  $('#g-rookie').addEventListener('change', function (e) { mvState.rookie = e.target.checked; drawGoalies(); });
  $('#f-q').addEventListener('input', function (e) { state.q = e.target.value.trim().toLowerCase(); drawPlayers(); });
  document.querySelectorAll('#t-spelare th button').forEach(function (b) {
    b.addEventListener('click', function () { state.sort = b.dataset.sort; drawPlayers(); });
  });
  function visaLag(lag) {
    state.lag = lag;
    $('#f-lag').value = lag;
    if (location.hash === '#spelare') show('spelare'); else location.hash = 'spelare';
  }

  // ---------- byggstenar ----------
  function matchupKort(g, medDetaljer) {
    var a = el('article', 'mu');
    var top = el('div', 'mu-top');
    top.appendChild(el('span', null, starttid(g.start)));
    var trotta = [g.b, g.h].filter(function (t) { return t.trott; }).map(function (t) { return t.k + ' spelade igår'; });
    if (trotta.length) top.appendChild(el('span', 'mu-flag', trotta.join(', ')));
    a.appendChild(top);

    var teams = el('div', 'mu-teams');
    [['b', g.b, g.h], ['h', g.h, g.b]].forEach(function (x) {
      var t = x[1], o = x[2];
      var box = el('div', 'mu-team ' + x[0]);
      var id = el('div', 'mu-id');
      id.appendChild(logo(t.k, 40));
      id.appendChild(el('span', 'mu-ab', t.k));
      box.appendChild(id);
      box.appendChild(el('div', 'mu-fn', t.n));
      box.appendChild(el('div', 'mu-pct' + (t.p >= o.p ? ' fav' : ''), pct(t.p)));
      teams.appendChild(box);
    });
    a.appendChild(teams);

    var farg = matchFarger(g.b.k, g.h.k);
    var bar = el('div', 'pbar');
    bar.setAttribute('role', 'img');
    bar.setAttribute('aria-label', g.b.k + ' ' + pct(g.b.p) + ', ' + g.h.k + ' ' + pct(g.h.p));
    var i1 = el('i'); i1.style.flex = g.b.p + ' 1 0'; i1.style.background = farg[0];
    var i2 = el('i'); i2.style.flex = g.h.p + ' 1 0'; i2.style.background = farg[1];
    bar.appendChild(i1); bar.appendChild(i2);
    a.appendChild(bar);

    var foot = el('div', 'mu-foot');
    foot.appendChild(el('span', null, 'Väntade mål ' + f1(g.b.xg) + '–' + f1(g.h.xg)));
    foot.appendChild(el('span', null, 'Hemma: ' + g.h.k));
    a.appendChild(foot);

    // troliga målvakter och chansen om reserven står
    if ((g.b.mv && g.b.mv.length) || (g.h.mv && g.h.mv.length)) {
      var mvBox = el('div', 'mu-mv');
      var rubrik = el('div', 'mu-mv-h', 'Troliga målvakter');
      mvBox.appendChild(rubrik);
      var namnrad = el('div', 'mu-mv-namn');
      [g.b, g.h].forEach(function (t, i) {
        var c = el('div', i ? 'h' : 'b');
        var m = (t.mv || [])[0];
        if (m) {
          var ln = el('a', 'sp-lank', m.n); ln.href = 'spelare.html?id=' + m.id; c.appendChild(ln);
          c.appendChild(el('div', 'mu-mv-sub', (m.sv != null ? (m.sv * 100).toFixed(1).replace('.', ',') + ' %' : '–') + ' · GSAx ' + f2(m.gsax)));
        } else c.textContent = '–';
        namnrad.appendChild(c);
      });
      mvBox.appendChild(namnrad);
      var alt = [];
      [['b', g.b], ['h', g.h]].forEach(function (x) {
        var t = x[1], m2 = (t.mv || [])[1];
        if (!m2 || t.alt == null) return;
        var ph = t.alt, pb = 1 - t.alt;
        var egen = x[0] === 'h' ? ph : pb, nu = t.p;
        var rad = el('div', 'mu-alt');
        var txt = el('span', 'mu-alt-t');
        txt.appendChild(document.createTextNode('Om '));
        var ln = el('a', 'sp-lank', m2.n); ln.href = 'spelare.html?id=' + m2.id; txt.appendChild(ln);
        txt.appendChild(document.createTextNode(' står för ' + t.k));
        rad.appendChild(txt);
        var d = Math.round(egen * 100) - Math.round(nu * 100);
        var v = el('span', 'mu-alt-v', t.k + ' ' + pct(egen));
        v.appendChild(el('small', d < 0 ? 'ned' : d > 0 ? 'upp' : '', d === 0 ? ' ±0' : (d > 0 ? ' +' : ' −') + Math.abs(d)));
        rad.appendChild(v);
        alt.push(rad);
      });
      alt.forEach(function (r) { mvBox.appendChild(r); });
      a.appendChild(mvBox);
    }

    if (medDetaljer) {
      var det = el('details');
      det.appendChild(el('summary', null, 'Jämför lagen'));
      var tab = el('div', 'cmp');
      var rad = function (vb, label, vh, bb, hb, extra) {
        var r = el('div', 'cmp-row' + (extra ? ' ' + extra : ''));
        var c1 = el('div', 'v' + (bb ? ' best' : '')); if (vb instanceof Node) c1.appendChild(vb); else c1.textContent = vb;
        var c3 = el('div', 'v h' + (hb ? ' best' : '')); if (vh instanceof Node) c3.appendChild(vh); else c3.textContent = vh;
        r.appendChild(c1); r.appendChild(el('div', 'l', label)); r.appendChild(c3);
        tab.appendChild(r);
      };
      var rader = [
        ['Matcher', 'gp', 0, null],
        ['Gjorda mål per match', 'mal', 2, 'hi'],
        ['Insläppta per match', 'insl', 2, 'lo'],
        ['Chanser för (xG)', 'xgf', 2, 'hi'],
        ['Chanser emot (xG)', 'xga', 2, 'lo'],
        ['Målvaktsspel (GSAx)', 'gsax', 2, 'hi']
      ];
      rader.forEach(function (r) {
        var vb = g.b[r[1]], vh = g.h[r[1]];
        if (vb == null && vh == null) return;
        var bb = !!r[3] && vb != null && vh != null && vb !== vh && ((r[3] === 'hi') === (vb > vh));
        var hb = !!r[3] && vb != null && vh != null && vb !== vh && !bb;
        var fmt = function (v) { return v == null ? '–' : r[2] ? (v < 0 ? '−' : '') + Math.abs(v).toFixed(r[2]) : String(v); };
        rad(fmt(vb), r[0], fmt(vh), bb, hb);
      });
      rad(form(g.b.form), 'Form, senaste 5 matcherna', form(g.h.form), false, false, 'form-row');
      det.appendChild(tab);
      a.appendChild(det);
    }
    return a;
  }
  function form(s) {
    var box = el('span', 'form');
    (s || '').split(' ').filter(Boolean).forEach(function (r) {
      var t = el('span', r, r === 'FÖ' ? 'Ö' : r);
      t.title = r === 'V' ? 'Vinst' : r === 'F' ? 'Förlust' : 'Förlust efter förlängning eller straffar';
      box.appendChild(t);
    });
    if (!s) box.textContent = '–';
    return box;
  }
  function matchKort(g) {
    var a = el('a', 'game');
    a.href = 'kort.html?id=' + g.id + (formel === 'gs' ? '&formel=original' : '');
    var row = el('div', 'row');
    var bortaVann = g.bm > g.hm;
    var tb = el('span', 'tm' + (bortaVann ? '' : ' lose')); tb.appendChild(logo(g.bk, 30)); tb.appendChild(el('span', null, g.bk));
    var th = el('span', 'tm' + (bortaVann ? ' lose' : '')); th.appendChild(el('span', null, g.hk)); th.appendChild(logo(g.hk, 30));
    var sc = el('span', 'sc');
    sc.appendChild(el('span', bortaVann ? null : 'lose', String(g.bm)));
    sc.appendChild(document.createTextNode('–'));
    sc.appendChild(el('span', bortaVann ? 'lose' : null, String(g.hm)));
    row.appendChild(tb); row.appendChild(sc); row.appendChild(th);
    sc.style.margin = '0 auto';
    a.appendChild(row);
    var star = g.stj && g.stj[formel === 'plus' ? 'pl' : 'gs'];
    var bits = [];
    if (g.avg !== 'Ordinarie') bits.push(g.avg === 'Straffar' ? 'Avgjord på straffar' : 'Avgjord i förlängning');
    if (star) bits.push('Matchens stjärna: ' + star.n + ', ' + star.k + ', ' + f2(star.v));
    if (bits.length) a.appendChild(el('div', 'extra', bits.join('. ')));
    if (g.pre) {
      var fav = g.pre.h >= g.pre.b ? [g.hk, g.pre.h] : [g.bk, g.pre.b];
      var vann = (g.pre.h >= g.pre.b) === (g.hm > g.bm);
      a.appendChild(el('div', 'extra', 'Före matchen: ' + fav[0] + ' favorit med ' + pct(fav[1]) + (vann ? ', och vann.' : ', men förlorade.')));
    }
    a.appendChild(el('div', 'go', 'Visa matchkortet'));
    return a;
  }
  function stjarnor(box) {
    box.textContent = '';
    var skaters = D.spelare.filter(function (p) { return p.gp >= MIN && avg(p) != null; }).sort(function (a, b) { return avg(b) - avg(a); });
    var goalie = D.mv.filter(function (p) { return p.gp >= MIN && avg(p) != null; }).sort(function (a, b) { return avg(b) - avg(a); })[0];
    function tile(rank, p, label) {
      var t = el('div', 'star');
      var r = el('div', rank === 'MV' ? 'rank mv' : 'rank', rank);
      r.style.color = tier(avg(p));
      var info = el('div'); info.style.minWidth = '0';
      if (label) info.appendChild(el('div', 'lbl', label));
      info.appendChild(el('div', 'nm', p.n));
      var sub = el('div', 'sub');
      sub.appendChild(team(p.k, 18));
      sub.appendChild(el('span', null, 'snitt ' + f2(avg(p)) + ', ' + p.gp + ' matcher'));
      info.appendChild(sub);
      t.appendChild(r); t.appendChild(info);
      return t;
    }
    skaters.slice(0, 3).forEach(function (p, i) { box.appendChild(tile(String(i + 1), p, '')); });
    if (goalie) box.appendChild(tile('MV', goalie, 'Bästa målvakt'));
    return skaters[0];
  }
  function tabellOrdning() {
    return D.lag.slice().sort(function (a, b) {
      return (b.pts - a.pts) || ((b.pts / b.gp) - (a.pts / a.gp)) || ((b.gf - b.ga) - (a.gf - a.ga));
    });
  }
  function grupperaPerDag(list, key) {
    var by = {};
    list.forEach(function (g) { (by[g[key]] = by[g[key]] || []).push(g); });
    return by;
  }

  // ---------- Översikt ----------
  function drawOversikt() {
    $('#o-title').textContent = 'NHL ' + D.sasong;
    $('#o-period').textContent = datum(D.forsta) + ' – ' + datum(D.sista) + ', ' + D.matcher.length + ' matcher spelade';
    var best = stjarnor($('#o-stars'));
    var w = D.vinnare[formel === 'plus' ? 'pl' : 'gs'];
    $('#o-take').textContent = best
      ? best.n + ' (' + best.lag + ') har högst snitt i ligan, ' + f2(avg(best)) + ' per match. Laget med högst sammanlagd Game Score har vunnit ' + w[0] + ' av ' + w[1] + ' matcher.'
      : '';

    var box = $('#o-matchups');
    box.textContent = '';
    if (D.kommande.length) {
      var forsta = D.kommande[0].d;
      var dag = D.kommande.filter(function (g) { return g.d === forsta; });
      $('#o-next-day').textContent = dagRubrik(forsta) + ', ' + dag.length + (dag.length === 1 ? ' match' : ' matcher') + '. Procenten är chansen att vinna.';
      dag.slice(0, 6).forEach(function (g) { box.appendChild(matchupKort(g, false)); });
    } else {
      $('#o-next-day').textContent = '';
      box.appendChild(el('div', 'empty', 'Inga matcher inplanerade de närmaste dagarna.'));
    }

    var senast = D.matcher.length ? D.matcher[D.matcher.length - 1].d : null;
    var games = $('#o-games');
    games.textContent = '';
    if (senast) {
      var lista = D.matcher.filter(function (g) { return g.d === senast; });
      $('#o-last-day').textContent = dagRubrik(senast) + '.';
      lista.forEach(function (g) { games.appendChild(matchKort(g)); });
    }

    var tb = $('#t-topp tbody');
    tb.textContent = '';
    tabellOrdning().slice(0, 5).forEach(function (t, i) {
      var tr = el('tr', 'click'); tr.tabIndex = 0;
      td(tr, String(i + 1), 'rk');
      td(tr, team(t.k, 26, t.lag), 'nm');
      td(tr, t.w + '–' + t.l + '–' + t.otl, 'n m hn');
      td(tr, t.pts + ' p', 'n val');
      tr.addEventListener('click', function () { visaLag(t.lag); });
      tr.addEventListener('keydown', function (e) { if (e.key === 'Enter') visaLag(t.lag); });
      tb.appendChild(tr);
    });
  }

  // ---------- Vinstchans ----------
  function drawVinstchans() {
    var box = $('#v-days');
    box.textContent = '';
    if (!D.kommande.length) {
      box.appendChild(el('div', 'empty', 'Inga matcher inplanerade de närmaste dagarna.'));
    } else {
      var by = grupperaPerDag(D.kommande, 'd');
      Object.keys(by).sort().forEach(function (d) {
        box.appendChild(el('h2', 'day-h', dagRubrik(d)));
        var grid = el('div', 'matchups');
        by[d].forEach(function (g) { grid.appendChild(matchupKort(g, true)); });
        box.appendChild(grid);
      });
    }
    var t = D.traff || { n: 0, k: 0, grupper: [] };
    var facts = $('#v-facts');
    facts.textContent = '';
    function fact(v, l) { var f = el('div', 'fact'); f.appendChild(el('div', 'v', v)); f.appendChild(el('div', 'l', l)); facts.appendChild(f); }
    if (t.n) {
      fact(pct(t.k / t.n), 'av matcherna vann favoriten');
      fact(String(t.n), 'matcher har tippats');
    } else {
      fact('–', 'Träffsäkerheten visas när lagen spelat några matcher.');
    }
    var tb = $('#t-kalib tbody');
    tb.textContent = '';
    t.grupper.forEach(function (g) {
      var tr = el('tr');
      td(tr, g.namn);
      td(tr, String(g.n), 'n');
      td(tr, g.n ? pct(g.k / g.n) + ' (' + g.k + ')' : '–', 'n val');
      td(tr, g.snitt != null ? pct(g.snitt) : '–', 'n m hn');
      tb.appendChild(tr);
    });
  }

  // ---------- Matcher ----------
  function drawMatcher() {
    var box = $('#m-days');
    box.textContent = '';
    var by = grupperaPerDag(D.matcher, 'd');
    Object.keys(by).sort().reverse().forEach(function (d) {
      box.appendChild(el('h2', 'day-h', dagRubrik(d)));
      var grid = el('div', 'games');
      by[d].forEach(function (g) { grid.appendChild(matchKort(g)); });
      box.appendChild(grid);
    });
  }

  // ---------- Spelare ----------
  // Reglaget för matcher går från 1 till flest spelade matcher.
  function matcherReglage(lista, st, id) {
    var max = lista.reduce(function (m, p) { return Math.max(m, p.gp || 0); }, 1);
    var r = $('#' + id + '-min');
    if (+r.max !== max) r.max = String(max);
    if (st.min > max) st.min = max;
    r.value = String(st.min);
    r.style.setProperty('--fyll', (max > 1 ? (st.min - 1) / (max - 1) * 100 : 100) + '%');
    $('#' + id + '-min-txt').textContent = st.min <= 1 ? 'Alla matcher' :
      st.min >= max ? 'Alla ' + max + ' matcher' : 'Minst ' + st.min + ' matcher';
  }
  function drawPlayers() {
    matcherReglage(D.spelare, state, 'f');
    var list = D.spelare.filter(function (p) {
      return (!state.lag || p.lag === state.lag) && (!state.pos || p.pos === state.pos) &&
        p.gp >= state.min && (!state.rookie || p.rook) && avg(p) != null &&
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
      var namn = spelarLank(p);
      td(tr, namn, 'nm');
      td(tr, team(p.k, 22), 'm hn');
      td(tr, p.pos, 'm hn');
      td(tr, String(p.gp), 'n hn');
      barCell(tr, avg(p), dom[0], dom[1], tier(avg(p)));
      td(tr, f2(avg(p)), 'n val');
      td(tr, f2(sum(p)), 'n hn');
      td(tr, String(p.p), 'n hn');
      tb.appendChild(tr);
    });
    if (!list.length) emptyRow(tb, 9, 'Inga spelare matchar filtret.');
    $('#c-spelare').textContent = list.length ? list.length + (state.rookie ? (list.length === 1 ? ' rookie' : ' rookies') : ' spelare') : '';

    var src = D.topp[formel === 'plus' ? 'pl' : 'gs'];
    var vals = src.bast.concat(src.samst).map(function (r) { return r.v; });
    var dom2 = domain(vals);
    [['#t-bast', src.bast], ['#t-samst', src.samst]].forEach(function (x) {
      var body = $(x[0] + ' tbody');
      body.textContent = '';
      x[1].slice(0, 10).forEach(function (r, i) {
        var tr = el('tr', 'click');
        td(tr, String(i + 1), 'rk');
        td(tr, r.n, 'nm');
        td(tr, team(r.k, 20, r.k + ' mot ' + r.mot + ', ' + datum(r.d, true)), 'm hn');
        barCell(tr, r.v, dom2[0], dom2[1], tier(r.v));
        td(tr, f2(r.v), 'n val');
        tr.addEventListener('click', function () { location.href = 'kort.html?id=' + r.id + (formel === 'gs' ? '&formel=original' : ''); });
        body.appendChild(tr);
      });
    });
  }

  // ---------- Tabell ----------
  function drawTeams() {
    var best = {};
    D.spelare.forEach(function (p) {
      if (p.gp < MIN || avg(p) == null) return;
      if (!best[p.lag] || avg(p) > avg(best[p.lag])) best[p.lag] = p;
    });
    var list = tabellOrdning();
    var dom = domain(list.map(avg));
    var tb = $('#t-lag tbody');
    tb.textContent = '';
    list.forEach(function (t, i) {
      var tr = el('tr', 'click');
      tr.tabIndex = 0;
      td(tr, String(i + 1), 'rk');
      td(tr, lagNamn(t.k, 26, t.lag), 'nm');
      td(tr, String(t.gp), 'n hn');
      td(tr, String(t.w), 'n');
      td(tr, String(t.l), 'n hn');
      td(tr, String(t.otl), 'n hn');
      td(tr, String(t.pts), 'n val');
      td(tr, t.gf + '–' + t.ga, 'n hn');
      barCell(tr, avg(t), dom[0], dom[1], avg(t) >= 0 ? 'var(--bra)' : 'var(--svag)', 'hn');
      td(tr, f2(avg(t)), 'n val');
      td(tr, best[t.lag] ? best[t.lag].n : '', 'm hn');
      tr.addEventListener('click', function () { visaLag(t.lag); });
      tr.addEventListener('keydown', function (e) { if (e.key === 'Enter') visaLag(t.lag); });
      tb.appendChild(tr);
    });
  }

  // ---------- Målvakter ----------
  function drawGoalies() {
    $('#mv-lead').textContent = formel === 'plus'
      ? 'Game Score+ för målvakter bygger på räddade mål över förväntan (GSAx). Noll är en normal insats.'
      : 'Originalformeln ger plus för varje räddning och minus för varje insläppt mål.';
    matcherReglage(D.mv, mvState, 'g');
    var list = D.mv.filter(function (p) { return avg(p) != null && p.gp >= mvState.min && (!mvState.rookie || p.rook); }).sort(function (a, b) { return (avg(b) - avg(a)) || (b.gp - a.gp); });
    var dom = domain(list.map(avg));
    var tb = $('#t-mv tbody');
    tb.textContent = '';
    list.forEach(function (p, i) {
      var tr = el('tr');
      td(tr, String(i + 1), 'rk');
      var namn = spelarLank(p);
      td(tr, namn, 'nm');
      td(tr, team(p.k, 22), 'm hn');
      td(tr, String(p.gp), 'n');
      barCell(tr, avg(p), dom[0], dom[1], tier(avg(p)));
      td(tr, f2(avg(p)), 'n val');
      td(tr, p.sv == null ? '–' : (p.sv * 100).toFixed(1).replace('.', ','), 'n hn');
      td(tr, f2(p.gsax), 'n hn');
      tb.appendChild(tr);
    });
    if (!list.length) emptyRow(tb, 8, 'Inga målvakter matchar filtret.');
    $('#c-mv').textContent = list.length ? list.length + (list.length === 1 ? (mvState.rookie ? ' rookie' : ' målvakt') : (mvState.rookie ? ' rookies' : ' målvakter')) : '';
  }

  // ---------- Tur & otur ----------
  function drawTur() {
    matcherReglage(D.spelare, turState, 't');
    var harX = D.spelare.some(function (p) { return p.xp != null; });
    var list = D.spelare.filter(function (p) {
      return p.xp != null && p.gp >= turState.min && (!turState.pos || p.pos === turState.pos) && (!turState.rookie || p.rook);
    });
    list.forEach(function (p) { p._d = p.p - p.xp; });
    list.sort(function (a, b) { return turState.vy === 'otur' ? a._d - b._d : b._d - a._d; });
    var lo = Math.min.apply(null, [-1].concat(list.map(function (p) { return p._d; })));
    var hi = Math.max.apply(null, [1].concat(list.map(function (p) { return p._d; })));
    var m = Math.max(-lo, hi);
    var tb = $('#t-tur tbody'); tb.textContent = '';
    list.forEach(function (p, i) {
      var tr = el('tr');
      td(tr, String(i + 1), 'rk');
      td(tr, spelarLank(p), 'nm');
      td(tr, team(p.k, 22), 'm hn');
      td(tr, String(p.gp), 'n hn');
      td(tr, String(p.p), 'n');
      td(tr, f1(p.xp), 'n m');
      barCell(tr, p._d, -m, m, p._d < 0 ? 'var(--bra)' : 'var(--svag)', 'hn');
      td(tr, (p._d > 0 ? '+' : '') + f1(p._d), 'n val');
      td(tr, p.g + ' / ' + f1(p.xg), 'n m hn');
      td(tr, p.a + ' / ' + f1(p.xa), 'n m hn');
      tb.appendChild(tr);
    });
    if (!list.length) emptyRow(tb, 10, harX ? 'Inga spelare matchar filtret.' : 'Förväntade poäng räknas när tillräckligt många matcher spelats.');
    $('#c-tur').textContent = list.length ? list.length + ' spelare' : '';
  }

  function draw() {
    if (!D) return;
    if (page === 'oversikt') drawOversikt();
    else if (page === 'vinstchans') drawVinstchans();
    else if (page === 'matcher') drawMatcher();
    else if (page === 'spelare') drawPlayers();
    else if (page === 'tur') drawTur();
    else if (page === 'lag') drawTeams();
    else if (page === 'malvakter') drawGoalies();
  }

  fetch('data/sasong.json', { cache: 'no-store' })
    .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function (data) {
      D = data;
      D.kommande = D.kommande || [];
      D.lagInfo = D.lagInfo || {};
      if (D.sajt) {
        varumarke($('#brand-name'), D.sajt);
        document.title = D.sajt + ' – NHL-statistik';
      }
      $('#updated').textContent = 'Uppdaterad ' + D.uppdaterad;
      $('#foot-upd').textContent = 'Uppdaterad ' + D.uppdaterad + '.';
      $('#sign').textContent = D.namn ? D.namn : '';
      if (D.kontakt) {
        document.querySelectorAll('.kontakt-lank').forEach(function (k) { k.href = D.kontakt; k.hidden = false; });
      }
      if (!D.plus) {
        formel = 'gs';
        var b = document.querySelector('[data-formel="plus"]');
        b.disabled = true;
        b.title = 'Game Score+ visas när säsongen har tillräckligt många skott för xG-modellen.';
        document.querySelectorAll('[data-formel]').forEach(function (x) { x.setAttribute('aria-pressed', String(x.dataset.formel === 'gs')); });
      }
      var lagSel = $('#f-lag');
      D.lag.map(function (t) { return t.lag; }).sort(function (a, b) { return a.localeCompare(b, 'sv'); })
        .forEach(function (l) { var o = el('option', null, l); o.value = l; lagSel.appendChild(o); });
      if (D.excel) {
        var dl = $('#dl');
        dl.appendChild(document.createTextNode('All statistik finns också som '));
        var a = el('a', null, 'Excel-fil');
        a.href = D.excel;
        dl.appendChild(a);
        dl.appendChild(document.createTextNode(', med en flik per tabell.'));
      }
      show(location.hash.slice(1));
    })
    .catch(function (e) {
      $('#o-take').textContent = 'Statistiken kunde inte laddas (' + e.message + '). Försök igen om en stund.';
    });
})();
