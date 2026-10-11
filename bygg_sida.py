#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bygger webbsidan med statistik och matchkort från nhl_stats.py:s CSV-filer.

  python bygg_sida.py                 # bygger mappen site/ för innevarande säsong
  python bygg_sida.py --bilder        # samma, plus en PNG-bild per match (senaste veckorna)

Sidan i site/ är statisk (HTML, CSS, JS och JSON) och kan läggas på GitHub Pages
eller öppnas lokalt med:  python -m http.server --directory site
"""

import argparse
import datetime as dt
import functools
import hashlib
import http.server
import json
import shutil
import sys
import threading
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from nhl_stats import current_season  # noqa: E402

MAN = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november", "december"]
DAG = ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag"]


def log(msg):
    print(msg, flush=True)


def num(v, nd=2):
    try:
        if v is None or pd.isna(v):
            return None
    except (TypeError, ValueError):
        return None
    return round(float(v), nd)


def integer(v):
    return 0 if v is None or pd.isna(v) else int(v)


def pos_code(p):
    if p == "Målvakt":
        return "MV"
    if p == "Back":
        return "B"
    return "F"


def load(csv_dir: Path, name: str):
    p = csv_dir / f"{name}.csv"
    return pd.read_csv(p, encoding="utf-8-sig") if p.exists() else pd.DataFrame()


def datum_text(s):
    d = dt.date.fromisoformat(s)
    return f"{DAG[d.weekday()]} {d.day} {MAN[d.month - 1]} {d.year}"


def now_text():
    try:
        from zoneinfo import ZoneInfo
        t = dt.datetime.now(ZoneInfo("Europe/Stockholm"))
    except Exception:  # noqa: BLE001
        t = dt.datetime.now()
    return f"{t.day} {MAN[t.month - 1]} {t.year} kl. {t:%H.%M}"


def build_data(csv_dir: Path, season: str, cfg: dict):
    P = load(csv_dir, "Per match")
    GK = load(csv_dir, "Målvakter per match")
    S = load(csv_dir, "Spelare")
    G = load(csv_dir, "Målvakter")
    L = load(csv_dir, "Lag")
    M = load(csv_dir, "Matcher")
    T = load(csv_dir, "Lag per match")
    if P.empty or M.empty:
        raise SystemExit(f"Hittar ingen statistik i {csv_dir}. Kör först: python nhl_stats.py")

    abbr = dict(zip(T["Lag"], T["Lagförkortning"]))
    has_plus = "Game Score+" in P and P["Game Score+"].notna().any()

    spelare = [{
        "id": int(r["Spelar-id"]), "n": r["Spelare"], "lag": r["Lag"], "k": abbr.get(r["Lag"], ""),
        "pos": "B" if r["Positionsgrupp"] == "Back" else "F", "gp": integer(r["Matcher"]),
        "g": integer(r["Mål"]), "a": integer(r["Assist"]), "p": integer(r["Poäng"]),
        "gs": num(r["Game Score snitt"]), "gsS": num(r["Game Score"]),
        "pl": num(r.get("Game Score+ snitt")), "plS": num(r.get("Game Score+")),
        "toi": num(r.get("Istid/match"), 1),
    } for _, r in S.iterrows()]

    mv = [{
        "id": int(r["Spelar-id"]), "n": r["Spelare"], "lag": r["Lag"], "k": abbr.get(r["Lag"], ""),
        "gp": integer(r["Matcher"]), "gs": num(r["Game Score snitt"]), "gsS": num(r["Game Score"]),
        "pl": num(r.get("Game Score+ snitt")), "plS": num(r.get("Game Score+")),
        "sv": num(r.get("Räddnings-%"), 4), "gsax": num(r.get("GSAx")),
    } for _, r in G.iterrows()] if not G.empty else []

    lag = [{
        "lag": r["Lag"], "k": abbr.get(r["Lag"], ""), "gp": integer(r["Matcher"]), "w": integer(r["V"]),
        "l": integer(r["F"]), "otl": integer(r["FÖ"]), "pts": integer(r["Poäng"]),
        "gf": integer(r["Mål för"]), "ga": integer(r["Mål mot"]),
        "gs": num(r["Game Score/match"]), "pl": num(r.get("Game Score+/match")),
    } for _, r in L.iterrows()]

    # alla insatser (utespelare + målvakter) i en tabell
    cols = ["Match-id", "Datum", "Spelar-id", "Spelare", "Lag", "Lagförkortning", "Motståndare", "Position", "Game Score", "Game Score+"]
    ins = pd.concat([P[[c for c in cols if c in P]], GK[[c for c in cols if c in GK]] if not GK.empty else None], ignore_index=True)
    ins["Motst kort"] = ins["Motståndare"].map(abbr)

    matcher, cards = [], {}
    for _, m in M.sort_values(["Datum", "Match-id"]).iterrows():
        gid = int(m["Match-id"])
        rows = ins[ins["Match-id"] == gid]
        stj = {}
        for key, col in (("gs", "Game Score"), ("pl", "Game Score+")):
            sub = rows[rows[col].notna()] if col in rows else rows.iloc[0:0]
            if len(sub):
                top = sub.loc[sub[col].idxmax()]
                stj[key] = {"n": top["Spelare"], "k": top["Lagförkortning"], "v": num(top[col])}
        matcher.append({"id": gid, "d": m["Datum"], "b": m["Bortalag"], "h": m["Hemmalag"],
                        "bk": m["Bortalag kort"], "hk": m["Hemmalag kort"], "bm": integer(m["Bortamål"]),
                        "hm": integer(m["Hemmamål"]), "avg": m["Avgjord i"], "stj": stj, "png": False})

        def side(team, short, goals):
            r = rows[rows["Lag"] == team]
            return {"n": team, "k": short, "m": goals,
                    "spelare": [[pos_code(x["Position"]), x["Spelare"], num(x["Game Score"]), num(x.get("Game Score+"))]
                                for _, x in r.iterrows()]}
        cards[gid] = {"id": gid, "d": m["Datum"], "datumText": datum_text(m["Datum"]), "avg": m["Avgjord i"],
                      "b": side(m["Bortalag"], m["Bortalag kort"], integer(m["Bortamål"])),
                      "h": side(m["Hemmalag"], m["Hemmalag kort"], integer(m["Hemmamål"])),
                      "plus": bool(has_plus), "namn": cfg.get("namn", ""), "png": False}

    def top(col, asc):
        sub = ins[ins[col].notna()] if col in ins else ins.iloc[0:0]
        sub = sub.sort_values(col, ascending=asc).head(20)
        return [{"n": r["Spelare"], "k": r["Lagförkortning"], "mot": r["Motst kort"], "d": r["Datum"],
                 "v": num(r[col]), "id": int(r["Match-id"])} for _, r in sub.iterrows()]

    def winner_share(col):
        n = k = 0
        for _, m in M.iterrows():
            h, a = m.get(f"Hemmalagets {col}"), m.get(f"Bortalagets {col}")
            if pd.isna(h) or pd.isna(a):
                continue
            n += 1
            home_won = m["Hemmamål"] > m["Bortamål"]
            if (h > a) == home_won and h != a:
                k += 1
        return [k, n]

    data = {
        "sasong": f"{season[:4]}/{season[6:]}", "uppdaterad": now_text(),
        "forsta": str(M["Datum"].min()), "sista": str(M["Datum"].max()),
        "plus": bool(has_plus), "namn": cfg.get("namn", ""), "excel": None,
        "spelare": spelare, "mv": mv, "lag": lag, "matcher": matcher,
        "topp": {"gs": {"bast": top("Game Score", False), "samst": top("Game Score", True)},
                 "pl": {"bast": top("Game Score+", False), "samst": top("Game Score+", True)}},
        "vinnare": {"gs": winner_share("Game Score"), "pl": winner_share("Game Score+")},
    }
    return data, cards


def card_hash(card):
    c = dict(card)
    c.pop("png", None)
    return hashlib.sha1(json.dumps(c, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def render_pngs(site: Path, cards: dict, cache: Path, days: int):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("Playwright saknas – hoppar över bilderna. Installera med: pip install playwright && python -m playwright install chromium")
        return set()
    if not cards:
        return set()
    cache.mkdir(parents=True, exist_ok=True)
    last = max(dt.date.fromisoformat(c["d"]) for c in cards.values())
    want = [c for c in cards.values() if (last - dt.date.fromisoformat(c["d"])).days <= days]
    todo = []
    for c in want:
        h = card_hash(c)
        png, sha = cache / f"{c['id']}.png", cache / f"{c['id']}.sha"
        if not (png.exists() and sha.exists() and sha.read_text() == h):
            todo.append((c, h))
    log(f"Matchkort som bilder: {len(want)} senaste matcherna, {len(todo)} behöver ritas.")
    if todo:
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        handler = functools.partial(Quiet, directory=str(site))
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
                for i, (c, h) in enumerate(todo, 1):
                    page.goto(f"http://127.0.0.1:{port}/kort.html?id={c['id']}&export=1")
                    page.wait_for_function("window.__kortKlart === true", timeout=30000)
                    page.locator("#kort").screenshot(path=str(cache / f"{c['id']}.png"))
                    (cache / f"{c['id']}.sha").write_text(h)
                    if i % 25 == 0 or i == len(todo):
                        log(f"  {i}/{len(todo)} bilder klara")
                browser.close()
        finally:
            srv.shutdown()
    ok = set()
    (site / "bilder").mkdir(exist_ok=True)
    for c in want:
        png, sha = cache / f"{c['id']}.png", cache / f"{c['id']}.sha"
        if png.exists() and sha.exists() and sha.read_text() == card_hash(c):
            shutil.copy2(png, site / "bilder" / png.name)
            ok.add(c["id"])
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bygger webbsidan från statistiken.")
    ap.add_argument("--data", default=str(HERE / "nhl_data"), help="mappen nhl_stats.py skriver till")
    ap.add_argument("--sasong", default=current_season())
    ap.add_argument("--ut", default=str(HERE / "site"), help="mapp att bygga sidan i")
    ap.add_argument("--bilder", action="store_true", help="skapa en PNG per match (kräver Playwright)")
    a = ap.parse_args(argv)

    cfg_path = HERE / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    data_root = Path(a.data) / a.sasong
    if not (data_root / "csv" / "Per match.csv").exists():
        # Före säsongsstart: visa senaste säsongen som har statistik.
        older = sorted(d for d in Path(a.data).glob("*") if (d / "csv" / "Per match.csv").exists())
        if not older:
            raise SystemExit("Hittar ingen statistik ännu. Kör först: python nhl_stats.py")
        data_root = older[-1]
        a.sasong = data_root.name
        log(f"Ingen statistik för innevarande säsong än – visar {a.sasong}.")
    site = Path(a.ut)
    if site.exists():
        shutil.rmtree(site)
    shutil.copytree(HERE / "webb", site)
    (site / ".nojekyll").write_text("")
    (site / "data" / "matcher").mkdir(parents=True, exist_ok=True)

    data, cards = build_data(data_root / "csv", a.sasong, cfg)
    for x in data_root.glob("NHL_statistik_*.xlsx"):
        shutil.copy2(x, site / "data" / x.name)
        data["excel"] = f"data/{x.name}"

    def write_cards():
        for gid, c in cards.items():
            (site / "data" / "matcher" / f"{gid}.json").write_text(json.dumps(c, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    write_cards()
    (site / "data" / "sasong.json").write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    if a.bilder:
        done = render_pngs(site, cards, data_root / "bilder", int(cfg.get("dagar_med_bilder", 21)))
        for c in cards.values():
            c["png"] = c["id"] in done
        for m in data["matcher"]:
            m["png"] = m["id"] in done
        write_cards()
        (site / "data" / "sasong.json").write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    log(f"Webbsidan är byggd i {site} ({len(data['spelare'])} utespelare, {len(cards)} matchkort).")


if __name__ == "__main__":
    main()
