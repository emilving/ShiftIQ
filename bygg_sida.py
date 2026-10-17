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


def logo_url(abbr):
    return f"https://assets.nhle.com/logos/nhl/svg/{abbr}_light.svg" if abbr else ""


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


def val(v):
    """Tal till JSON: heltal som heltal, annars två decimaler, saknas = None."""
    try:
        if v is None or pd.isna(v):
            return None
    except (TypeError, ValueError):
        return v
    f = float(v)
    return int(f) if f.is_integer() else round(f, 3)


# Grupper på spelarsidan: (rubrik, [(etikett, kolumn, typ)]). typ: n = tal, p = andel som procent, m = minuter/match
SPELARGRUPPER = [
    ("Poäng", [("Matcher", "Matcher", "n"), ("Mål", "Mål", "n"), ("Assist", "Assist", "n"), ("Poäng", "Poäng", "n"),
               ("Primära assist", "Primära assist", "n"), ("Sekundära assist", "Sekundära assist", "n"),
               ("Powerplaypoäng", "PP-poäng", "n"), ("Powerplaymål", "PP-mål", "n"), ("Boxplaypoäng", "SH-poäng", "n"),
               ("Mål i tom bur", "Mål i tom bur", "n"), ("Plus/minus", "Plus/minus", "n"), ("Poäng/60 min", "Poäng/60", "n")]),
    ("Förväntat", [("Förväntade mål", "Förväntade mål", "n"), ("Förväntade assist", "Förväntade assist", "n"),
                   ("Förväntade poäng", "Förväntade poäng", "n"), ("Mål över förväntan", "Mål över förväntan", "n"),
                   ("Assist över förväntan", "Assist över förväntan", "n"), ("Poäng över förväntan", "Poäng över förväntan", "n")]),
    ("Skott", [("Skott på mål", "Skott", "n"), ("Skottförsök", "Skottförsök", "n"), ("Skott utanför", "Missade skott", "n"),
               ("Skott blockerade", "Egna skott blockerade", "n"), ("Skottprocent", "Skott-%", "p"),
               ("Skott/60 min", "Skott/60", "n"), ("Mål/60 min", "Mål/60", "n"), ("ixG (utan tom bur)", "ixG", "n")]),
    ("Istid per match", [("Totalt", "Istid/match", "t"), ("5 mot 5", "Istid 5v5 (min)", "m"),
                         ("Powerplay", "Istid PP (min)", "m"), ("Boxplay", "Istid SH (min)", "m")]),
    ("På isen vid 5 mot 5", [("Skottförsök för", "CF 5v5", "n"), ("Skottförsök mot", "CA 5v5", "n"), ("Andel skottförsök", "CF% 5v5", "p"),
                             ("Mål för", "GF 5v5", "n"), ("Mål mot", "GA 5v5", "n"), ("Andel mål", "GF% 5v5", "p"),
                             ("xG för", "xGF 5v5", "n"), ("xG mot", "xGA 5v5", "n"), ("Andel xG", "xGF% 5v5", "p")]),
    ("Fysiskt och tekningar", [("Tacklingar", "Träffar", "n"), ("Blev tacklad", "Tacklad", "n"), ("Blockerade skott", "Blockeringar", "n"),
                               ("Puckvinster", "Puckvinster", "n"), ("Puckförluster", "Puckförluster", "n"),
                               ("Vunna tekningar", "Vunna tekningar", "n"), ("Förlorade tekningar", "Förlorade tekningar", "n"),
                               ("Tekningsprocent", "Tekning-%", "p")]),
    ("Utvisningar", [("Tagna", "Tagna utvisningar", "n"), ("Dragna", "Dragna utvisningar", "n"),
                     ("Netto", "Utvisningsnetto", "n"), ("Utvisningsminuter", "Utvisningsminuter", "n")]),
    ("Game Score", [("Game Score+ snitt", "Game Score+ snitt", "n"), ("Game Score+ bästa", "Game Score+ bästa", "n"),
                    ("Game Score+ sämsta", "Game Score+ sämsta", "n"), ("Game Score+ summa", "Game Score+", "n"),
                    ("Game Score snitt", "Game Score snitt", "n"), ("Game Score summa", "Game Score", "n")]),
]
MVGRUPPER = [
    ("Matcher", [("Matcher", "Matcher", "n"), ("Starter", "Starter", "n"), ("Vinster", "Vinster", "n"), ("Istid totalt (min)", "Istid (min)", "n")]),
    ("Räddningar", [("Skott mot", "Skott mot", "n"), ("Räddningar", "Räddningar", "n"), ("Insläppta", "Insläppta", "n"),
                    ("Räddningsprocent", "Räddnings-%", "p"), ("Räddningsprocent 5 mot 5", "Räddnings-% 5v5", "p"),
                    ("Insläppta/60 min", "Insläppta/60", "n")]),
    ("Förväntat", [("xG mot", "xG mot", "n"), ("Insläppta på de skotten", "Insläppta (xG-skott)", "n"),
                   ("Räddade mål över förväntan (GSAx)", "GSAx", "n")]),
    ("Game Score", [("Game Score+ summa", "Game Score+", "n"), ("Game Score snitt", "Game Score snitt", "n"), ("Game Score summa", "Game Score", "n")]),
]


