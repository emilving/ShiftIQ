# -*- coding: utf-8 -*-
"""
Vinstchans – Slotlines matchmodell.

Så räknas chansen att vinna:
1. Anfall: gjorda mål (utan tom bur) och förväntade mål (xG). xG väger tyngst,
   eftersom chanserna säger mer om nästa match än vilka skott som råkade gå in.
2. Försvar: chanserna laget släpper till (xG mot). Hur många av dem som går in
   avgörs av målvakten, och räknas för sig (punkt 4).
3. Senare matcher väger mer än tidiga (en match som är HALVERING matcher gammal
   väger hälften). Varje lag dras mot sin nivå från förra säsongen, halvvägs mot
   ligasnittet, med KRYMP "matcher" – så att några matcher i början av säsongen
   inte ger orimliga siffror.
4. Målvakten: hur många mål han släpper in jämfört med chanserna han möter
   (insläppta / xG mot). Dras mot förra säsongens räddningsprocent och mot
   snittet med MV_KRYMP förväntade mål, eftersom målvaktsspel svänger mycket.
   Trolig startare: den som stått flest av lagets senaste 10 matcher. Spelade
   han dagen innan räknas reserven som trolig.
5. Förväntade mål i matchen = eget anfall × motståndarens försvar / ligasnitt
   × motståndarmålvaktens kvot, med fördel för hemmalaget och nackdel för lag
   som spelade dagen innan.
6. Chansen räknas med Poissonfördelningen. Blir det lika efter full tid avgörs
   en del i förlängning (där det bästa anfallet har en liten fördel) och resten
   på straffar (lika chans).

Inställningarna är valda genom att testa på säsongens spelade matcher, där varje
prognos bara får se matcherna innan.
"""

import datetime as dt
import math

import numpy as np
import pandas as pd

LIGASNITT_START = 3.0   # mål per lag och match innan säsongen har gett någon data
HALVERING = 20          # matcher – så gammal är en match när den väger hälften
KRYMP = 6               # antal matcher varje lag dras mot sin utgångsnivå
XG_VIKT = 0.7           # hur mycket xG väger jämfört med riktiga mål i anfallet
FORRA_VIKT = 0.5        # hur mycket av förra säsongens nivå som behålls (resten = ligasnitt)
MV_KRYMP = 50.0         # förväntade mål en målvakt dras mot sin utgångsnivå (ungefär 18 matcher)
MV_FORRA_VIKT = 0.5     # hur mycket av förra säsongens räddningsprocent som behålls
MV_NY = 1.03            # utgångsnivå för målvakt utan NHL-matcher förra säsongen (lite sämre än snittet)
SKARPA = 0.9           # < 1 dämpar de mest extrema matcherna (få matcher in på säsongen gör ytterlägena osäkra)
MV_SENASTE = 10         # så många av lagets senaste matcher avgör vem som är förstemålvakt
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


def forra_niva(forra_lag):
    """Förra säsongens anfall och försvar per lag, som kvot mot ligasnittet."""
    if forra_lag is None or not len(forra_lag) or "Mål/match" not in forra_lag:
        return {}
    lg = forra_lag["Mål/match"].mean()
    if not lg > 0:
        return {}
    return {int(r["Lag-id"]): (1 + FORRA_VIKT * (r["Mål/match"] / lg - 1), 1 + FORRA_VIKT * (r["Insläppta/match"] / lg - 1))
            for _, r in forra_lag.iterrows()}


def styrka(rows: pd.DataFrame, fore: str, forra=None, med_mv=False):
    """Ligasnitt och varje lags anfall/försvar räknat på matcher före datumet `fore`.
    med_mv: försvaret räknas bara på chanser emot, eftersom målvakten räknas för sig."""
    forra = forra or {}
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
            xga = np.average(g["xGA"], weights=w)
            forsvar = xga if med_mv else XG_VIKT * xga + (1 - XG_VIKT) * ga
        else:
            anfall, forsvar = gf, ga
        pa, pf = forra.get(int(tid), (1.0, 1.0))
        lag[tid] = {"anfall": (n * anfall + KRYMP * snitt * pa) / (n + KRYMP),
                    "forsvar": (n * forsvar + KRYMP * snitt * pf) / (n + KRYMP),
                    "matcher": len(g)}
    for tid, (pa, pf) in forra.items():
        if tid not in lag:
            lag[tid] = {"anfall": snitt * pa, "forsvar": snitt * pf, "matcher": 0}
    return snitt, lag


