/* NHL Game Score – matchkortet. Läser data/matcher/<id>.json. */
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
  var POS = { F: 'F', B: 'B', MV: 'MV' };

  function scale() {
    if (exportMode) return;
    var box = $('#skala');
    var s = Math.min(1, box.clientWidth / 1080);
    $('#yta').style.transform = 'scale(' + s + ')';
    box.style.height = (1350 * s) + 'px';
  }
  window.addEventListener('resize', scale);

  function render() {
    var vi = formel === 'plus' ? 3 : 2;
    var b = G.b, h = G.h;
    var awayWon = b.m > h.m;
    document.title = 'Matchkort ' + b.k + ' – ' + h.k;
    $('#kort').setAttribute('aria-label', 'Matchkort ' + b.n + ' mot ' + h.n + ', ' + b.m + '–' + h.m);
    $('#k-mark').textContent = formel === 'plus' ? 'Game Score+' : 'Game Score';
    $('#k-date').textContent = G.datumText;
    $('#k-bn').textContent = b.n; $('#k-bk').textContent = b.k;
    $('#k-hn').textContent = h.n; $('#k-hk').textContent = h.k;
    var bm = $('#k-bm'), hm = $('#k-hm');
    bm.textContent = b.m; hm.textContent = h.m;
    bm.className = awayWon ? '' : 'lose'; hm.className = awayWon ? 'lose' : '';
    $('#k-avg').textContent = G.avg === 'Förlängning' ? 'Avgjord i förlängning' : G.avg === 'Straffar' ? 'Avgjord på straffar' : '';

    var all = b.spelare.map(function (p) { return { p: p, k: b.k }; }).concat(h.spelare.map(function (p) { return { p: p, k: h.k }; }))
      .filter(function (x) { return x.p[vi] != null; });
    var vals = all.map(function (x) { return x.p[vi]; });
    var lo = Math.floor(Math.min.apply(null, [-1].concat(vals)));
    var hi = Math.ceil(Math.max.apply(null, [2].concat(vals)));
    var BW = 190;
    var x = function (v) { return (v - lo) / (hi - lo) * BW; };
    var zero = x(0);

    var stars = $('#k-stars');
    while (stars.children.length > 1) stars.removeChild(stars.lastChild);
    all.slice().sort(function (a, c) { return c.p[vi] - a.p[vi]; }).slice(0, 3).forEach(function (s, i) {
      var t = el('div', 'k-star');
      var r = el('div', 'r', String(i + 1)); r.style.color = tier(s.p[vi]);
      var info = el('div', 't');
      info.appendChild(el('div', 'n', s.p[1]));
      info.appendChild(el('div', 's', s.k + ', ' + f2(s.p[vi])));
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
      head.appendChild(el('div', 'n', t.n));
      var lost = G.avg !== 'Ordinarie' && !won ? 'Förlust efter ' + (G.avg === 'Straffar' ? 'straffar' : 'förl.') : 'Förlust';
      head.appendChild(el('div', won ? 'pill win' : 'pill', won ? 'Vinst' : lost));
      col.appendChild(head);
      col.appendChild(el('div', 'k-sum', x3[2] + ', lagets summa ' + f2(total)));
      var list = el('div', 'k-list');
      var z = el('div', 'k-zero'); z.style.left = (34 + 8 + 160 + 8 + zero) + 'px';
      list.appendChild(z);
      ps.forEach(function (p) {
        var v = p[vi];
        var row = el('div', 'k-row');
        row.appendChild(el('div', 'p', POS[p[0]] || p[0]));
        row.appendChild(el('div', 'n', p[1]));
        var bb = el('div', 'b');
        var i = el('i');
        var bx = x(v);
        i.style.left = Math.min(zero, bx) + 'px';
        i.style.width = Math.max(2, Math.abs(bx - zero)) + 'px';
        i.style.background = tier(v);
        i.style.borderRadius = v >= 0 ? '0 4px 4px 0' : '4px 0 0 4px';
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
    $('#k-src').textContent = formel === 'plus' ? 'Data: NHL. Formel: Game Score+.' : 'Data: NHL. Formel: Dom Luszczyszyn.';
    $('#k-sign').textContent = G.namn || '';

    var dl = $('#ladda');
    var hasPng = G.png && formel === (G.plus ? 'plus' : 'gs');
    dl.hidden = !hasPng;
    if (hasPng) { dl.href = 'bilder/' + G.id + '.png'; dl.setAttribute('download', 'matchkort-' + G.d + '-' + b.k + '-' + h.k + '.png'); }
    document.querySelectorAll('[data-formel]').forEach(function (btn) { btn.setAttribute('aria-pressed', String(btn.dataset.formel === formel)); });
    scale();
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
      return document.fonts ? document.fonts.ready : null;
    })
    .then(function () { window.__kortKlart = true; })
    .catch(function (e) {
      $('#k-date').textContent = 'Matchen kunde inte laddas (' + e.message + ').';
      window.__kortKlart = true;
    });
})();
