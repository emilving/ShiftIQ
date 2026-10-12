# -*- coding: utf-8 -*-
"""
Vinstchans – ShiftIQ:s matchmodell.

Så räknas chansen att vinna:
1. Varje lags styrka tas fram ur säsongens matcher: gjorda och insläppta mål
   (utan mål i tom bur) och förväntade mål (xG) för och emot. xG väger tyngst,
   eftersom chanserna säger mer om nästa match än vilka skott som råkade gå in.
   Eftersom insläppta mål också ingår räknas målvaktsspelet med.
2. Senare matcher väger mer än tidiga (en match som är HALVERING matcher gammal
   väger hälften). Varje lag dras också mot ligasnittet med KRYMP "snittmatcher",
   så att ett par matcher i början av säsongen inte ger orimliga siffror.
3. Förväntade mål i matchen = eget anfall × motståndarens försvar / ligasnitt,
   med fördel för hemmalaget och nackdel för lag som spelade dagen innan.
4. Chansen räknas med Poissonfördelningen. Blir det lika efter full tid avgörs
   en del i förlängning (där det bästa anfallet har en liten fördel) och resten
   på straffar (lika chans).
"""

import datetime as dt
import math

import numpy as np
import pandas as pd

LIGASNITT_START = 3.0   # mål per lag och match innan säsongen har gett någon data
HALVERING = 20          # matcher – så gammal är en match när den väger hälften
KRYMP = 8               # antal snittmatcher varje lag dras mot
XG_VIKT = 0.65          # hur mycket xG väger jämfört med riktiga mål
HEMMA = 1.05            # hemmalagets anfall gånger, bortalagets delat med
TROTT = 0.97            # anfall gånger (och försvar delat med) dagen efter en match
ANDEL_FORLANGNING = 0.6 # andel av de oavgjorda matcherna som avgörs i förlängning
MAX_MAL = 15
MIN_MATCHER_TRAFF = 3   # båda lagen ska ha spelat så här många matcher innan en prognos räknas i träffsäkerheten

KOLUMNER = ["Match-id", "Datum", "Lag-id", "Lag", "Lagförkortning", "Logga", "Hemma/borta", "Resultat",
            "Mål för", "Mål mot", "Mål (ej tom bur)", "Insläppta (ej tom bur)", "xGF", "xGA"]


def _poisson(lam):
    k = np.arange(MAX_MAL + 1)
    return np.exp(-lam + k * math.log(lam) - np.array([math.lgamma(x + 1) for x in k]))


def chans(mal_hemma, mal_borta):
    """Chansen att vinna (hemma, borta) givet förväntade mål för respektive lag."""
    m = np.outer(_poisson(mal_hemma), _poisson(mal_borta))  # rad = hemmamål, kolumn = bortamål
    total = m.sum()
    hemma_ordinarie = np.tril(m, -1).sum() / total
    oavgjort = np.trace(m) / total
    forl_hemma = ANDEL_FORLANGNING * mal_hemma / (mal_hemma + mal_borta) + (1 - ANDEL_FORLANGNING) * 0.5
    p = hemma_ordinarie + oavgjort * forl_hemma
    return float(p), float(1 - p)


def lagmatcher(T: pd.DataFrame) -> pd.DataFrame:
    """En rad per lag och match, med de kolumner modellen behöver."""
    df = T.copy()
    if "Lag-id" not in df and "_id" in df:
        df["Lag-id"] = df["_id"]
    for c in ("Mål (ej tom bur)", "Insläppta (ej tom bur)"):
        if c not in df:
            df[c] = df["Mål för" if c.startswith("Mål") else "Mål mot"]
    for c in ("xGF", "xGA", "Logga"):
        if c not in df:
            df[c] = np.nan
    df = df[[c for c in KOLUMNER if c in df]].copy()
    df["Datum"] = df["Datum"].astype(str)
    return df.sort_values(["Datum", "Match-id"]).reset_index(drop=True)


