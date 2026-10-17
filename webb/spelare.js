/* Slotline – spelarsidan. Läser data/spelare/<id>.json. */
(function () {
  'use strict';
  var MAN_K = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];
  var FARG = window.LAGFARG || {};
  var id = new URLSearchParams(location.search).get('id');
  function $(s) { return document.querySelector(s); }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function minus(s) { return String(s).replace('-', '−'); }
  function tal(v, dec) {
    if (v == null || isNaN(v)) return '–';
    if (dec == null) dec = Number.isInteger(v) ? 0 : 2;
    return minus(v.toFixed(dec));
  }
  function tid(min) { if (min == null) return '–'; var t = Math.round(min * 60); return Math.floor(t / 60) + ':' + ('0' + (t % 60)).slice(-2); }
  function procent(v) { return v == null ? '–' : (v * 100).toFixed(1).replace('.', ',') + ' %'; }
  function datum(s) { var d = new Date(s + 'T12:00:00'); return d.getDate() + ' ' + MAN_K[d.getMonth()]; }
  function prick(abbr, size) {
    var s = el('span', 'lagprick'); s.style.width = size + 'px'; s.style.height = size + 'px';
    s.style.setProperty('--c', (FARG[abbr] || ['#9AA8B6'])[0]); s.appendChild(el('i')); return s;
  }
  function logo(src, size, abbr) {
    if (!src) return prick(abbr, size);
    var img = el('img', 'logo'); img.alt = ''; img.width = size; img.height = size;
    img.onerror = function () { if (img.parentNode) img.parentNode.replaceChild(prick(abbr, size), img); };
    img.src = src; return img;
  }
  function varde(r) {
    var v = r[1], typ = r[2];
    if (typ === 'p') return procent(v);
    if (typ === 't' || typ === 'm') return tid(v);
    if (/över förväntan|Netto|Plus\/minus/.test(r[0]) && v > 0) return '+' + tal(v);
    return tal(v);
  }
  function hitta(S, namn) {
    for (var i = 0; i < S.grupper.length; i++) for (var j = 0; j < S.grupper[i].r.length; j++) if (S.grupper[i].r[j][0] === namn) return S.grupper[i].r[j][1];
    return null;
  }

  function render(S) {
    document.title = S.n + ' – ' + (S.sajt || 'Slotline');
    if (document.referrer && document.referrer.indexOf(location.origin) === 0) {
      $('#tillbaka').textContent = 'Tillbaka';
      $('#tillbaka').addEventListener('click', function (e) { e.preventDefault(); history.back(); });
    } else if (S.mv) $('#tillbaka').href = './#malvakter';
    $('#sp-logo').appendChild(logo(S.logo, 64, S.k));
    var h = $('#sp-namn'); h.textContent = S.n;
    if (S.rook) { var r = el('span', 'rookie', 'R'); r.title = 'Rookie'; h.appendChild(r); }
    $('#sp-sub').textContent = S.lag + ' · ' + S.pos + (S.rook ? ' · Rookie' : '');

    var tiles = $('#sp-tiles');
    var plus = S.plus;
    var lista = S.mv
      ? [['Matcher', hitta(S, 'Matcher')], ['Räddningsprocent', procent(hitta(S, 'Räddningsprocent'))], ['GSAx', tal(hitta(S, 'Räddade mål över förväntan (GSAx)'))],
         [plus ? 'Game Score+' : 'Game Score', tal(hitta(S, plus ? 'Game Score+ summa' : 'Game Score summa'))]]
      : [['Matcher', hitta(S, 'Matcher')], ['Mål', hitta(S, 'Mål')], ['Assist', hitta(S, 'Assist')], ['Poäng', hitta(S, 'Poäng')],
         ['Förväntade poäng', tal(hitta(S, 'Förväntade poäng'), 1)], [plus ? 'Game Score+ snitt' : 'Game Score snitt', tal(hitta(S, plus ? 'Game Score+ snitt' : 'Game Score snitt'))]];
    lista.forEach(function (t) {
      if (t[1] == null || t[1] === '–') return;
      var d = el('div', 'sp-tile'); d.appendChild(el('div', 'v', String(t[1]))); d.appendChild(el('div', 'l', t[0])); tiles.appendChild(d);
    });

    var diff = hitta(S, 'Poäng över förväntan');
    if (!S.mv && diff != null) {
      var p = hitta(S, 'Poäng'), xp = hitta(S, 'Förväntade poäng');
      var tur = $('#sp-tur'); tur.hidden = false;
      var a = Math.abs(diff).toFixed(1).replace('.', ',');
      if (diff <= -1) { tur.className = 'sp-tur otur'; tur.textContent = 'Borde ha fler poäng. Chanserna han varit med om är värda ' + xp.toFixed(1).replace('.', ',') + ' poäng, men han har ' + p + '. Det är ' + a + ' färre än väntat.'; }
      else if (diff >= 1) { tur.className = 'sp-tur tur'; tur.textContent = 'Har haft flyt. Han har ' + p + ' poäng, men chanserna är bara värda ' + xp.toFixed(1).replace('.', ',') + '. Det är ' + a + ' fler än väntat.'; }
      else { tur.className = 'sp-tur'; tur.textContent = 'Poängen stämmer med chanserna: ' + p + ' poäng mot ' + xp.toFixed(1).replace('.', ',') + ' förväntade.'; }
    }

    var gr = $('#sp-grupper');
    S.grupper.forEach(function (g) {
      var box = el('section', 'sp-grupp');
      box.appendChild(el('h3', null, g.t));
      var dl = el('dl');
      g.r.forEach(function (r) { dl.appendChild(el('dt', null, r[0])); dl.appendChild(el('dd', null, varde(r))); });
      box.appendChild(dl);
      gr.appendChild(box);
    });

    var kol = S.mv
      ? [['Datum', ''], ['Mot', ''], ['Res.', ''], ['Skott mot', 'n'], ['Räddn.', 'n'], ['Insl.', 'n'], ['Rädd.%', 'n'], ['GSAx', 'n hn'], ['Istid', 'n hn'], [plus ? 'GS+' : 'GS', 'n']]
      : [['Datum', ''], ['Mot', ''], ['Res.', ''], ['M', 'n'], ['A', 'n'], ['P', 'n'], ['Skott', 'n hn'], ['+/−', 'n hn'], ['Istid', 'n hn'], [plus ? 'GS+' : 'GS', 'n']];
    var tr = el('tr'); kol.forEach(function (k) { tr.appendChild(el('th', k[1], k[0])); });
    $('#sp-logg thead').appendChild(tr);
    var tb = $('#sp-logg tbody');
    S.logg.slice().reverse().forEach(function (m) {
      var r = el('tr', 'click'); r.tabIndex = 0;
      var c = function (v, cls) { var t = el('td', cls); if (v instanceof Node) t.appendChild(v); else t.textContent = v == null ? '–' : v; r.appendChild(t); return t; };
      c(datum(m.d), 'm');
      var mot = el('span', 'sp-mot'); mot.appendChild(document.createTextNode(m.hemma ? 'mot ' : '@ ')); mot.appendChild(logo((window.__loggor || {})[m.mot], 20, m.mot)); mot.appendChild(document.createTextNode(m.mot)); c(mot, '');
      var res = el('span', 'sp-res ' + (m.res === 'V' ? 'v' : 'f'), (m.res === 'FÖ' ? 'FÖ' : m.res) + ' ' + m.st[0] + '–' + m.st[1]); c(res, '');
      if (S.mv) {
        c(m.sa, 'n'); c(m.sv, 'n'); c(m.ga, 'n'); c(procent(m.svp), 'n'); c(tal(m.gsax), 'n hn'); c(tid(m.toi), 'n hn');
      } else {
        c(m.g, 'n' + (m.g ? ' fet' : '')); c(m.a, 'n' + (m.a ? ' fet' : '')); c(m.p, 'n' + (m.p ? ' fet' : ''));
        c(m.s, 'n hn'); c(m.pm == null ? '–' : (m.pm > 0 ? '+' + m.pm : minus(m.pm)), 'n hn'); c(tid(m.toi), 'n hn');
      }
      var v = plus ? m.pl : m.gs; var t = c(tal(v), 'n fet'); if (v != null && v < 0) t.style.color = 'var(--svag)';
      var gaTill = function () { location.href = 'kort.html?id=' + m.id; };
      r.addEventListener('click', gaTill);
      r.addEventListener('keydown', function (e) { if (e.key === 'Enter') gaTill(); });
      tb.appendChild(r);
    });
  }

  if (!id) { $('#sp-namn').textContent = 'Ingen spelare vald.'; return; }
  Promise.all([
    fetch('data/spelare/' + encodeURIComponent(id) + '.json', { cache: 'no-store' }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }),
    fetch('data/sasong.json', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; })
  ]).then(function (x) {
    var loggor = {};
    if (x[1] && x[1].lagInfo) Object.keys(x[1].lagInfo).forEach(function (k) { loggor[k] = x[1].lagInfo[k].logo; });
    window.__loggor = loggor;
    render(x[0]);
  }).catch(function (e) { $('#sp-namn').textContent = 'Spelaren kunde inte laddas (' + e.message + ').'; });
})();
