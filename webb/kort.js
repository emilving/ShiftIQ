/* Slotline – matchkortet. Läser data/matcher/<id>.json. */
(function () {
  'use strict';
  var q = new URLSearchParams(location.search);
  var id = q.get('id');
  var exportMode = q.get('export') === '1';
  var formel = q.get('formel') === 'original' ? 'gs' : 'plus';
  var G = null;
  if (exportMode) document.body.classList.add('export');

  function $(s) { return document.querySelector(s); }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function f2(v) { return (v < 0 ? '−' : '') + Math.abs(v).toFixed(2); }
  function tier(v) { return v < 0 ? 'var(--svag)' : v < 1 ? 'var(--godk)' : v < 2 ? 'var(--bra)' : 'var(--lys)'; }
  function varumarke(node, namn) {
    node.textContent = '';
    // Sista delen av namnet får accentfärg: Slot + line.
    var m = /^(.+?)(line|IQ)$/i.exec(namn || '');
    if (m) {
      node.appendChild(document.createTextNode(m[1]));
      node.appendChild(el('span', 'accent', m[2]));
    } else node.textContent = namn;
  }
  var FARG = window.LAGFARG || {};
  function prick(abbr, size) {
    var s = el('span', 'lagprick');
    s.style.width = size + 'px'; s.style.height = size + 'px';
    s.style.setProperty('--c', (FARG[abbr] || ['#9AA8B6'])[0]);
    s.setAttribute('aria-hidden', 'true');
    s.appendChild(el('i'));
    return s;
  }
  // Byter en <img> mot lagets logga, eller mot en färgprick om loggor inte visas eller inte går att ladda.
  function setLogo(slot, src, abbr) {
    var size = parseInt(slot.getAttribute('width') || slot.style.width, 10) || 30;
    var img = el('img', 'logo'); img.alt = ''; img.width = size; img.height = size;
    if (slot.id) img.id = slot.id;
    var ersatt = function () { var p = prick(abbr, size); if (slot.id) p.id = slot.id; if (img.parentNode) img.parentNode.replaceChild(p, img); };
    slot.parentNode.replaceChild(img, slot);
    if (!src) { ersatt(); return; }
    img.onerror = ersatt;
    img.src = src;
  }
  function smallLogo(src, size, abbr) {
    if (!src) return prick(abbr, size);
    var img = el('img', 'logo'); img.alt = ''; img.width = size; img.height = size;
    img.onerror = function () { if (img.parentNode) img.parentNode.replaceChild(prick(abbr, size), img); };
    img.src = src;
    return img;
  }
  function bilderKlara() {
    var imgs = Array.prototype.slice.call(document.querySelectorAll('#kort img'));
    return Promise.all(imgs.map(function (img) {
      if (img.complete) return true;
      return new Promise(function (ok) { img.addEventListener('load', ok); img.addEventListener('error', ok); setTimeout(ok, 8000); });
    }));
  }
  var POS = { F: 'F', B: 'B', MV: 'MV' };

  // Mobil: kortet visas som en läsbar sida i stället för en förminskad bild.
  var mobilFraga = window.matchMedia ? window.matchMedia('(max-width: 700px)') : null;
  function arMobil() { return !exportMode && mobilFraga && mobilFraga.matches; }
  function scale() {
    if (exportMode) return;
    var box = $('#skala'), yta = $('#yta');
    document.body.classList.toggle('mobil', arMobil());
    if (arMobil()) { yta.style.transform = ''; box.style.height = ''; return; }
    var s = Math.min(1, box.clientWidth / 1080);
    yta.style.transform = 'scale(' + s + ')';
    box.style.height = (1350 * s) + 'px';
  }
  window.addEventListener('resize', scale);
  if (mobilFraga && mobilFraga.addEventListener) mobilFraga.addEventListener('change', scale);

  // ---------- matchrapport ----------
  function tid(min) { if (min == null) return '–'; var t = Math.round(min * 60); return Math.floor(t / 60) + ':' + ('0' + (t % 60)).slice(-2); }
  function periodNamn(n) { return n === 1 ? '1:a perioden' : n === 2 ? '2:a perioden' : n === 3 ? '3:e perioden' : n === 4 ? 'Förlängning' : (n - 3) + ':e förlängningen'; }
  function spelarLank(namn, pid, extra) {
    var a = el(pid ? 'a' : 'span', 'sp-lank', namn);
    if (pid) a.href = 'spelare.html?id=' + pid;
    if (extra != null) { var e = el('span', 'tot', ' (' + extra + ')'); a.appendChild(e); }
    return a;
  }
  function cell(tr, v, cls) { var c = el('td', cls); if (v instanceof Node) c.appendChild(v); else c.textContent = v == null ? '–' : v; tr.appendChild(c); return c; }
  function tecken(v) { return v == null ? '–' : v > 0 ? '+' + v : v < 0 ? '−' + Math.abs(v) : '0'; }
  var LAGE = { PP: 'Powerplay', SH: 'Boxplay', TB: 'Tom bur' };

  function renderRapport() {
    var R = G.rapport;
    var box = $('#rapport');
    if (!R || exportMode) { box.hidden = true; return; }
    box.hidden = false;
    var b = G.b, h = G.h, logo = {}; logo[b.k] = b.logo; logo[h.k] = h.logo;

    // Målen
    var ml = $('#r-mal'); ml.textContent = '';
    if (!R.mal.length) ml.appendChild(el('div', 'r-tom', 'Inga mål under ordinarie tid eller förlängning.'));
    var per = null;
    R.mal.forEach(function (m) {
      if (m.per !== per) { per = m.per; ml.appendChild(el('div', 'r-per', periodNamn(per))); }
      var row = el('div', 'r-mal-rad');
      row.appendChild(el('div', 'r-tid', m.tid));
      var lag = el('div', 'r-lagk'); lag.appendChild(smallLogo(logo[m.k], 26, m.k)); lag.appendChild(el('span', null, m.k)); row.appendChild(lag);
      var st = el('div', 'r-st'); st.textContent = m.st[0] + '–' + m.st[1]; row.appendChild(st);
      var txt = el('div', 'r-txt');
      var rad1 = el('div', 'r-skytt'); rad1.appendChild(spelarLank(m.n, m.id, m.tot));
      if (m.lage) rad1.appendChild(el('span', 'r-lage ' + m.lage.toLowerCase(), LAGE[m.lage] || m.lage));
      txt.appendChild(rad1);
      var as = el('div', 'r-ass');
      if (m.a.length) {
        as.appendChild(document.createTextNode('Assist: '));
        m.a.forEach(function (a, i) { if (i) as.appendChild(document.createTextNode(', ')); as.appendChild(spelarLank(a[0], a[2], a[1])); });
      } else as.textContent = 'Utan assist';
      txt.appendChild(as);
      row.appendChild(txt);
      ml.appendChild(row);
    });

    // Straffar
    var sf = $('#r-straff'); sf.textContent = '';
    if (R.straff && R.straff.length) {
      sf.appendChild(el('h3', null, 'Straffläggning'));
      var sb = el('div', 'box short r-mal');
      R.straff.forEach(function (x) {
        var row = el('div', 'r-mal-rad straff');
        var lag = el('div', 'r-lagk'); lag.appendChild(smallLogo(logo[x.k], 26, x.k)); lag.appendChild(el('span', null, x.k)); row.appendChild(lag);
        var t = el('div', 'r-txt'); t.appendChild(spelarLank(x.n, x.id)); row.appendChild(t);
        row.appendChild(el('div', x.mal ? 'r-sm ja' : 'r-sm', x.mal ? 'Mål' : 'Miss'));
        sb.appendChild(row);
      });
      sf.appendChild(sb);
    }

    // Lagen
    var lg = $('#r-lag'); lg.textContent = '';
    var B = R.lag.b || {}, H = R.lag.h || {};
    var farger = (function () {
      var fb = FARG[b.k] || ['#4677BA', '#86A7D2'], fh = FARG[h.k] || ['#1B4A8A', '#86A7D2'];
      var rgb = function (x) { var n = parseInt(x.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; };
      var a = rgb(fb[0]), c = rgb(fh[0]);
      var d = Math.sqrt(Math.pow(a[0] - c[0], 2) + Math.pow(a[1] - c[1], 2) + Math.pow(a[2] - c[2], 2));
      return [fb[0], d < 90 ? fh[1] : fh[0]];
    })();
    var huvud = el('div', 'r-cmp-h');
    [b, h].forEach(function (t, i) {
      var c = el('div', i ? 'h' : 'b'); c.appendChild(smallLogo(t.logo, 26, t.k)); c.appendChild(el('span', null, t.k)); huvud.appendChild(c);
      if (!i) huvud.appendChild(el('div'));
    });
    lg.appendChild(huvud);
    function fo(t) { var n = (t['Vunna tekningar'] || 0) + (t['Förlorade tekningar'] || 0); return n ? Math.round(100 * t['Vunna tekningar'] / n) : null; }
    var rader = [
      ['Skott på mål', B['Skott'], H['Skott']],
      ['Förväntade mål (xG)', B['xGF'], H['xGF'], 2],
      ['Skottförsök', B['Skottförsök'], H['Skottförsök']],
      ['Tekningar, %', fo(B), fo(H)],
      ['Powerplaymål', B['PP-mål'], H['PP-mål'], 0, (B['PP-mål'] || 0) + ' av ' + (H['Utvisningar'] || 0), (H['PP-mål'] || 0) + ' av ' + (B['Utvisningar'] || 0)],
      ['Tacklingar', B['Träffar'], H['Träffar']],
      ['Blockerade skott', B['Blockeringar'], H['Blockeringar']],
      ['Utvisningsminuter', B['Utvisningsminuter'], H['Utvisningsminuter']]
    ];
    rader.forEach(function (r) {
      if (r[1] == null && r[2] == null) return;
      var a = r[1] || 0, c = r[2] || 0, sum = a + c;
      var row = el('div', 'r-cmp');
      var vt = function (v, txt) { return txt || (r[3] ? (+v).toFixed(r[3]) : String(v)); };
      row.appendChild(el('div', 'v b' + (a > c ? ' mer' : ''), vt(a, r[4])));
      var mid = el('div', 'mid');
      mid.appendChild(el('div', 'l', r[0]));
      var bar = el('div', 'r-bar');
      var ib = el('i'); ib.style.width = (sum ? a / sum * 100 : 50) + '%'; ib.style.background = (FARG[b.k] || ['#4677BA'])[0];
      var ih = el('i'); ih.style.width = (sum ? c / sum * 100 : 50) + '%'; ih.style.background = (FARG[h.k] || ['#1B4A8A'])[0];
      ib.style.background = farger[0]; ih.style.background = farger[1];
      bar.appendChild(ib); bar.appendChild(ih); mid.appendChild(bar);
      row.appendChild(mid);
      row.appendChild(el('div', 'v h' + (c > a ? ' mer' : ''), vt(c, r[5])));
      lg.appendChild(row);
    });

    // Spelarna
    var vi = formel === 'plus' ? 'pl' : 'gs';
    var sp = $('#r-spelare'); sp.textContent = '';
    [['b', b], ['h', h]].forEach(function (x) {
      var t = x[1], key = x[0];
      var hd = el('h3', 'r-laghuvud'); hd.appendChild(smallLogo(t.logo, 28, t.k)); hd.appendChild(document.createTextNode(t.n)); sp.appendChild(hd);
      var wrap = el('div', 'box short r-tab');
      var tab = el('table', 'rows r-rows');
      var th = el('thead'); var tr = el('tr');
      [['Nr', 'n'], ['Spelare', ''], ['Pos', ''], ['M', 'n'], ['A', 'n'], ['P', 'n'], ['+/−', 'n'], ['Skott', 'n'], ['xG', 'n'],
       ['Tackl.', 'n'], ['Block', 'n'], ['Tekn.', 'n'], ['Utv.', 'n'], ['Istid', 'n'], [formel === 'plus' ? 'GS+' : 'GS', 'n']]
        .forEach(function (c) { var e = el('th', c[1], c[0]); tr.appendChild(e); });
      th.appendChild(tr); tab.appendChild(th);
      var tb = el('tbody');
      (R.spelare[key] || []).forEach(function (p) {
        var r = el('tr');
        cell(r, p.nr, 'n m');
        cell(r, spelarLank(p.n, p.id), 'nm');
        cell(r, p.pos, 'm');
        cell(r, p.g, 'n' + (p.g ? ' fet' : ''));
        cell(r, p.a, 'n' + (p.a ? ' fet' : ''));
        cell(r, p.p, 'n' + (p.p ? ' fet' : ''));
        cell(r, tecken(p.pm), 'n');
        cell(r, p.s, 'n');
        cell(r, p.xg == null ? '–' : p.xg.toFixed(2), 'n m');
        cell(r, p.hit, 'n');
        cell(r, p.blk, 'n');
        cell(r, (p.fo[0] || p.fo[1]) ? p.fo[0] + '–' + p.fo[1] : '–', 'n m');
        cell(r, p.pim, 'n');
        cell(r, tid(p.toi), 'n');
        var v = p[vi]; var c = cell(r, v == null ? '–' : f2(v), 'n fet'); if (v != null) c.style.color = v < 0 ? 'var(--svag)' : 'var(--ink)';
        tb.appendChild(r);
      });
      tab.appendChild(tb); wrap.appendChild(tab); sp.appendChild(wrap);
      var mv = (R.mv || {})[key] || [];
      if (mv.length) {
        var w2 = el('div', 'box short r-tab');
        var t2 = el('table', 'rows r-rows');
        var h2 = el('thead'); var r2 = el('tr');
        [['Nr', 'n'], ['Målvakt', ''], ['Skott mot', 'n'], ['Räddn.', 'n'], ['Insl.', 'n'], ['Rädd.%', 'n'], ['GSAx', 'n'], ['Istid', 'n'], ['Beslut', ''], [formel === 'plus' ? 'GS+' : 'GS', 'n']]
          .forEach(function (c) { r2.appendChild(el('th', c[1], c[0])); });
        h2.appendChild(r2); t2.appendChild(h2);
        var b2 = el('tbody');
        mv.forEach(function (g) {
          var r = el('tr');
          cell(r, g.nr, 'n m'); cell(r, spelarLank(g.n, g.id), 'nm'); cell(r, g.sa, 'n'); cell(r, g.sv, 'n'); cell(r, g.ga, 'n');
          cell(r, g.svp == null ? '–' : (g.svp * 100).toFixed(1).replace('.', ',') + ' %', 'n');
          cell(r, g.gsax == null ? '–' : f2(g.gsax), 'n'); cell(r, tid(g.toi), 'n'); cell(r, g.bes || '–', 'm');
          var v = g[vi]; var c = cell(r, v == null ? '–' : f2(v), 'n fet'); if (v != null) c.style.color = v < 0 ? 'var(--svag)' : 'var(--ink)';
          b2.appendChild(r);
        });
        t2.appendChild(b2); w2.appendChild(t2); sp.appendChild(w2);
      }
    });
  }

  function render() {
    var vi = formel === 'plus' ? 3 : 2;
    var b = G.b, h = G.h;
    var awayWon = b.m > h.m;
    document.title = 'Matchkort ' + b.k + '–' + h.k + ' – ' + (G.sajt || 'Slotline');
    $('#kort').setAttribute('aria-label', 'Matchkort ' + b.n + ' mot ' + h.n + ', ' + b.m + '–' + h.m);
    varumarke($('#k-mark'), G.sajt || 'Slotline');
    $('#k-sub').textContent = formel === 'plus' ? 'Game Score+' : 'Game Score';
    setLogo($('#k-bl'), b.logo, b.k);
    setLogo($('#k-hl'), h.logo, h.k);
    $('#k-date').textContent = G.datumText;
    $('#k-bn').textContent = b.n; $('#k-bk').textContent = b.k;
    $('#k-hn').textContent = h.n; $('#k-hk').textContent = h.k;
    var bm = $('#k-bm'), hm = $('#k-hm');
    bm.textContent = b.m; hm.textContent = h.m;
    bm.className = awayWon ? '' : 'lose'; hm.className = awayWon ? 'lose' : '';
    $('#k-avg').textContent = G.avg === 'Förlängning' ? 'Avgjord i förlängning' : G.avg === 'Straffar' ? 'Avgjord på straffar' : '';

    var all = b.spelare.map(function (p) { return { p: p, k: b.k, logo: b.logo }; }).concat(h.spelare.map(function (p) { return { p: p, k: h.k, logo: h.logo }; }))
      .filter(function (x) { return x.p[vi] != null; });
    var vals = all.map(function (x) { return x.p[vi]; });
    var lo = Math.floor(Math.min.apply(null, [-1].concat(vals)));
    var hi = Math.ceil(Math.max.apply(null, [2].concat(vals)));
    var x = function (v) { return (v - lo) / (hi - lo) * 100; };  // procent av stapelns bredd
    var zero = x(0);

    var stars = $('#k-stars');
    while (stars.children.length > 1) stars.removeChild(stars.lastChild);
    all.slice().sort(function (a, c) { return c.p[vi] - a.p[vi]; }).slice(0, 3).forEach(function (s, i) {
      var t = el('div', 'k-star');
      var r = el('div', 'r', String(i + 1)); r.style.color = tier(s.p[vi]);
      var info = el('div', 't');
      info.appendChild(el('div', 'n', s.p[1]));
      var sline = el('div', 's');
      sline.appendChild(smallLogo(s.logo, 22, s.k));
      sline.appendChild(document.createTextNode(s.k + ', ' + f2(s.p[vi])));
      info.appendChild(sline);
      t.appendChild(r); t.appendChild(info);
      stars.appendChild(t);
    });

    var cols = $('#k-cols');
    cols.textContent = '';
    [[b, awayWon, 'Borta'], [h, !awayWon, 'Hemma']].forEach(function (x3) {
      var t = x3[0], won = x3[1];
      var ps = t.spelare.filter(function (p) { return p[vi] != null; }).sort(function (a, c) { return c[vi] - a[vi]; });
      var total = ps.reduce(function (s, p) { return s + p[vi]; }, 0);
      var col = el('div', 'k-col');
      var head = el('div', 'k-head');
      var hn = el('div', 'n');
      hn.appendChild(smallLogo(t.logo, 30, t.k));
      hn.appendChild(document.createTextNode(t.n));
      head.appendChild(hn);
      var lost = G.avg !== 'Ordinarie' && !won ? 'Förlust efter ' + (G.avg === 'Straffar' ? 'straffar' : 'förl.') : 'Förlust';
      head.appendChild(el('div', won ? 'pill win' : 'pill', won ? 'Vinst' : lost));
      col.appendChild(head);
      col.appendChild(el('div', 'k-sum', x3[2] + ', lagets summa ' + f2(total)));
      var list = el('div', 'k-list');
      ps.forEach(function (p) {
        var v = p[vi];
        var row = el('div', 'k-row');
        row.appendChild(el('div', 'p', POS[p[0]] || p[0]));
        row.appendChild(el('div', 'n', p[1]));
        var bb = el('div', 'b');
        var i = el('i');
        var bx = x(v);
        i.style.left = Math.min(zero, bx) + '%';
        i.style.width = 'max(2px, ' + Math.abs(bx - zero) + '%)';
        i.style.background = tier(v);
        i.style.borderRadius = v >= 0 ? '0 4px 4px 0' : '4px 0 0 4px';
        var nolla = el('span', 'z'); nolla.style.left = zero + '%';
        bb.appendChild(nolla);
        bb.appendChild(i);
        row.appendChild(bb);
        row.appendChild(el('div', 'v', f2(v)));
        list.appendChild(row);
      });
      col.appendChild(list);
      cols.appendChild(col);
    });

    $('#k-explain').textContent = formel === 'plus'
      ? 'Game Score+ samlar en spelares match i ett tal: poäng, chansernas kvalitet (xG), tekningar, utvisningar och hur det gick när spelaren var på isen. Noll är en vanlig insats.'
      : 'Game Score samlar en spelares match i ett tal: poäng, skott, tekningar, utvisningar och hur det gick när spelaren var på isen. Noll är en vanlig insats.';
    $('#k-src').textContent = (formel === 'plus' ? 'Data: NHL. Formel: Game Score+.' : 'Data: NHL. Formel: Dom Luszczyszyn.') +
      ' Oberoende fansida utan koppling till NHL eller lagen.';
    $('#k-sign').textContent = G.namn || '';

    var dl = $('#ladda');
    var hasPng = G.png && formel === (G.plus ? 'plus' : 'gs');
    dl.hidden = !hasPng;
    if (hasPng) { dl.href = 'bilder/' + G.id + '.png'; dl.setAttribute('download', 'matchkort-' + G.d + '-' + b.k + '-' + h.k + '.png'); }
    document.querySelectorAll('[data-formel]').forEach(function (btn) { btn.setAttribute('aria-pressed', String(btn.dataset.formel === formel)); });
    scale();
    renderRapport();
  }

  document.querySelectorAll('[data-formel]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (btn.disabled) return;
      formel = btn.dataset.formel;
      var u = new URL(location.href);
      if (formel === 'gs') u.searchParams.set('formel', 'original'); else u.searchParams.delete('formel');
      if (history.replaceState) history.replaceState(null, '', u);
      render();
    });
  });

  if (!id) { $('#k-date').textContent = 'Ingen match vald.'; return; }
  fetch('data/matcher/' + encodeURIComponent(id) + '.json', { cache: 'no-store' })
    .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function (data) {
      G = data;
      if (!G.plus) {
        formel = 'gs';
        var pb = document.querySelector('[data-formel="plus"]');
        pb.disabled = true;
      }
      render();
      return Promise.all([document.fonts ? document.fonts.ready : null, bilderKlara()]);
    })
    .then(function () { window.__kortKlart = true; })
    .catch(function (e) {
      $('#k-date').textContent = 'Matchen kunde inte laddas (' + e.message + ').';
      window.__kortKlart = true;
    });
})();