def grupper(r, defs):
    ut = []
    for rubrik, rader in defs:
        rr = []
        for etikett, kol, typ in rader:
            if kol not in r.index or val(r[kol]) is None:
                continue
            v = float(r[kol])
            if typ == "m":
                v = v / max(1, float(r.get("Matcher", 1)))
            rr.append([etikett, round(v, 3), typ])
        if rr:
            ut.append({"t": rubrik, "r": rr})
    return ut


def load_build(csv_dir: Path, name: str, cols=None):
    p = csv_dir / f"{name}.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, encoding="utf-8-sig", usecols=lambda c: cols is None or c in cols)
    return df


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
    V = load(csv_dir, "Vinstchans")
    PR = load(csv_dir, "Prognoser")

    # lagens namn och loggor, nyckel = förkortning
    lag_info = {}
    for _, r in T.iterrows():
        logo = r.get("Logga") if "Logga" in T else None
        lag_info[r["Lagförkortning"]] = {"n": r["Lag"], "logo": logo if isinstance(logo, str) and logo else logo_url(r["Lagförkortning"])}
    for _, r in V.iterrows():
        for sida in ("Borta", "Hemma"):
            k = r[f"{sida}lag kort"]
            if k not in lag_info or not lag_info[k]["logo"]:
                logo = r.get(f"{sida}lagets logga")
                lag_info[k] = {"n": r[f"{sida}lag"], "logo": logo if isinstance(logo, str) and logo else logo_url(k)}
    has_plus = "Game Score+" in P and P["Game Score+"].notna().any()

    spelare = [{
        "id": int(r["Spelar-id"]), "n": r["Spelare"], "lag": r["Lag"], "k": abbr.get(r["Lag"], ""),
        "pos": "B" if r["Positionsgrupp"] == "Back" else "F", "gp": integer(r["Matcher"]),
        "g": integer(r["Mål"]), "a": integer(r["Assist"]), "p": integer(r["Poäng"]),
        "gs": num(r["Game Score snitt"]), "gsS": num(r["Game Score"]),
        "pl": num(r.get("Game Score+ snitt")), "plS": num(r.get("Game Score+")),
        "toi": num(r.get("Istid/match"), 1), "rook": 1 if r.get("Rookie") == "ja" else 0,
        "xg": num(r.get("Förväntade mål")), "xa": num(r.get("Förväntade assist")), "xp": num(r.get("Förväntade poäng")),
    } for _, r in S.iterrows()]

    mv = [{
        "id": int(r["Spelar-id"]), "n": r["Spelare"], "lag": r["Lag"], "k": abbr.get(r["Lag"], ""),
        "gp": integer(r["Matcher"]), "gs": num(r["Game Score snitt"]), "gsS": num(r["Game Score"]),
        "pl": num(r.get("Game Score+ snitt")), "plS": num(r.get("Game Score+")),
        "sv": num(r.get("Räddnings-%"), 4), "gsax": num(r.get("GSAx")),
        "rook": 1 if r.get("Rookie") == "ja" else 0,
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

    if not cfg.get("visa_loggor", True):
        for v in lag_info.values():
            v["logo"] = ""

    SK = load_build(csv_dir, "Skott", {"Match-id", "Typ", "Period", "Tid", "Lag", "Skytt-id", "Skytt", "Mål", "Tom bur",
                                       "Läge (kort)", "Assist 1-id", "Assist 1", "Assist 2-id", "Assist 2", "Mål i säsongen",
                                       "Assist 1 i säsongen", "Assist 2 i säsongen"})
    goals = SK[SK["Mål"] == 1] if not SK.empty else SK
    SO = load(csv_dir, "Straffläggningar")

    def rapport(gid, bort, hemma):
        """Alla mål, lagstatistik och spelarstatistik för en match."""
        mal, bs, hs_ = [], 0, 0
        g = goals[goals["Match-id"] == gid] if len(goals) else goals
        if len(g):
            g = g.assign(_s=g["Tid"].astype(str).str.split(":").map(lambda x: int(x[0]) * 60 + int(x[1]) if len(x) == 2 else 0))
            g = g.sort_values(["Period", "_s"])
        for _, r in g.iterrows():
            if r["Lag"] == bort:
                bs += 1
            else:
                hs_ += 1
            lage = "TB" if r.get("Tom bur") == 1 else ("" if r.get("Läge (kort)") == "EV" else r.get("Läge (kort)", ""))
            ass = [[x, val(r.get(f"{x} i säsongen")), val(r.get(f"{x}-id"))] for x in ("Assist 1", "Assist 2")]
            mal.append({"per": val(r["Period"]), "tid": r["Tid"], "k": abbr.get(r["Lag"], ""),
                        "n": r["Skytt"], "id": val(r.get("Skytt-id")), "tot": val(r.get("Mål i säsongen")),
                        "a": [[r[a[0]], a[1], a[2]] for a in ass if isinstance(r.get(a[0]), str) and r.get(a[0])],
                        "lage": lage or "", "st": [bs, hs_]})
        straff = []
        if not SO.empty:
            for _, r in SO[SO["Match-id"] == gid].sort_values("Ordning").iterrows():
                straff.append({"k": r["Lagförkortning"], "n": r["Skytt"], "id": val(r.get("Skytt-id")), "mal": int(r["Mål"])})
        lagstat = {}
        for key, namn in (("b", bort), ("h", hemma)):
            t = T[(T["Match-id"] == gid) & (T["Lag"] == namn)]
            if not len(t):
                continue
            t = t.iloc[0]
            lagstat[key] = {c: val(t.get(c)) for c in ("Skott", "xGF", "Skottförsök", "Vunna tekningar", "Förlorade tekningar", "Träffar",
                                                       "Blockeringar", "Utvisningsminuter", "Utvisningar", "PP-mål")}
        spel, mvs = {}, {}
        pm = P[P["Match-id"] == gid]
        gm = GK[GK["Match-id"] == gid] if not GK.empty else GK
        for key, namn in (("b", bort), ("h", hemma)):
            rows_ = pm[pm["Lag"] == namn].sort_values(["Poäng", "Mål", "Game Score+" if "Game Score+" in pm else "Game Score"], ascending=False)
            spel[key] = [{"id": val(r["Spelar-id"]), "nr": val(r.get("Nummer")), "n": r["Spelare"], "pos": pos_code(r.get("Positionsgrupp", "")),
                          "g": val(r["Mål"]), "a": val(r["Assist"]), "p": val(r["Poäng"]), "pm": val(r.get("Plus/minus")),
                          "s": val(r["Skott"]), "xg": num(r.get("ixG")), "hit": val(r.get("Träffar")), "blk": val(r.get("Blockeringar")),
                          "fo": [val(r.get("Vunna tekningar")), val(r.get("Förlorade tekningar"))], "pim": val(r.get("Utvisningsminuter")),
                          "toi": num(r.get("Istid (min)")), "gs": num(r.get("Game Score")), "pl": num(r.get("Game Score+"))}
                         for _, r in rows_.iterrows()]
            if len(gm):
                mvs[key] = [{"id": val(r["Spelar-id"]), "nr": val(r.get("Nummer")), "n": r["Spelare"], "sa": val(r.get("Skott mot")),
                             "sv": val(r.get("Räddningar")), "ga": val(r.get("Insläppta")), "svp": num(r.get("Räddnings-%"), 3),
                             "gsax": num(r.get("GSAx")), "toi": num(r.get("Istid (min)")), "bes": r.get("Beslut") if isinstance(r.get("Beslut"), str) else "",
                             "gs": num(r.get("Game Score")), "pl": num(r.get("Game Score+"))}
                            for _, r in gm[gm["Lag"] == namn].sort_values("Istid (min)", ascending=False).iterrows()]
        return {"mal": mal, "straff": straff, "lag": lagstat, "spelare": spel, "mv": mvs}

    pre = {}
    for _, r in PR.iterrows():
        pre[int(r["Match-id"])] = {"b": num(r["Chans borta"], 3), "h": num(r["Chans hemma"], 3)}

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
                        "hm": integer(m["Hemmamål"]), "avg": m["Avgjord i"], "stj": stj, "png": False,
                        "pre": pre.get(gid)})

        def side(team, short, goals):
            r = rows[rows["Lag"] == team]
            return {"n": team, "k": short, "m": goals, "logo": lag_info.get(short, {}).get("logo", ""),
                    "spelare": [[pos_code(x["Position"]), x["Spelare"], num(x["Game Score"]), num(x.get("Game Score+")), val(x["Spelar-id"])]
                                for _, x in r.iterrows()]}
        cards[gid] = {"id": gid, "d": m["Datum"], "datumText": datum_text(m["Datum"]), "avg": m["Avgjord i"],
                      "b": side(m["Bortalag"], m["Bortalag kort"], integer(m["Bortamål"])),
                      "h": side(m["Hemmalag"], m["Hemmalag kort"], integer(m["Hemmamål"])),
                      "plus": bool(has_plus), "namn": cfg.get("namn", ""), "sajt": cfg.get("sajtnamn", "Slotline"),
                      "png": False, "rapport": rapport(gid, m["Bortalag"], m["Hemmalag"])}

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

    # kommande matcher med vinstchans
    idag = dt.date.today().isoformat()
    kommande = []
    for _, r in V.iterrows():
        if str(r["Datum"]) < idag:
            continue
        g = {"id": int(r["Match-id"]), "d": str(r["Datum"]), "start": r.get("Start (UTC)") if isinstance(r.get("Start (UTC)"), str) else ""}
        for key, sida in (("b", "Borta"), ("h", "Hemma")):
            g[key] = {"n": r[f"{sida}lag"], "k": r[f"{sida}lag kort"], "p": num(r[f"Chans {sida.lower()}"], 4),
                      "xg": num(r[f"Förväntade mål {sida.lower()}"]), "trott": r[f"{sida} spelade igår"] == "ja",
                      "gp": integer(r[f"{sida} matcher"]), "mal": num(r[f"{sida} mål/match"]),
                      "insl": num(r[f"{sida} insläppta/match"]), "xgf": num(r[f"{sida} xG för/match"]),
                      "xga": num(r[f"{sida} xG mot/match"]), "gsax": num(r[f"{sida} GSAx/match"]),
                      "form": r[f"{sida} form"] if isinstance(r[f"{sida} form"], str) else ""}
        kommande.append(g)
    kommande.sort(key=lambda g: (g["d"], g["start"], g["id"]))

    # träffsäkerhet: matcher där båda lagen spelat minst 3 matcher innan
    traff = {"n": 0, "k": 0, "grupper": []}
    if not PR.empty:
        q = PR[(PR["Matcher borta före"] >= 3) & (PR["Matcher hemma före"] >= 3)]
        traff["n"], traff["k"] = int(len(q)), int((q["Favoriten vann"] == "ja").sum())
        for lo, hi, namn in ((0.5, 0.55, "50–55 %"), (0.55, 0.6, "55–60 %"), (0.6, 0.65, "60–65 %"), (0.65, 1.01, "65 % eller mer")):
            g = q[(q["Favoritens chans"] >= lo) & (q["Favoritens chans"] < hi)]
            traff["grupper"].append({"namn": namn, "n": int(len(g)), "k": int((g["Favoriten vann"] == "ja").sum()),
                                     "snitt": num(g["Favoritens chans"].mean(), 3) if len(g) else None})

    data = {
        "sasong": f"{season[:4]}/{season[6:]}", "uppdaterad": now_text(),
        "sajt": cfg.get("sajtnamn", "Slotline"), "lagInfo": lag_info, "kommande": kommande, "traff": traff,
        "forsta": str(M["Datum"].min()), "sista": str(M["Datum"].max()),
        "plus": bool(has_plus), "namn": cfg.get("namn", ""), "kontakt": cfg.get("kontakt", ""), "excel": None,
        "spelare": spelare, "mv": mv, "lag": lag, "matcher": matcher,
        "topp": {"gs": {"bast": top("Game Score", False), "samst": top("Game Score", True)},
                 "pl": {"bast": top("Game Score+", False), "samst": top("Game Score+", True)}},
        "vinnare": {"gs": winner_share("Game Score"), "pl": winner_share("Game Score+")},
    }
    # en fil per spelare: all säsongsstatistik och matchlogg
    sidor = {}
    for _, r in S.iterrows():
        pid = int(r["Spelar-id"])
        logg = P[P["Spelar-id"] == pid].sort_values("Datum")
        sidor[pid] = {"id": pid, "n": r["Spelare"], "lag": r["Lag"], "k": abbr.get(r["Lag"], ""), "pos": r.get("Position", ""),
                      "mv": False, "rook": r.get("Rookie") == "ja", "grupper": grupper(r, SPELARGRUPPER),
                      "logg": [{"id": int(x["Match-id"]), "d": x["Datum"], "mot": abbr.get(x["Motståndare"], ""), "hemma": x["Hemma/borta"] == "Hemma",
                                "res": x["Resultat"], "st": [val(x["Mål för"]), val(x["Mål mot"])], "g": val(x["Mål"]), "a": val(x["Assist"]),
                                "p": val(x["Poäng"]), "s": val(x["Skott"]), "pm": val(x.get("Plus/minus")), "toi": num(x.get("Istid (min)")),
                                "gs": num(x.get("Game Score")), "pl": num(x.get("Game Score+"))} for _, x in logg.iterrows()]}
    for _, r in (G.iterrows() if not G.empty else []):
        pid = int(r["Spelar-id"])
        logg = GK[GK["Spelar-id"] == pid].sort_values("Datum")
        sidor[pid] = {"id": pid, "n": r["Spelare"], "lag": r["Lag"], "k": abbr.get(r["Lag"], ""), "pos": "Målvakt",
                      "mv": True, "rook": r.get("Rookie") == "ja", "grupper": grupper(r, MVGRUPPER),
                      "logg": [{"id": int(x["Match-id"]), "d": x["Datum"], "mot": abbr.get(x["Motståndare"], ""), "hemma": x["Hemma/borta"] == "Hemma",
                                "res": x["Resultat"], "st": [val(x["Mål för"]), val(x["Mål mot"])], "sa": val(x.get("Skott mot")),
                                "sv": val(x.get("Räddningar")), "ga": val(x.get("Insläppta")), "svp": num(x.get("Räddnings-%"), 3),
                                "gsax": num(x.get("GSAx")), "toi": num(x.get("Istid (min)")), "bes": x.get("Beslut") if isinstance(x.get("Beslut"), str) else "",
                                "gs": num(x.get("Game Score")), "pl": num(x.get("Game Score+"))} for _, x in logg.iterrows()]}
    for v in sidor.values():
        v["logo"] = lag_info.get(v["k"], {}).get("logo", "")
        v["sajt"] = cfg.get("sajtnamn", "Slotline")
        v["plus"] = bool(has_plus)
    return data, cards, sidor


def card_hash(card):
    c = dict(card)
    c.pop("png", None)
    c.pop("rapport", None)
    c["b"] = dict(c["b"], spelare=[x[:4] for x in c["b"]["spelare"]])
    c["h"] = dict(c["h"], spelare=[x[:4] for x in c["h"]["spelare"]])
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

    data, cards, sidor = build_data(data_root / "csv", a.sasong, cfg)
    (site / "data" / "spelare").mkdir(parents=True, exist_ok=True)
    for pid, sp in sidor.items():
        (site / "data" / "spelare" / f"{pid}.json").write_text(json.dumps(sp, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    for x in sorted(data_root.glob("*.xlsx"), key=lambda p: p.stat().st_mtime)[-1:]:
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