def styrka(rows: pd.DataFrame, fore: str):
    """Ligasnitt och varje lags anfall/försvar räknat på matcher före datumet `fore`."""
    tidigare = rows[rows["Datum"] < fore]
    snitt = float(tidigare["Mål (ej tom bur)"].mean()) if len(tidigare) else LIGASNITT_START
    if not snitt > 0:
        snitt = LIGASNITT_START
    lag = {}
    for tid, g in tidigare.groupby("Lag-id"):
        g = g.sort_values(["Datum", "Match-id"], ascending=False)
        w = 0.5 ** (np.arange(len(g)) / HALVERING)
        n = w.sum()
        gf = np.average(g["Mål (ej tom bur)"], weights=w)
        ga = np.average(g["Insläppta (ej tom bur)"], weights=w)
        if g["xGF"].notna().all() and g["xGA"].notna().all():
            anfall = XG_VIKT * np.average(g["xGF"], weights=w) + (1 - XG_VIKT) * gf
            forsvar = XG_VIKT * np.average(g["xGA"], weights=w) + (1 - XG_VIKT) * ga
        else:
            anfall, forsvar = gf, ga
        lag[tid] = {"anfall": (n * anfall + KRYMP * snitt) / (n + KRYMP),
                    "forsvar": (n * forsvar + KRYMP * snitt) / (n + KRYMP),
                    "matcher": len(g)}
    return snitt, lag


def matchup(snitt, lag, hemma, borta, trott_hemma=False, trott_borta=False):
    tom = {"anfall": snitt, "forsvar": snitt, "matcher": 0}
    h, b = lag.get(hemma, tom), lag.get(borta, tom)
    th, tb = (TROTT if trott_hemma else 1.0), (TROTT if trott_borta else 1.0)
    mal_hemma = (h["anfall"] * th) * (b["forsvar"] / tb) / snitt * HEMMA
    mal_borta = (b["anfall"] * tb) * (h["forsvar"] / th) / snitt / HEMMA
    ph, pb = chans(mal_hemma, mal_borta)
    return {"mal_hemma": mal_hemma, "mal_borta": mal_borta, "chans_hemma": ph, "chans_borta": pb,
            "matcher_hemma": h["matcher"], "matcher_borta": b["matcher"]}


def _dagen_fore(datum: str) -> str:
    return (dt.date.fromisoformat(datum) - dt.timedelta(days=1)).isoformat()


def prognoser(T: pd.DataFrame) -> pd.DataFrame:
    """Prognos före varje spelad match, räknad bara på matcher som spelats innan."""
    rows = lagmatcher(T)
    if rows.empty:
        return pd.DataFrame()
    spelat = set(zip(rows["Lag-id"], rows["Datum"]))
    borta = rows[rows["Hemma/borta"] == "Borta"].set_index("Match-id")
    ut = []
    for datum, dag in rows[rows["Hemma/borta"] == "Hemma"].groupby("Datum"):
        snitt, lag = styrka(rows, datum)
        igar = _dagen_fore(datum)
        for _, h in dag.iterrows():
            if h["Match-id"] not in borta.index:
                continue
            b = borta.loc[h["Match-id"]]
            m = matchup(snitt, lag, h["Lag-id"], b["Lag-id"], (h["Lag-id"], igar) in spelat, (b["Lag-id"], igar) in spelat)
            fav_hemma = m["chans_hemma"] >= m["chans_borta"]
            hemma_vann = h["Resultat"] == "V"
            ut.append({"Match-id": int(h["Match-id"]), "Datum": datum,
                       "Bortalag": b["Lag"], "Hemmalag": h["Lag"],
                       "Bortalag kort": b["Lagförkortning"], "Hemmalag kort": h["Lagförkortning"],
                       "Chans borta": round(m["chans_borta"], 4), "Chans hemma": round(m["chans_hemma"], 4),
                       "Förväntade mål borta": round(m["mal_borta"], 2), "Förväntade mål hemma": round(m["mal_hemma"], 2),
                       "Favorit": h["Lagförkortning"] if fav_hemma else b["Lagförkortning"],
                       "Favoritens chans": round(max(m["chans_hemma"], m["chans_borta"]), 4),
                       "Vinnare": h["Lagförkortning"] if hemma_vann else b["Lagförkortning"],
                       "Favoriten vann": "ja" if fav_hemma == hemma_vann else "nej",
                       "Matcher borta före": m["matcher_borta"], "Matcher hemma före": m["matcher_hemma"]})
    return pd.DataFrame(ut)