class Malvakter:
    """Målvakternas kvot (insläppta / xG mot) och vem som troligen startar."""

    def __init__(self, GK, forra_mv=None):
        self.ok = GK is not None and len(GK) > 0 and "xG mot" in GK and GK["xG mot"].notna().any()
        self.forra = {}
        if forra_mv is not None and len(forra_mv) and "Skott mot" in forra_mv:
            sv_lg = 1 - forra_mv["Insläppta"].sum() / max(1, forra_mv["Skott mot"].sum())
            for _, r in forra_mv.iterrows():
                if r.get("Skott mot", 0) > 0 and pd.notna(r.get("Räddnings-%")):
                    kvot = (1 - r["Räddnings-%"]) / (1 - sv_lg)
                    self.forra[int(r["Spelar-id"])] = 1 + MV_FORRA_VIKT * (kvot - 1)
        if not self.ok:
            return
        g = GK.copy()
        g["Datum"] = g["Datum"].astype(str)
        g = g[g["xG mot"].notna()]
        self.g = g.sort_values(["Datum", "Match-id"])
        self.namn = dict(zip(g["Spelar-id"], g["Spelare"]))

    def kvot(self, pid, fore):
        if pid is None:
            return 1.0
        start = self.forra.get(int(pid), MV_NY)
        if not self.ok:
            return start
        h = self.g[(self.g["Spelar-id"] == pid) & (self.g["Datum"] < fore)]
        return float((h["Insläppta (xG-skott)"].sum() + MV_KRYMP * start) / (h["xG mot"].sum() + MV_KRYMP))

    def stats(self, pid, fore):
        h = self.g[(self.g["Spelar-id"] == pid) & (self.g["Datum"] < fore)] if self.ok else None
        if h is None or not len(h):
            return {"matcher": 0, "sv": None, "gsax": None}
        sa = h["Skott mot"].sum()
        return {"matcher": int(len(h)), "sv": round(float(1 - h["Insläppta"].sum() / sa), 4) if sa else None,
                "gsax": round(float(h["xG mot"].sum() - h["Insläppta (xG-skott)"].sum()), 2)}

    def troliga(self, lag, fore, spelade_igar):
        """[(id, namn, anledning)] – trolig startare först, sedan reserven."""
        if not self.ok:
            return []
        h = self.g[(self.g["Lag"] == lag) & (self.g["Datum"] < fore)]
        if not len(h):
            return []
        # målvakter som fortfarande spelar för laget: senaste laget per målvakt
        senaste_lag = self.g[self.g["Datum"] < fore].groupby("Spelar-id")["Lag"].last()
        h = h[h["Spelar-id"].map(senaste_lag) == lag]
        if not len(h):
            return []
        matcher = sorted(h["Match-id"].unique(), key=lambda m: h[h["Match-id"] == m]["Datum"].iloc[0])[-MV_SENASTE:]
        st = h[(h["Match-id"].isin(matcher)) & (h["Startade"] == "ja")]
        rank = st.groupby("Spelar-id").agg(n=("Match-id", "size"), sist=("Datum", "max")).reset_index()
        rank = rank.sort_values(["n", "sist"], ascending=False)
        ordning = list(rank["Spelar-id"])
        for pid in h.sort_values("Datum", ascending=False)["Spelar-id"]:
            if pid not in ordning:
                ordning.append(pid)
        ordning = ordning[:2]
        skal = ["flest starter"] + ["reserv"] * (len(ordning) - 1)
        if spelade_igar and len(ordning) == 2:
            igar = h[h["Datum"] == max(h["Datum"])]
            igar_start = igar[igar["Startade"] == "ja"]["Spelar-id"].tolist()
            if igar_start and igar_start[0] == ordning[0]:
                ordning = [ordning[1], ordning[0]]
                skal = ["förstemålvakten spelade igår", "spelade igår"]
        return [(int(pid), self.namn.get(pid, ""), s) for pid, s in zip(ordning, skal)]