def _form(g: pd.DataFrame, n=5):
    return " ".join(g.sort_values(["Datum", "Match-id"])["Resultat"].tail(n).tolist())


def lagfakta(rows: pd.DataFrame):
    """Säsongssiffror per lag som visas bredvid prognosen."""
    ut = {}
    for tid, g in rows.groupby("Lag-id"):
        n = len(g)
        has_xg = g["xGF"].notna().all() and g["xGA"].notna().all()
        ut[tid] = {
            "matcher": n,
            "mal": round(g["Mål för"].sum() / n, 2),
            "inslappta": round(g["Mål mot"].sum() / n, 2),
            "xgf": round(g["xGF"].sum() / n, 2) if has_xg else None,
            "xga": round(g["xGA"].sum() / n, 2) if has_xg else None,
            "gsax": round((g["xGA"].sum() - g["Insläppta (ej tom bur)"].sum()) / n, 2) if has_xg else None,
            "form": _form(g),
        }
    return ut


def kommande(T: pd.DataFrame, matcher: list) -> pd.DataFrame:
    """Prognos för kommande matcher. `matcher` kommer från NHL:s schema."""
    if not matcher:
        return pd.DataFrame()
    rows = lagmatcher(T)
    snitt, lag = styrka(rows, "9999-12-31")
    fakta = lagfakta(rows)
    namn = {}
    for _, r in rows.iterrows():
        namn[r["Lag-id"]] = (r["Lag"], r["Lagförkortning"], r["Logga"])
    spelat = set(zip(rows["Lag-id"], rows["Datum"]))
    for g in matcher:
        spelat.add((g["home"]["id"], g["date"]))
        spelat.add((g["away"]["id"], g["date"]))
    ut = []
    for g in matcher:
        hid, bid = g["home"]["id"], g["away"]["id"]
        igar = _dagen_fore(g["date"])
        th, tb = (hid, igar) in spelat, (bid, igar) in spelat
        m = matchup(snitt, lag, hid, bid, th, tb)
        rad = {"Match-id": g["id"], "Datum": g["date"], "Start (UTC)": g.get("start", ""), "Status": g.get("state", "")}
        for sida, tid, info, trott, chans_, mal in (("Borta", bid, g["away"], tb, m["chans_borta"], m["mal_borta"]),
                                                    ("Hemma", hid, g["home"], th, m["chans_hemma"], m["mal_hemma"])):
            n, k, logga = namn.get(tid, (info.get("name"), info.get("abbr"), info.get("logo")))
            f = fakta.get(tid, {})
            rad.update({f"{sida}lag": n, f"{sida}lag kort": k, f"{sida}lag-id": tid,
                        f"{sida}lagets logga": info.get("logo") or logga,
                        f"Chans {sida.lower()}": round(chans_, 4), f"Förväntade mål {sida.lower()}": round(mal, 2),
                        f"{sida} spelade igår": "ja" if trott else "nej",
                        f"{sida} matcher": f.get("matcher", 0), f"{sida} mål/match": f.get("mal"),
                        f"{sida} insläppta/match": f.get("inslappta"), f"{sida} xG för/match": f.get("xgf"),
                        f"{sida} xG mot/match": f.get("xga"), f"{sida} GSAx/match": f.get("gsax"),
                        f"{sida} form": f.get("form", "")})
        ut.append(rad)
    return pd.DataFrame(ut)