def matchup(snitt, lag, hemma, borta, trott_hemma=False, trott_borta=False, mv_hemma=1.0, mv_borta=1.0):
    """mv_hemma/mv_borta: målvaktens kvot (insläppta per förväntat mål) för respektive lag."""
    tom = {"anfall": snitt, "forsvar": snitt, "matcher": 0}
    h, b = lag.get(hemma, tom), lag.get(borta, tom)
    th, tb = (TROTT if trott_hemma else 1.0), (TROTT if trott_borta else 1.0)
    mal_hemma = (h["anfall"] * th) * (b["forsvar"] / tb) / snitt * HEMMA * mv_borta
    mal_borta = (b["anfall"] * tb) * (h["forsvar"] / th) / snitt / HEMMA * mv_hemma
    mal_hemma = snitt * (mal_hemma / snitt) ** SKARPA
    mal_borta = snitt * (mal_borta / snitt) ** SKARPA
    ph, pb = chans(mal_hemma, mal_borta)
    return {"mal_hemma": mal_hemma, "mal_borta": mal_borta, "chans_hemma": ph, "chans_borta": pb,
            "matcher_hemma": h["matcher"], "matcher_borta": b["matcher"]}


def _dagen_fore(datum: str) -> str:
    return (dt.date.fromisoformat(datum) - dt.timedelta(days=1)).isoformat()


def prognoser(T: pd.DataFrame, GK=None, forra_lag=None, forra_mv=None) -> pd.DataFrame:
    """Prognos före varje spelad match, räknad bara på matcher som spelats innan."""
    rows = lagmatcher(T)
    if rows.empty:
        return pd.DataFrame()
    MV = Malvakter(GK, forra_mv)
    forra = forra_niva(forra_lag)
    spelat = set(zip(rows["Lag-id"], rows["Datum"]))
    borta = rows[rows["Hemma/borta"] == "Borta"].set_index("Match-id")
    ut = []
    for datum, dag in rows[rows["Hemma/borta"] == "Hemma"].groupby("Datum"):
        snitt, lag = styrka(rows, datum, forra, MV.ok)
        igar = _dagen_fore(datum)
        for _, h in dag.iterrows():
            if h["Match-id"] not in borta.index:
                continue
            b = borta.loc[h["Match-id"]]
            th, tb = (h["Lag-id"], igar) in spelat, (b["Lag-id"], igar) in spelat
            # samma gissning om målvakt som inför matchen – inte facit
            mh = MV.troliga(h["Lag"], datum, th)
            mb = MV.troliga(b["Lag"], datum, tb)
            kh = MV.kvot(mh[0][0], datum) if mh else 1.0
            kb = MV.kvot(mb[0][0], datum) if mb else 1.0
            m = matchup(snitt, lag, h["Lag-id"], b["Lag-id"], th, tb, kh, kb)
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


def kommande(T: pd.DataFrame, matcher: list, GK=None, forra_lag=None, forra_mv=None) -> pd.DataFrame:
    """Prognos för kommande matcher. `matcher` kommer från NHL:s schema."""
    if not matcher:
        return pd.DataFrame()
    rows = lagmatcher(T)
    MV = Malvakter(GK, forra_mv)
    snitt, lag = styrka(rows, "9999-12-31", forra_niva(forra_lag), MV.ok)
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
        hnamn, bnamn = namn.get(hid, (None,))[0], namn.get(bid, (None,))[0]
        mh = MV.troliga(hnamn, "9999-12-31", th) if hnamn else []
        mb = MV.troliga(bnamn, "9999-12-31", tb) if bnamn else []
        kv = lambda lst, i: MV.kvot(lst[i][0], "9999-12-31") if len(lst) > i else 1.0
        m = matchup(snitt, lag, hid, bid, th, tb, kv(mh, 0), kv(mb, 0))
        rad = {"Match-id": g["id"], "Datum": g["date"], "Start (UTC)": g.get("start", ""), "Status": g.get("state", "")}
        # målvakter: trolig startare och reserv, och chansen om reserven står i stället
        for sida, lst, alt in (("Borta", mb, lambda: matchup(snitt, lag, hid, bid, th, tb, kv(mh, 0), kv(mb, 1))),
                               ("Hemma", mh, lambda: matchup(snitt, lag, hid, bid, th, tb, kv(mh, 1), kv(mb, 0)))):
            for i, (pid, mnamn, varfor) in enumerate(lst[:2], 1):
                st = MV.stats(pid, "9999-12-31")
                rad.update({f"{sida} mv{i}": mnamn, f"{sida} mv{i}-id": pid, f"{sida} mv{i} varför": varfor,
                            f"{sida} mv{i} matcher": st["matcher"], f"{sida} mv{i} rädd%": st["sv"], f"{sida} mv{i} GSAx": st["gsax"],
                            f"{sida} mv{i} kvot": round(kv(lst, i - 1), 3)})
            if len(lst) > 1:
                a = alt()
                rad[f"Chans hemma om {sida.lower()} mv2"] = round(a["chans_hemma"], 4)
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
