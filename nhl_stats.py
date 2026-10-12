#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ShiftIQ – NHL-statistik med Game Score+, hämtad direkt från NHL:s egna data.

Vad skriptet gör
----------------
1. Hämtar säsongens matchschema från NHL och letar upp alla färdigspelade matcher.
2. Hämtar play-by-play, boxscore och byteslistor (shift charts) för varje match.
   Allt sparas i mappen nhl_data/, så varje match hämtas bara en gång.
3. Räknar fram statistik per spelare och match:
   mål, assist (primära/sekundära), poäng, PP/SH-mål, skott, skottförsök, träffar,
   blockeringar, puckvinster/-förluster, tekningar, utvisningar (tagna/dragna),
   istid totalt/5 mot 5/PP/SH, skottförsök och mål på isen vid 5 mot 5 (Corsi, GF/GA),
   egen xG-modell (förväntade mål), Game Score och vår egen Game Score+.
4. Målvakter: skott mot, räddningar, insläppta, räddningsprocent, xG mot och GSAx.
5. Lag: tabell, mål, skott, Corsi%, xG%, PP- och SH-mål samt lagets Game Score.
6. Vinstchans för kommande matcher och hur modellen hade tippat varje spelad match
   (se vinstchans.py).
7. Valfritt (--edge): NHL Edge-data per spelare (skridskofart, skotthastighet,
   åkt sträcka, zontid m.m.) för säsongen.
8. Skriver allt till en Excel-fil (en flik per tabell) och CSV-filer.

Game Score (Dom Luszczyszyn, Hockey Graphs 2016):
  Utespelare = 0.75·G + 0.7·A1 + 0.55·A2 + 0.075·SOG + 0.05·BLK + 0.15·PD − 0.15·PT
               + 0.01·FOW − 0.01·FOL + 0.05·CF − 0.05·CA + 0.15·GF − 0.15·GA
               (CF, CA, GF, GA = på isen vid 5 mot 5)
  Målvakt    = −0.75·GA + 0.1·SV

Game Score+ (vår version): samma formel, men 0.075·SOG byts mot 1.0·ixG och
  0.05·(CF − CA) mot 1.0·(xGF − xGA) vid 5 mot 5. Målvakt: 0.75·GSAx.

Krav
----
Python 3.9 eller senare och paketen:  pip install requests numpy pandas openpyxl

Körning
-------
  python nhl_stats.py                 # uppdatera säsongen 2026/27 och skriv Excel
  python nhl_stats.py --edge          # samma, plus NHL Edge-data per spelare
  python nhl_stats.py --sasong 20252026          # förra säsongen
  python nhl_stats.py --fran 2026-10-01 --till 2026-10-10
  python nhl_stats.py --slutspel      # ta även med slutspelsmatcher

NHL:s datatjänster (api-web.nhle.com och api.nhle.com) är öppna men inte officiellt
dokumenterade, så adresser och fält kan ändras. Skriptet kontrollerar sina egna
siffror mot NHL:s boxscore och varnar om något inte stämmer.
"""

import argparse
import datetime as dt
import gzip
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
    import requests
except ImportError:
    print("Saknar paket. Kör först:  pip install requests numpy pandas openpyxl")
    sys.exit(1)

WEB = "https://api-web.nhle.com/v1"
STATS = "https://api.nhle.com/stats/rest/en"

# Första matchdag per säsong (används som startdatum om --fran inte anges).
SEASON_STARTS = {
    "20252026": "2025-10-07",
    "20262027": "2026-09-29",
}
def current_season(today=None):
    d = today or dt.date.today()
    y = d.year if d.month >= 8 else d.year - 1
    return f"{y}{y + 1}"


DEFAULT_SEASON = current_season()

POSITIONS = {"C": "Center", "L": "Vänsterforward", "R": "Högerforward", "D": "Back", "G": "Målvakt"}
POS_GROUP = {"C": "Forward", "L": "Forward", "R": "Forward", "D": "Back", "G": "Målvakt"}

SHOT_EVENTS = ("goal", "shot-on-goal", "missed-shot", "blocked-shot")
UNBLOCKED = ("goal", "shot-on-goal", "missed-shot")
SHOT_TYPES = ("wrist", "snap", "slap", "backhand", "tip-in", "deflected", "wrap-around")


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Hämtning med cache
# ---------------------------------------------------------------------------

class Fetcher:
    def __init__(self, root: Path, offline=False, pause=0.35):
        self.root = root
        self.offline = offline
        self.pause = pause
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "nhl-gamescore-skript/1.0 (privat statistik)"
        self.requests_made = 0

    @staticmethod
    def _gz(cache: Path):
        return cache.with_name(cache.name + ".gz")

    def forget(self, cache: Path):
        for c in (cache, self._gz(cache)):
            if c.exists():
                c.unlink()

    def get(self, url, cache: Path = None, max_age_s=None):
        """Hämtar JSON. Med cache: läser sparad fil (komprimerad .json.gz) om den finns och inte är för gammal."""
        if cache is not None:
            for c in (self._gz(cache), cache):
                if c.exists():
                    fresh = max_age_s is None or (time.time() - c.stat().st_mtime) < max_age_s
                    if fresh or self.offline:
                        raw = gzip.decompress(c.read_bytes()) if c.suffix == ".gz" else c.read_bytes()
                        return json.loads(raw.decode("utf-8"))
        if self.offline:
            raise RuntimeError(f"Offlineläge och ingen sparad fil för {url}")
        last_err = None
        for attempt in range(5):
            try:
                r = self.session.get(url, timeout=30)
            except requests.RequestException as e:
                last_err = e
                time.sleep(2 ** attempt)
                continue
            self.requests_made += 1
            if r.status_code == 200:
                data = r.json()
                if cache is not None:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    self._gz(cache).write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False).encode("utf-8"), 6))
                    if cache.exists():
                        cache.unlink()
                time.sleep(self.pause)
                return data
            if r.status_code == 404:
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                wait = r.headers.get("Retry-After")
                time.sleep(int(wait) if wait and wait.isdigit() else 2 ** (attempt + 1))
                last_err = f"HTTP {r.status_code}"
                continue
            raise RuntimeError(f"HTTP {r.status_code} från {url}")
        raise RuntimeError(f"Kunde inte hämta {url} ({last_err})")


# ---------------------------------------------------------------------------
# Hjälpfunktioner
# ---------------------------------------------------------------------------

def txt(v):
    """NHL lägger många namn i {'default': '...'}."""
    if isinstance(v, dict):
        return v.get("default") or next((x for x in v.values() if isinstance(x, str)), "")
    return v if isinstance(v, str) else ("" if v is None else str(v))


def mmss(s):
    if not s or ":" not in str(s):
        return None
    m, sec = str(s).split(":")[:2]
    return int(m) * 60 + int(sec)


def parse_situation(code):
    """situationCode '1551' = bortalagets målvakt, bortalagets utespelare, hemmalagets utespelare, hemmalagets målvakt."""
    if not code or len(str(code)) != 4 or not str(code).isdigit():
        return None
    c = str(code)
    return {"away_g": int(c[0]), "away_sk": int(c[1]), "home_sk": int(c[2]), "home_g": int(c[3])}


def team_view(sit, is_home):
    """Läget sett från ett lag: egna utespelare, motståndarens, egen målvakt, motståndarens."""
    if sit is None:
        return None
    if is_home:
        return sit["home_sk"], sit["away_sk"], sit["home_g"], sit["away_g"]
    return sit["away_sk"], sit["home_sk"], sit["away_g"], sit["home_g"]


def game_score_skater(r):
    return (0.75 * r["Mål"] + 0.7 * r["Primära assist"] + 0.55 * r["Sekundära assist"]
            + 0.075 * r["Skott"] + 0.05 * r["Blockeringar"] + 0.15 * r["Dragna utvisningar"]
            - 0.15 * r["Tagna utvisningar"] + 0.01 * r["Vunna tekningar"] - 0.01 * r["Förlorade tekningar"]
            + 0.05 * r["CF 5v5"] - 0.05 * r["CA 5v5"] + 0.15 * r["GF 5v5"] - 0.15 * r["GA 5v5"])


def game_score_goalie(r):
    return -0.75 * r["Insläppta"] + 0.1 * r["Räddningar"]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def logo_url(abbr):
    return f"https://assets.nhle.com/logos/nhl/svg/{abbr}_light.svg" if abbr else ""


def team_info(t):
    t = t or {}
    abbr = t.get("abbrev", "")
    name = f"{txt(t.get('placeName'))} {txt(t.get('commonName'))}".strip() or txt(t.get("name")) or abbr
    return {"id": t.get("id"), "abbr": abbr, "name": name, "logo": t.get("logo") or logo_url(abbr)}


def list_games(f: Fetcher, season, start: dt.date, end: dt.date, game_types):
    today = dt.date.today()
    games = {}
    d = start
    while d <= end:
        week_done = d + dt.timedelta(days=7) < today - dt.timedelta(days=1)
        cache = f.root / "schema" / (f"{d.isoformat()}.json" if week_done else f"{d.isoformat()}_preliminar.json")
        data = f.get(f"{WEB}/schedule/{d.isoformat()}", cache, None if week_done else 3600) or {}
        for week in data.get("gameWeek", []):
            for g in week.get("games", []):
                if str(g.get("season")) != str(season) or g.get("gameType") not in game_types:
                    continue
                gdate = week.get("date") or str(g.get("gameDate", ""))[:10]
                if not (start.isoformat() <= gdate <= end.isoformat()):
                    continue
                games[g["id"]] = {"id": g["id"], "date": gdate, "state": g.get("gameState", ""),
                                  "type": g.get("gameType"), "sched": g.get("gameScheduleState", "OK"),
                                  "start": g.get("startTimeUTC", ""),
                                  "home": team_info(g.get("homeTeam")), "away": team_info(g.get("awayTeam"))}
        nxt = data.get("nextStartDate")
        nd = dt.date.fromisoformat(nxt) if nxt else None
        d = nd if nd and nd > d else d + dt.timedelta(days=7)
    return sorted(games.values(), key=lambda g: (g["date"], g["id"]))


def fetch_game(f: Fetcher, g):
    gid = g["id"]
    final = g["state"] == "OFF"
    age = None if final else 3 * 3600
    base = f.root / "matcher" / str(gid)
    if not final:
        base = base / "preliminar"
    pbp = f.get(f"{WEB}/gamecenter/{gid}/play-by-play", base / "play-by-play.json", age)
    box = f.get(f"{WEB}/gamecenter/{gid}/boxscore", base / "boxscore.json", age)
    shifts_path = base / "byten.json"
    try:
        shifts = f.get(f"{STATS}/shiftcharts?cayenneExp=gameId={gid}", shifts_path, age)
    except Exception:  # noqa: BLE001 – byteslistan är inte nödvändig för grundstatistiken
        shifts = None
    if not shifts or not shifts.get("data"):
        # NHL lägger ibland upp byteslistorna senare – försök igen nästa körning.
        if not f.offline:
            f.forget(shifts_path)
        shifts = None
    return pbp, box, shifts


# ---------------------------------------------------------------------------
# Byteslistor: vilka är på isen, istid per läge
# ---------------------------------------------------------------------------

class OnIce:
    def __init__(self, shifts_json, roster, home_id, away_id):
        self.ok = False
        self.periods = {}
        self.toi = defaultdict(float)
        self.toi_5v5 = defaultdict(float)
        self.toi_pp = defaultdict(float)
        self.toi_sh = defaultdict(float)
        if not shifts_json:
            return
        rows = []
        for s in shifts_json.get("data", []):
            if s.get("typeCode") not in (None, 517) or s.get("eventDescription"):
                continue  # mål-rader m.m., inte byten
            a, b = mmss(s.get("startTime")), mmss(s.get("endTime"))
            pid, per = s.get("playerId"), s.get("period")
            if a is None or b is None or b <= a or pid is None or per is None:
                continue
            team = s.get("teamId") or roster.get(pid, {}).get("team")
            goalie = roster.get(pid, {}).get("pos") == "G"
            rows.append((int(per), pid, team, a, b, goalie))
        if not rows:
            return
        self.ok = True
        by_period = defaultdict(list)
        for r in rows:
            by_period[r[0]].append(r[1:])
        for per, lst in by_period.items():
            pid = np.array([x[0] for x in lst])
            team = np.array([x[1] for x in lst])
            a = np.array([x[2] for x in lst])
            b = np.array([x[3] for x in lst])
            goalie = np.array([x[4] for x in lst])
            self.periods[per] = (pid, team, a, b, goalie)
            L = int(b.max()) + 1
            cnt = {}
            for t in (home_id, away_id):
                sk = np.zeros(L, int)
                gk = np.zeros(L, int)
                for p_, tm, s_, e_, g_ in lst:
                    if tm != t:
                        continue
                    (gk if g_ else sk)[s_:e_] += 1
                cnt[t] = (sk, np.minimum(gk, 1))
            hs, hg = cnt[home_id]
            as_, ag = cnt[away_id]
            both_g = (hg == 1) & (ag == 1)
            m5 = (hs == 5) & (as_ == 5) & both_g
            pp_home = (hs > as_) & both_g
            pp_away = (as_ > hs) & both_g
            for p_, tm, s_, e_, g_ in lst:
                self.toi[p_] += e_ - s_
                self.toi_5v5[p_] += m5[s_:e_].sum()
                own_pp, own_sh = (pp_home, pp_away) if tm == home_id else (pp_away, pp_home)
                self.toi_pp[p_] += own_pp[s_:e_].sum()
                self.toi_sh[p_] += own_sh[s_:e_].sum()

    def at(self, period, sec, faceoff=False):
        """Spelare på isen vid en händelse. Faceoff: nya byten räknas; övrigt: de som avslutar bytet."""
        if period not in self.periods or sec is None:
            return []
        pid, team, a, b, goalie = self.periods[period]
        m = (a <= sec) & (b > sec) if faceoff else (a < sec) & (b >= sec)
        return list(zip(pid[m].tolist(), team[m].tolist(), goalie[m].tolist()))


# ---------------------------------------------------------------------------
# En match
# ---------------------------------------------------------------------------

def blank_skater():
    keys = ["Mål", "Assist", "Primära assist", "Sekundära assist", "PP-mål", "SH-mål", "PP-poäng", "SH-poäng",
            "Mål i tom bur", "Skott", "Skottförsök", "Missade skott", "Egna skott blockerade", "Träffar",
            "Tacklad", "Blockeringar", "Puckvinster", "Puckförluster", "Vunna tekningar", "Förlorade tekningar",
            "Tagna utvisningar", "Dragna utvisningar", "Utvisningsminuter", "CF 5v5", "CA 5v5", "GF 5v5",
            "GA 5v5", "GF på isen", "GA på isen", "ixG", "xGF 5v5", "xGA 5v5"]
    return {k: 0.0 for k in keys}


def blank_goalie():
    keys = ["Skott mot", "Räddningar", "Insläppta", "Skott mot 5v5", "Insläppta 5v5", "xG mot", "Insläppta (xG-skott)"]
    return {k: 0.0 for k in keys}


def parse_game(meta, pbp, box, shifts):
    gid = meta["id"]
    home, away = pbp["homeTeam"], pbp["awayTeam"]
    home_id, away_id = home["id"], away["id"]
    tname = {t["id"]: (f"{txt(t.get('placeName'))} {txt(t.get('commonName'))}".strip() or txt(t.get("name")) or t.get("abbrev"))
             for t in (home, away)}
    tabbr = {t["id"]: t.get("abbrev", "") for t in (home, away)}
    tlogo = {t["id"]: t.get("logo") or logo_url(t.get("abbrev", "")) for t in (home, away)}
    roster = {}
    for r in pbp.get("rosterSpots", []):
        roster[r["playerId"]] = {"name": f"{txt(r.get('firstName'))} {txt(r.get('lastName'))}".strip(),
                                 "team": r.get("teamId"), "pos": r.get("positionCode", ""),
                                 "nr": r.get("sweaterNumber")}
    onice = OnIce(shifts, roster, home_id, away_id)

    last_type = ((pbp.get("gameOutcome") or {}).get("lastPeriodType") or ((box or {}).get("gameOutcome") or {}).get("lastPeriodType")
                 or (pbp.get("periodDescriptor") or {}).get("periodType", "REG"))
    hs, as_ = home.get("score", 0), away.get("score", 0)
    winner = home_id if hs > as_ else away_id

    sk = defaultdict(blank_skater)
    gk = defaultdict(blank_goalie)
    team = {t: defaultdict(float) for t in (home_id, away_id)}
    shots = []

    plays = [p for p in pbp.get("plays", []) if (p.get("periodDescriptor") or {}).get("periodType") != "SO"]

    # Vilket mål anfaller varje lag i varje period? (majoritet av skottens x-koordinat)
    xs = defaultdict(list)
    for p in plays:
        d = p.get("details") or {}
        if p.get("typeDescKey") in ("shot-on-goal", "goal") and d.get("xCoord") is not None:
            tm = d.get("eventOwnerTeamId") or roster.get(d.get("shootingPlayerId") or d.get("scoringPlayerId"), {}).get("team")
            xs[((p.get("periodDescriptor") or {}).get("number"), tm)].append(d["xCoord"])

    def net_x(period, tm, x, play):
        v = xs.get((period, tm))
        if v and abs(np.median(v)) > 5:
            return 89.0 if np.median(v) > 0 else -89.0
        side = play.get("homeTeamDefendingSide")
        if side in ("left", "right"):
            home_att = 89.0 if side == "left" else -89.0
            return home_att if tm == home_id else -home_att
        return 89.0 if (x or 0) >= 0 else -89.0

    prev = None
    for p in plays:
        kind = p.get("typeDescKey")
        d = p.get("details") or {}
        per = (p.get("periodDescriptor") or {}).get("number")
        sec = mmss(p.get("timeInPeriod"))
        sit = parse_situation(p.get("situationCode"))
        five = sit is not None and sit == {"away_g": 1, "away_sk": 5, "home_sk": 5, "home_g": 1}

        if kind in SHOT_EVENTS:
            shooter = d.get("shootingPlayerId") or d.get("scoringPlayerId")
            tm = roster.get(shooter, {}).get("team") if shooter else None
            if tm is None:
                tm = d.get("eventOwnerTeamId")
                if kind == "blocked-shot" and tm in (home_id, away_id) and d.get("blockingPlayerId"):
                    tm = roster.get(d.get("blockingPlayerId"), {}).get("team") == home_id and away_id or home_id
            if tm not in (home_id, away_id):
                prev = p
                continue
            opp = away_id if tm == home_id else home_id
            tv = team_view(sit, tm == home_id)
            own_sk, opp_sk, own_g, opp_g = tv if tv else (5, 5, 1, 1)
            # utespelare utan extra attackerare (målvakt utbytt räknas inte som numerärt överläge)
            own_sk -= 1 if own_g == 0 and own_sk > 0 else 0
            opp_sk -= 1 if opp_g == 0 and opp_sk > 0 else 0
            on = onice.at(per, sec) if onice.ok else []
            on_for = [x[0] for x in on if x[1] == tm and not x[2]]
            on_against = [x[0] for x in on if x[1] == opp and not x[2]]
            goalie = d.get("goalieInNetId")
            if goalie is None and onice.ok:
                goalie = next((x[0] for x in on if x[1] == opp and x[2]), None)
            if opp_g == 0:
                goalie = None

            if shooter:
                sk[shooter]["Skottförsök"] += 1
            T, O = team[tm], team[opp]
            T["Skottförsök"] += 1
            O["Skottförsök mot"] += 1
            if five:
                T["CF 5v5"] += 1
                O["CA 5v5"] += 1
                for q in on_for:
                    sk[q]["CF 5v5"] += 1
                for q in on_against:
                    sk[q]["CA 5v5"] += 1

            if kind == "goal":
                scorer = d.get("scoringPlayerId")
                a1, a2 = d.get("assist1PlayerId"), d.get("assist2PlayerId")
                strength = "PP" if own_sk > opp_sk else ("SH" if own_sk < opp_sk else "EV")
                if scorer:
                    sk[scorer]["Mål"] += 1
                    sk[scorer]["Skott"] += 1
                    if strength == "PP":
                        sk[scorer]["PP-mål"] += 1
                    if strength == "SH":
                        sk[scorer]["SH-mål"] += 1
                    if opp_g == 0:
                        sk[scorer]["Mål i tom bur"] += 1
                for i, a in enumerate((a1, a2)):
                    if a:
                        sk[a]["Assist"] += 1
                        sk[a]["Primära assist" if i == 0 else "Sekundära assist"] += 1
                for q in (scorer, a1, a2):
                    if q and strength == "PP":
                        sk[q]["PP-poäng"] += 1
                    if q and strength == "SH":
                        sk[q]["SH-poäng"] += 1
                T["Mål"] += 1
                O["Insläppta mål"] += 1
                if opp_g == 0:
                    T["Mål i tom bur"] += 1
                T["Skott"] += 1
                O["Skott mot"] += 1
                if strength == "PP":
                    T["PP-mål"] += 1
                if strength == "SH":
                    T["SH-mål"] += 1
                if goalie:
                    gk[goalie]["Skott mot"] += 1
                    gk[goalie]["Insläppta"] += 1
                    if five:
                        gk[goalie]["Skott mot 5v5"] += 1
                        gk[goalie]["Insläppta 5v5"] += 1
                if five:
                    T["GF 5v5"] += 1
                    O["GA 5v5"] += 1
                    for q in on_for:
                        sk[q]["GF 5v5"] += 1
                    for q in on_against:
                        sk[q]["GA 5v5"] += 1
                for q in on_for:
                    sk[q]["GF på isen"] += 1
                for q in on_against:
                    sk[q]["GA på isen"] += 1
            elif kind == "shot-on-goal":
                if shooter:
                    sk[shooter]["Skott"] += 1
                T["Skott"] += 1
                O["Skott mot"] += 1
                if goalie:
                    gk[goalie]["Skott mot"] += 1
                    gk[goalie]["Räddningar"] += 1
                    if five:
                        gk[goalie]["Skott mot 5v5"] += 1
            elif kind == "missed-shot":
                if shooter:
                    sk[shooter]["Missade skott"] += 1
            elif kind == "blocked-shot":
                if shooter:
                    sk[shooter]["Egna skott blockerade"] += 1
                blocker = d.get("blockingPlayerId")
                if blocker and d.get("reason") != "teammate-blocked":
                    sk[blocker]["Blockeringar"] += 1
                    O["Blockeringar"] += 1

            x, y = d.get("xCoord"), d.get("yCoord")
            rec = {"Match-id": gid, "Datum": meta["date"], "Period": per, "Tid": p.get("timeInPeriod"),
                   "Lag": tname[tm], "Motståndare": tname[opp], "Typ": kind, "Skytt-id": shooter,
                   "Skytt": roster.get(shooter, {}).get("name", ""), "Målvakt-id": goalie,
                   "Målvakt": roster.get(goalie, {}).get("name", "") if goalie else "",
                   "Skottyp": d.get("shotType", ""), "Läge": p.get("situationCode", ""),
                   "Egna utespelare": own_sk, "Motståndarens utespelare": opp_sk, "Tom bur": int(opp_g == 0),
                   "5 mot 5": int(five), "Mål": int(kind == "goal"), "x": x, "y": y,
                   "Avstånd (fot)": None, "Vinkel (grader)": None, "Retur": 0, "Rush": 0,
                   "_for": on_for, "_against": on_against, "_team": tm, "_opp": opp}
            if x is not None and y is not None:
                nx = net_x(per, tm, x, p)
                dx = (nx - x) if nx > 0 else (x - nx)
                rec["Avstånd (fot)"] = round(math.hypot(nx - x, y), 1)
                rec["Vinkel (grader)"] = round(math.degrees(math.atan2(abs(y), dx)), 1)
            if prev is not None and (prev.get("periodDescriptor") or {}).get("number") == per:
                ps = mmss(prev.get("timeInPeriod"))
                pd_ = prev.get("details") or {}
                if ps is not None and sec is not None:
                    gap = sec - ps
                    prev_team = roster.get(pd_.get("shootingPlayerId") or pd_.get("scoringPlayerId"), {}).get("team")
                    if prev.get("typeDescKey") in SHOT_EVENTS and gap <= 3 and prev_team == tm:
                        rec["Retur"] = 1
                    if gap <= 4 and x is not None and pd_.get("xCoord") is not None and abs(pd_["xCoord"] - x) >= 50:
                        rec["Rush"] = 1
            shots.append(rec)

        elif kind == "hit":
            if d.get("hittingPlayerId"):
                sk[d["hittingPlayerId"]]["Träffar"] += 1
                tm = roster.get(d["hittingPlayerId"], {}).get("team")
                if tm in team:
                    team[tm]["Träffar"] += 1
            if d.get("hitteePlayerId"):
                sk[d["hitteePlayerId"]]["Tacklad"] += 1
        elif kind == "giveaway" and d.get("playerId"):
            sk[d["playerId"]]["Puckförluster"] += 1
        elif kind == "takeaway" and d.get("playerId"):
            sk[d["playerId"]]["Puckvinster"] += 1
        elif kind == "faceoff":
            w, l_ = d.get("winningPlayerId"), d.get("losingPlayerId")
            if w:
                sk[w]["Vunna tekningar"] += 1
                tm = roster.get(w, {}).get("team")
                if tm in team:
                    team[tm]["Vunna tekningar"] += 1
            if l_:
                sk[l_]["Förlorade tekningar"] += 1
                tm = roster.get(l_, {}).get("team")
                if tm in team:
                    team[tm]["Förlorade tekningar"] += 1
        elif kind == "penalty":
            code = str(d.get("typeCode", "")).upper()
            desc = str(d.get("descKey", "")).lower()
            counts = code not in ("MIS", "GMIS") and "misconduct" not in desc
            who = d.get("committedByPlayerId")
            if who:
                sk[who]["Utvisningsminuter"] += d.get("duration") or 0
                if counts:
                    sk[who]["Tagna utvisningar"] += 1
            if d.get("drawnByPlayerId") and counts:
                sk[d["drawnByPlayerId"]]["Dragna utvisningar"] += 1
            tm = roster.get(who, {}).get("team") if who else d.get("eventOwnerTeamId")
            if tm in team:
                team[tm]["Utvisningsminuter"] += d.get("duration") or 0
                if counts:
                    team[tm]["Utvisningar"] += 1
        if kind not in ("stoppage", "period-start", "period-end", "game-end", "delayed-penalty"):
            prev = p

    # --- boxscore: istid, plus/minus, kontroll ---
    box_players = {}
    pbg = (box or {}).get("playerByGameStats") or {}
    for side in ("homeTeam", "awayTeam"):
        for grp in ("forwards", "defense", "goalies"):
            for b in pbg.get(side, {}).get(grp, []) or []:
                box_players[b.get("playerId")] = b

    played = set(sk) | set(gk) | set(box_players) | set(onice.toi)
    checks = []
    rows, grows = [], []
    for pid in played:
        info = roster.get(pid)
        if not info:
            b = box_players.get(pid, {})
            info = {"name": txt(b.get("name")), "team": None, "pos": b.get("position", ""), "nr": b.get("sweaterNumber")}
            if info["team"] is None:
                for side, tid in (("homeTeam", home_id), ("awayTeam", away_id)):
                    if any(x.get("playerId") == pid for g_ in ("forwards", "defense", "goalies") for x in pbg.get(side, {}).get(g_, []) or []):
                        info["team"] = tid
        tm = info["team"]
        if tm not in (home_id, away_id):
            continue
        opp = away_id if tm == home_id else home_id
        b = box_players.get(pid, {})
        toi = onice.toi.get(pid, 0) / 60 if onice.ok else (mmss(b.get("toi")) or 0) / 60
        if toi == 0 and pid not in sk and pid not in gk:
            continue  # klädd men spelade inte (t.ex. reservmålvakt)
        result = "V" if tm == winner else ("FÖ" if last_type in ("OT", "SO") else "F")
        base = {"Match-id": gid, "Datum": meta["date"], "Spelar-id": pid, "Spelare": info["name"],
                "Nummer": info["nr"], "Lag": tname[tm], "Lagförkortning": tabbr[tm], "Motståndare": tname[opp],
                "Hemma/borta": "Hemma" if tm == home_id else "Borta", "Resultat": result,
                "Mål för": hs if tm == home_id else as_, "Mål mot": as_ if tm == home_id else hs,
                "Avgjord i": {"REG": "Ordinarie", "OT": "Förlängning", "SO": "Straffar"}.get(last_type, last_type),
                "Istid (min)": round(toi, 2), "Byteslista": "ja" if onice.ok else "saknas"}
        if info["pos"] == "G":
            g = gk[pid] if pid in gk else blank_goalie()
            r = {**base, "Position": "Målvakt", **g,
                 "Startade": "ja" if b.get("starter") else ("nej" if b else ""),
                 "Beslut": {"W": "Vinst", "L": "Förlust", "O": "Förlust (förl./str.)"}.get(b.get("decision"), "")}
            r["Räddnings-%"] = round(r["Räddningar"] / r["Skott mot"], 3) if r["Skott mot"] else None
            r["Game Score"] = round(game_score_goalie(r), 3)
            grows.append(r)
        else:
            s = sk[pid] if pid in sk else blank_skater()
            r = {**base, "Position": POSITIONS.get(info["pos"], info["pos"]), "Positionsgrupp": POS_GROUP.get(info["pos"], ""),
                 **s, "Poäng": s["Mål"] + s["Assist"],
                 "Istid 5v5 (min)": round(onice.toi_5v5.get(pid, 0) / 60, 2) if onice.ok else None,
                 "Istid PP (min)": round(onice.toi_pp.get(pid, 0) / 60, 2) if onice.ok else None,
                 "Istid SH (min)": round(onice.toi_sh.get(pid, 0) / 60, 2) if onice.ok else None,
                 "Byten": b.get("shifts"), "Plus/minus": b.get("plusMinus")}
            r["Game Score"] = round(game_score_skater(r), 3)
            rows.append(r)
            if b:
                for ours, theirs in (("Mål", "goals"), ("Assist", "assists"), ("Skott", "sog")):
                    if b.get(theirs) is not None and int(b[theirs]) != int(r[ours]):
                        checks.append(f"{info['name']} {ours}: vi {int(r[ours])}, NHL {b[theirs]}")

    # lagets match
    trows = []
    for tm in (home_id, away_id):
        opp = away_id if tm == home_id else home_id
        T = team[tm]
        result = "V" if tm == winner else ("FÖ" if last_type in ("OT", "SO") else "F")
        trows.append({"Match-id": gid, "Datum": meta["date"], "Lag": tname[tm], "Lagförkortning": tabbr[tm],
                      "Motståndare": tname[opp], "Hemma/borta": "Hemma" if tm == home_id else "Borta",
                      "Resultat": result, "Mål för": hs if tm == home_id else as_, "Mål mot": as_ if tm == home_id else hs,
                      "Avgjord i": {"REG": "Ordinarie", "OT": "Förlängning", "SO": "Straffar"}.get(last_type, last_type),
                      "Skott": T["Skott"], "Skott mot": T["Skott mot"], "Skottförsök": T["Skottförsök"],
                      "Skottförsök mot": T["Skottförsök mot"], "CF 5v5": T["CF 5v5"], "CA 5v5": T["CA 5v5"],
                      "GF 5v5": T["GF 5v5"], "GA 5v5": T["GA 5v5"], "PP-mål": T["PP-mål"], "SH-mål": T["SH-mål"],
                      "Träffar": T["Träffar"], "Blockeringar": T["Blockeringar"], "Utvisningar": T["Utvisningar"],
                      "Utvisningsminuter": T["Utvisningsminuter"], "Vunna tekningar": T["Vunna tekningar"],
                      "Förlorade tekningar": T["Förlorade tekningar"], "_id": tm, "Lag-id": tm, "Logga": tlogo[tm],
                      "Mål (ej tom bur)": T["Mål"] - T["Mål i tom bur"],
                      "Insläppta (ej tom bur)": team[opp]["Mål"] - team[opp]["Mål i tom bur"]})
    # kontroll: mål i play-by-play mot slutresultatet (straffmål räknas inte i play-by-play här)
    for tr in trows:
        goals_pbp = team[tr["_id"]]["Mål"]
        shootout_bonus = 1 if (last_type == "SO" and tr["Resultat"] == "V") else 0
        if goals_pbp + shootout_bonus != tr["Mål för"]:
            checks.append(f"{tr['Lag']}: {int(goals_pbp)} mål i händelselistan men {tr['Mål för']} i resultatet")
    return rows, grows, trows, shots, checks


# ---------------------------------------------------------------------------
# xG-modell (logistisk regression, tränas på säsongens egna skott)
# ---------------------------------------------------------------------------

def xg_features(df):
    d = df["Avstånd (fot)"].astype(float)
    a = df["Vinkel (grader)"].astype(float)
    X = {"avst": d, "avst2": d ** 2, "logavst": np.log1p(d), "vinkel": a, "vinkel2": a ** 2,
         "retur": df["Retur"].astype(float), "rush": df["Rush"].astype(float),
         "pp": (df["Egna utespelare"] > df["Motståndarens utespelare"]).astype(float),
         "sh": (df["Egna utespelare"] < df["Motståndarens utespelare"]).astype(float)}
    st = df["Skottyp"].fillna("").str.lower()
    for t in SHOT_TYPES:
        X["typ_" + t] = (st == t).astype(float)
    return pd.DataFrame(X)


def fit_xg(shots: pd.DataFrame):
    train = shots[shots["Typ"].isin(UNBLOCKED) & (shots["Tom bur"] == 0) & shots["Avstånd (fot)"].notna()]
    if len(train) < 3000:
        log(f"  För få skott ({len(train)}) för en pålitlig xG-modell – xG hoppas över tills fler matcher spelats.")
        return None
    F = xg_features(train)
    mu, sd = F.mean(), F.std().replace(0, 1)
    X = np.column_stack([np.ones(len(F)), ((F - mu) / sd).to_numpy()])
    y = train["Mål"].to_numpy(float)
    w = np.zeros(X.shape[1])
    lam = 1.0
    for _ in range(50):
        p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
        W = p * (1 - p)
        reg = lam * w
        reg[0] = 0
        g = X.T @ (y - p) - reg
        H = (X.T * W) @ X + lam * np.eye(X.shape[1])
        H[0, 0] -= lam
        step = np.linalg.solve(H, g)
        w += step
        if np.abs(step).max() < 1e-7:
            break
    p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
    log(f"  xG-modell tränad på {len(train)} skott: {int(y.sum())} mål, {p.sum():.1f} förväntade.")
    return {"w": w, "mu": mu, "sd": sd}


def apply_xg(model, shots: pd.DataFrame):
    xg = np.full(len(shots), np.nan)
    mask = shots["Typ"].isin(UNBLOCKED).to_numpy() & (shots["Tom bur"] == 0).to_numpy() & shots["Avstånd (fot)"].notna().to_numpy()
    if model is not None and mask.any():
        F = xg_features(shots[mask])
        X = np.column_stack([np.ones(len(F)), ((F - model["mu"]) / model["sd"]).to_numpy()])
        xg[mask] = 1 / (1 + np.exp(-np.clip(X @ model["w"], -30, 30)))
    return xg


# ---------------------------------------------------------------------------
# NHL Edge
# ---------------------------------------------------------------------------

def flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if "imperial" in kl or "headshot" in kl or "url" in kl or "logo" in kl:
                continue
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        if len(obj) <= 5 and all(not isinstance(v, (dict, list)) for v in obj):
            for i, v in enumerate(obj):
                out[f"{prefix}[{i}]"] = v
        elif len(obj) <= 10 and all(isinstance(v, dict) for v in obj):
            for i, v in enumerate(obj):
                out.update(flatten(v, f"{prefix}[{i}]"))
    elif isinstance(obj, (int, float, str, bool)) or obj is None:
        out[prefix] = obj
    return out


def fetch_edge(f: Fetcher, season, players: pd.DataFrame, game_type=2):
    today = dt.date.today().isoformat()
    sk_rows, g_rows, failed = [], [], []
    total = len(players)
    for i, (_, p) in enumerate(players.iterrows(), 1):
        kind = "goalie" if p["Position"] == "Målvakt" else "skater"
        cache = f.root / "edge" / today / f"{kind}_{p['Spelar-id']}.json"
        try:
            data = f.get(f"{WEB}/edge/{kind}-detail/{p['Spelar-id']}/{season}/{game_type}", cache)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{p['Spelare']}: {e}")
            if len(failed) >= 25 and not sk_rows and not g_rows:
                log("  Edge-hämtningen misslyckas för alla spelare – avbryter. Första felet: " + failed[0])
                break
            continue
        if i % 50 == 0 or i == total:
            log(f"  Edge: {i}/{total} spelare")
        if not data:
            continue
        flat = flatten(data)
        flat = {k: v for k, v in flat.items()
                if not (isinstance(v, str) and len(v) > 40) and not k.startswith(("player.", "seasonsWithEdgeStats"))}
        row = {"Spelar-id": p["Spelar-id"], "Spelare": p["Spelare"], "Lag": p["Lag"], "Position": p["Position"], **flat}
        (g_rows if kind == "goalie" else sk_rows).append(row)
    if failed:
        log(f"  Edge saknas för {len(failed)} spelare (t.ex. {failed[0]}).")
    return pd.DataFrame(sk_rows), pd.DataFrame(g_rows)


# ---------------------------------------------------------------------------
# Sammanställning
# ---------------------------------------------------------------------------

def per60(num, minutes):
    return np.where(minutes > 0, num / minutes * 60, np.nan)


def pct(a, b):
    tot = a + b
    return np.where(tot > 0, a / tot, np.nan)


def season_tables(per_game: pd.DataFrame, goalies: pd.DataFrame, teams: pd.DataFrame):
    sum_cols = [c for c in per_game.columns if c in blank_skater() or c in ("Poäng", "Game Score", "Game Score+", "Istid (min)",
                                                                             "Istid 5v5 (min)", "Istid PP (min)",
                                                                             "Istid SH (min)", "Plus/minus")]
    grp = per_game.groupby(["Spelar-id", "Spelare", "Lag", "Position", "Positionsgrupp"], dropna=False)
    S = grp[sum_cols].sum(min_count=1).reset_index()
    S.insert(5, "Matcher", grp.size().values)
    gs = grp["Game Score"]
    S["Game Score snitt"] = (S["Game Score"] / S["Matcher"]).round(3)
    S["Game Score bästa"] = gs.max().values
    S["Game Score sämsta"] = gs.min().values
    gp = grp["Game Score+"]
    S["Game Score+ snitt"] = (S["Game Score+"] / S["Matcher"]).round(3)
    S["Game Score+ bästa"] = gp.max().values
    S["Game Score+ sämsta"] = gp.min().values
    S["Istid/match"] = (S["Istid (min)"] / S["Matcher"]).round(2)
    S["Poäng/60"] = per60(S["Poäng"], S["Istid (min)"]).round(2)
    S["Mål/60"] = per60(S["Mål"], S["Istid (min)"]).round(2)
    S["Skott/60"] = per60(S["Skott"], S["Istid (min)"]).round(2)
    S["Skott-%"] = np.where(S["Skott"] > 0, S["Mål"] / S["Skott"], np.nan).round(3)
    S["Tekning-%"] = pct(S["Vunna tekningar"], S["Förlorade tekningar"]).round(3)
    S["CF% 5v5"] = pct(S["CF 5v5"], S["CA 5v5"]).round(3)
    S["GF% 5v5"] = pct(S["GF 5v5"], S["GA 5v5"]).round(3)
    S["xGF% 5v5"] = pct(S["xGF 5v5"], S["xGA 5v5"]).round(3)
    S["CF/60 5v5"] = per60(S["CF 5v5"], S["Istid 5v5 (min)"]).round(2)
    S["CA/60 5v5"] = per60(S["CA 5v5"], S["Istid 5v5 (min)"]).round(2)
    S["Mål över xG"] = (S["Mål"] - S["ixG"]).round(2)
    S["Utvisningsnetto"] = S["Dragna utvisningar"] - S["Tagna utvisningar"]
    S = S.sort_values("Game Score", ascending=False)

    G = None
    if len(goalies):
        gg = goalies.groupby(["Spelar-id", "Spelare", "Lag"], dropna=False)
        gcols = ["Skott mot", "Räddningar", "Insläppta", "Skott mot 5v5", "Insläppta 5v5", "xG mot",
                 "Insläppta (xG-skott)", "Istid (min)", "Game Score", "Game Score+"]
        G = gg[gcols].sum(min_count=1).reset_index()
        G.insert(3, "Matcher", gg.size().values)
        G.insert(4, "Starter", gg["Startade"].apply(lambda s: (s == "ja").sum()).values)
        G.insert(5, "Vinster", gg["Beslut"].apply(lambda s: (s == "Vinst").sum()).values)
        G["Räddnings-%"] = np.where(G["Skott mot"] > 0, G["Räddningar"] / G["Skott mot"], np.nan).round(3)
        G["Räddnings-% 5v5"] = np.where(G["Skott mot 5v5"] > 0, 1 - G["Insläppta 5v5"] / G["Skott mot 5v5"], np.nan).round(3)
        G["Insläppta/60"] = per60(G["Insläppta"], G["Istid (min)"]).round(2)
        G["GSAx"] = (G["xG mot"] - G["Insläppta (xG-skott)"]).round(2)
        G["Game Score snitt"] = (G["Game Score"] / G["Matcher"]).round(3)
        G["Game Score bästa"] = gg["Game Score"].max().values
        G["Game Score+ snitt"] = (G["Game Score+"] / G["Matcher"]).round(3)
        G["Game Score+ bästa"] = gg["Game Score+"].max().values
        G = G.sort_values("Game Score", ascending=False)

    tg = teams.groupby("Lag")
    L = tg[["Mål för", "Mål mot", "Skott", "Skott mot", "Skottförsök", "Skottförsök mot", "CF 5v5", "CA 5v5",
            "GF 5v5", "GA 5v5", "xGF 5v5", "xGA 5v5", "PP-mål", "SH-mål", "Träffar", "Blockeringar",
            "Utvisningar", "Utvisningsminuter", "Vunna tekningar", "Förlorade tekningar", "Lagets Game Score",
            "Lagets Game Score+"]].sum(min_count=1).reset_index()
    L.insert(1, "Matcher", tg.size().values)
    L.insert(2, "V", tg["Resultat"].apply(lambda s: (s == "V").sum()).values)
    L.insert(3, "F", tg["Resultat"].apply(lambda s: (s == "F").sum()).values)
    L.insert(4, "FÖ", tg["Resultat"].apply(lambda s: (s == "FÖ").sum()).values)
    L.insert(5, "Poäng", 2 * L["V"] + L["FÖ"])
    L.insert(6, "Poäng-%", (L["Poäng"] / (2 * L["Matcher"])).round(3))
    L["Målskillnad"] = L["Mål för"] - L["Mål mot"]
    L["Skott-%"] = np.where(L["Skott"] > 0, L["Mål för"] / L["Skott"], np.nan).round(3)
    L["Räddnings-%"] = np.where(L["Skott mot"] > 0, 1 - L["Mål mot"] / L["Skott mot"], np.nan).round(3)
    L["PDO"] = (L["Skott-%"] + L["Räddnings-%"]).round(3)
    L["CF% 5v5"] = pct(L["CF 5v5"], L["CA 5v5"]).round(3)
    L["GF% 5v5"] = pct(L["GF 5v5"], L["GA 5v5"]).round(3)
    L["xGF% 5v5"] = pct(L["xGF 5v5"], L["xGA 5v5"]).round(3)
    L["Tekning-%"] = pct(L["Vunna tekningar"], L["Förlorade tekningar"]).round(3)
    L["Game Score/match"] = (L["Lagets Game Score"] / L["Matcher"]).round(2)
    L["Game Score+/match"] = (L["Lagets Game Score+"] / L["Matcher"]).round(2)
    L = L.sort_values(["Poäng", "Poäng-%", "Målskillnad"], ascending=False)
    return S, G, L


ABOUT = [
    ("Källa", "NHL:s öppna datatjänster: api-web.nhle.com (schema, play-by-play, boxscore, Edge) och api.nhle.com (byteslistor)."),
    ("Game Score", "Dom Luszczyszyns formel från 2016 (Hockey Graphs). Utespelare: 0.75·Mål + 0.7·Primär assist + 0.55·Sekundär assist + 0.075·Skott + 0.05·Blockeringar + 0.15·Dragna utvisningar − 0.15·Tagna utvisningar + 0.01·Vunna tekningar − 0.01·Förlorade tekningar + 0.05·CF − 0.05·CA + 0.15·GF − 0.15·GA (CF/CA/GF/GA på isen vid 5 mot 5). Målvakt: −0.75·Insläppta + 0.1·Räddningar."),
    ("Game Score+", "Vår vidareutveckling av Game Score. Samma vikter för mål, assist, blockeringar, utvisningar, tekningar och mål på isen, men två delar byts mot mått på chansernas kvalitet: 0.075·Skott blir 1.0·ixG (spelarens egna förväntade mål) och 0.05·(CF − CA) blir 1.0·(xGF − xGA) på isen vid 5 mot 5. Ett skott från blå linjen väger då mindre än ett friläge. Målvakter: 0.75·GSAx (räddade mål över förväntan), så att en målvakt bedöms mot hur svåra skotten var i stället för hur många de var. Noll är en normal målvaktsinsats."),
    ("Vinstchans", "Prognos före varje match. Lagens anfall och försvar räknas fram ur säsongens mål och förväntade mål (xG väger 65 %), där senare matcher väger mer och varje lag dras mot ligasnittet med 8 snittmatcher. Förväntade mål i matchen = anfall × motståndarens försvar / ligasnitt, med 5 % fördel för hemmalaget och 3 % nackdel för lag som spelade dagen innan. Chansen räknas med Poissonfördelning; vid lika efter full tid avgörs 60 % i förlängning och resten på straffar. Fliken Prognoser visar hur modellen hade tippat varje spelad match, räknat bara på matcherna innan."),
    ("Skiljer sig från korten", "HockeyStatCards använder Luszczyszyns nyare modell med xG och justering för med- och motspelare. Den är inte offentlig, så värdena här blir inte identiska med korten."),
    ("CF / CA", "Skottförsök (mål, skott på mål, missar, blockerade) för och mot laget medan spelaren var på isen vid 5 mot 5."),
    ("GF / GA", "Mål för och mot medan spelaren var på isen vid 5 mot 5."),
    ("xG", "Egen modell (logistisk regression) tränad på säsongens oblockerade skott: avstånd, vinkel, skottyp, retur, rush och numerärt läge. Skott mot tom bur ingår inte."),
    ("ixG / xGF / xGA", "ixG = spelarens egna förväntade mål. xGF/xGA = förväntade mål för/mot på isen vid 5 mot 5."),
    ("GSAx", "Räddade mål över förväntan för målvakter: xG mot minus insläppta på samma skott. Plus är bra."),
    ("Istid", "Räknad från NHL:s byteslistor. 5v5 = båda lagen fem utespelare och målvakt. PP/SH = numerärt över-/underläge."),
    ("Resultat", "V = vinst, F = förlust i ordinarie tid, FÖ = förlust efter förlängning eller straffar (ger 1 poäng)."),
    ("Straffläggning", "Straffar räknas inte i någon statistik, bara i resultatet."),
    ("Byteslista saknas", "Om NHL inte lagt upp byteslistan räknas inte CF/CA/GF/GA, xGF/xGA eller istid per läge för den matchen. Skriptet försöker igen nästa körning."),
    ("NHL Edge", "Säsongsdata per spelare (med --edge). Fältnamnen kommer direkt från NHL. Mått i imperial-enheter är bortplockade, metriska finns kvar."),
]


def write_outputs(out_dir: Path, season, tables: dict, excel=True):
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_dir = out_dir / "csv"
    csv_dir.mkdir(exist_ok=True)
    xlsx = out_dir / f"ShiftIQ_{season[:4]}-{season[6:]}.xlsx"
    for name, df in tables.items():
        if df is not None and len(df):
            df.to_csv(csv_dir / f"{name}.csv", index=False, encoding="utf-8-sig")
        elif (csv_dir / f"{name}.csv").exists():
            (csv_dir / f"{name}.csv").unlink()  # inga gamla prognoser kvar när det inte finns kommande matcher
    if not excel:
        return None
    try:
        with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
            for name, df in tables.items():
                if df is None or not len(df):
                    continue
                df.to_excel(xw, sheet_name=name[:31], index=False)
                ws = xw.sheets[name[:31]]
                ws.freeze_panes = "C2" if "Spelare" in df.columns else "B2"
                ws.auto_filter.ref = ws.dimensions
                from openpyxl.styles import Font
                for c in ws[1]:
                    c.font = Font(bold=True)
                for i, col in enumerate(df.columns, 1):
                    sample = df[col].astype(str).head(200).str.len().max() if len(df) else 0
                    sample = 0 if sample is None or pd.isna(sample) else int(sample)
                    width = min(max(len(str(col)), sample) + 2, 40)
                    ws.column_dimensions[ws.cell(1, i).column_letter].width = width
            pd.DataFrame(ABOUT, columns=["Begrepp", "Förklaring"]).to_excel(xw, sheet_name="Om", index=False)
            ws = xw.sheets["Om"]
            ws.column_dimensions["A"].width = 22
            ws.column_dimensions["B"].width = 120
    except PermissionError:
        log(f"Kunde inte skriva {xlsx.name} – är filen öppen i Excel? Stäng den och kör igen. CSV-filerna är uppdaterade.")
        return None
    return xlsx


# ---------------------------------------------------------------------------
# Huvudprogram
# ---------------------------------------------------------------------------

def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="NHL-statistik med Game Score direkt från NHL.")
    ap.add_argument("--sasong", default=DEFAULT_SEASON, help="t.ex. 20262027 (standard)")
    ap.add_argument("--fran", help="första datum, ÅÅÅÅ-MM-DD (standard: säsongsstart)")
    ap.add_argument("--till", help="sista datum, ÅÅÅÅ-MM-DD (standard: i dag)")
    ap.add_argument("--slutspel", action="store_true", help="ta även med slutspelsmatcher")
    ap.add_argument("--edge", action="store_true", help="hämta NHL Edge-data per spelare (tar några minuter)")
    ap.add_argument("--mapp", default=None, help="mapp för data och resultat (standard: nhl_data bredvid skriptet)")
    ap.add_argument("--offline", action="store_true", help="använd bara redan sparad data")
    ap.add_argument("--utan-excel", action="store_true", help="skriv bara CSV-filer (snabbare)")
    a = ap.parse_args(argv)

    root = Path(a.mapp) if a.mapp else Path(__file__).resolve().parent / "nhl_data"
    season = a.sasong
    if len(season) != 8 or not season.isdigit():
        sys.exit("--sasong ska se ut som 20262027")
    start = dt.date.fromisoformat(a.fran) if a.fran else dt.date.fromisoformat(
        SEASON_STARTS.get(season, f"{season[:4]}-09-20"))
    end = dt.date.fromisoformat(a.till) if a.till else dt.date.today()
    f = Fetcher(root / season / "radata", offline=a.offline)
    types = (2, 3) if a.slutspel else (2,)

    today = dt.date.today()
    sched_end = max(end, today + dt.timedelta(days=7)) if end >= today - dt.timedelta(days=1) else end
    log(f"Säsong {season[:4]}/{season[6:]}: hämtar matchschema {start} – {sched_end} …")
    try:
        games = list_games(f, season, start, sched_end, types)
    except Exception as e:  # noqa: BLE001
        log(f"Kunde inte hämta matchschemat från NHL: {e}")
        log("Kontrollera internetanslutningen och försök igen om en stund.")
        sys.exit(1)
    done = [g for g in games if g["state"] in ("OFF", "FINAL") and g["date"] <= end.isoformat()]
    upcoming = [g for g in games if g["state"] in ("FUT", "PRE") and g.get("sched", "OK") == "OK"
                and g["date"] >= today.isoformat() and g["home"]["id"] and g["away"]["id"]]
    log(f"  {len(done)} färdigspelade och {len(upcoming)} kommande matcher hittades.")
    if not done:
        log("Inga färdigspelade matcher ännu.")
        return

    per_game, goalies, teams, shots, problems = [], [], [], [], []
    for i, g in enumerate(done, 1):
        try:
            pbp, box, shifts = fetch_game(f, g)
            if not pbp:
                problems.append(f"Match {g['id']}: ingen play-by-play")
                continue
            r, gr, tr, sh, checks = parse_game(g, pbp, box, shifts)
            per_game += r
            goalies += gr
            teams += tr
            shots += sh
            for c in checks:
                problems.append(f"Match {g['id']} ({g['date']}): {c}")
        except Exception as e:  # noqa: BLE001
            problems.append(f"Match {g['id']} ({g['date']}): kunde inte tolkas – {type(e).__name__}: {e}")
        if i % 25 == 0 or i == len(done):
            log(f"  Läst {i}/{len(done)} matcher ({f.requests_made} nya hämtningar)")

    if not per_game:
        log("Ingen statistik kunde räknas fram. Se problemen nedan.")
        for p in problems[:20]:
            log("  - " + p)
        return

    P = pd.DataFrame(per_game)
    GK = pd.DataFrame(goalies)
    T = pd.DataFrame(teams)
    SH = pd.DataFrame(shots)

    log("Tränar xG-modell …")
    model = fit_xg(SH) if len(SH) else None
    SH["xG"] = apply_xg(model, SH) if len(SH) else []
    # fördela xG på spelare, målvakter och lag
    if model is not None:
        ixg = defaultdict(float)
        xgf, xga = defaultdict(float), defaultdict(float)
        gxa, gga = defaultdict(float), defaultdict(float)
        txf, txa = defaultdict(float), defaultdict(float)
        taf, taa = defaultdict(float), defaultdict(float)
        for rec in SH.itertuples(index=False):
            v = getattr(rec, "xG")
            if v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            gid = rec[SH.columns.get_loc("Match-id")]
            shooter = rec[SH.columns.get_loc("Skytt-id")]
            goalie = rec[SH.columns.get_loc("Målvakt-id")]
            goal = rec[SH.columns.get_loc("Mål")]
            taf[(gid, rec[SH.columns.get_loc("_team")])] += v
            taa[(gid, rec[SH.columns.get_loc("_opp")])] += v
            if shooter:
                ixg[(gid, shooter)] += v
            if goalie:
                gxa[(gid, goalie)] += v
                gga[(gid, goalie)] += goal
            if rec[SH.columns.get_loc("5 mot 5")]:
                for q in rec[SH.columns.get_loc("_for")]:
                    xgf[(gid, q)] += v
                for q in rec[SH.columns.get_loc("_against")]:
                    xga[(gid, q)] += v
                txf[(gid, rec[SH.columns.get_loc("_team")])] += v
                txa[(gid, rec[SH.columns.get_loc("_opp")])] += v
        keys = list(zip(P["Match-id"], P["Spelar-id"]))
        P["ixG"] = [round(ixg.get(k, 0), 3) for k in keys]
        P["xGF 5v5"] = [round(xgf.get(k, 0), 3) for k in keys]
        P["xGA 5v5"] = [round(xga.get(k, 0), 3) for k in keys]
        if len(GK):
            gkeys = list(zip(GK["Match-id"], GK["Spelar-id"]))
            GK["xG mot"] = [round(gxa.get(k, 0), 3) for k in gkeys]
            GK["Insläppta (xG-skott)"] = [gga.get(k, 0) for k in gkeys]
            GK["GSAx"] = (GK["xG mot"] - GK["Insläppta (xG-skott)"]).round(3)
        tkeys = list(zip(T["Match-id"], T["_id"]))
        T["xGF 5v5"] = [round(txf.get(k, 0), 3) for k in tkeys]
        T["xGA 5v5"] = [round(txa.get(k, 0), 3) for k in tkeys]
        T["xGF"] = [round(taf.get(k, 0), 3) for k in tkeys]
        T["xGA"] = [round(taa.get(k, 0), 3) for k in tkeys]
    else:
        P[["ixG", "xGF 5v5", "xGA 5v5"]] = np.nan
        if len(GK):
            GK[["xG mot", "Insläppta (xG-skott)"]] = np.nan
            GK["GSAx"] = np.nan
        T["xGF 5v5"] = np.nan
        T["xGA 5v5"] = np.nan
        T["xGF"] = np.nan
        T["xGA"] = np.nan

    # Game Score+ (vår formel): xG i stället för skott- och Corsi-termerna, GSAx för målvakter
    if model is not None:
        P["Game Score+"] = (0.75 * P["Mål"] + 0.7 * P["Primära assist"] + 0.55 * P["Sekundära assist"]
                            + 1.0 * P["ixG"] + 0.05 * P["Blockeringar"] + 0.15 * P["Dragna utvisningar"]
                            - 0.15 * P["Tagna utvisningar"] + 0.01 * P["Vunna tekningar"]
                            - 0.01 * P["Förlorade tekningar"] + 1.0 * (P["xGF 5v5"] - P["xGA 5v5"])
                            + 0.15 * (P["GF 5v5"] - P["GA 5v5"])).round(3)
        if len(GK):
            GK["Game Score+"] = (0.75 * GK["GSAx"]).round(3)
    else:
        P["Game Score+"] = np.nan
        if len(GK):
            GK["Game Score+"] = np.nan

    for col in ("Game Score", "Game Score+"):
        team_gs = pd.concat([P[["Match-id", "Lag", col]], GK[["Match-id", "Lag", col]] if len(GK) else None])
        team_gs = team_gs.groupby(["Match-id", "Lag"])[col].sum(min_count=1)
        T[f"Lagets {col}"] = [round(team_gs.get((m, l), np.nan), 3) for m, l in zip(T["Match-id"], T["Lag"])]

    S, G, L = season_tables(P, GK, T)

    matches = T[T["Hemma/borta"] == "Hemma"][["Match-id", "Datum", "Motståndare", "Lag", "Mål mot", "Mål för", "Avgjord i",
                                              "Skott mot", "Skott", "Lagets Game Score", "Lagets Game Score+"]].copy()
    matches.columns = ["Match-id", "Datum", "Bortalag", "Hemmalag", "Bortamål", "Hemmamål", "Avgjord i",
                       "Bortaskott", "Hemmaskott", "Hemmalagets Game Score", "Hemmalagets Game Score+"]
    away_t = T[T["Hemma/borta"] == "Borta"].set_index("Match-id")
    matches["Bortalagets Game Score"] = matches["Match-id"].map(away_t["Lagets Game Score"]).round(2)
    matches["Bortalagets Game Score+"] = matches["Match-id"].map(away_t["Lagets Game Score+"]).round(2)
    away_abbr = away_t["Lagförkortning"]
    home_abbr = T[T["Hemma/borta"] == "Hemma"].set_index("Match-id")["Lagförkortning"]
    matches["Bortalag kort"] = matches["Match-id"].map(away_abbr)
    matches["Hemmalag kort"] = matches["Match-id"].map(home_abbr)
    for c in ("Hemmalagets Game Score", "Hemmalagets Game Score+"):
        matches[c] = matches[c].round(2)
    matches = matches.sort_values(["Datum", "Match-id"])

    per_game_out = P.sort_values(["Datum", "Lag", "Game Score"], ascending=[True, True, False])
    shots_out = SH.drop(columns=[c for c in SH.columns if c.startswith("_")]) if len(SH) else SH
    if "xG" in shots_out:
        shots_out["xG"] = shots_out["xG"].round(4)
    T_out = T.drop(columns=["_id"])

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import vinstchans as VC
    try:
        progn = VC.prognoser(T_out)
        komm = VC.kommande(T_out, upcoming)
    except Exception as e:  # noqa: BLE001 – vinstchansen får aldrig stoppa resten
        problems.append(f"Vinstchansen kunde inte räknas: {type(e).__name__}: {e}")
        progn, komm = pd.DataFrame(), pd.DataFrame()

    tables = {"Spelare": S, "Målvakter": G, "Lag": L, "Vinstchans": komm, "Per match": per_game_out,
              "Målvakter per match": GK, "Lag per match": T_out, "Matcher": matches, "Prognoser": progn,
              "Skott": shots_out}

    if a.edge:
        log("Hämtar NHL Edge-data …")
        who = pd.concat([S[["Spelar-id", "Spelare", "Lag", "Position"]],
                         G.assign(Position="Målvakt")[["Spelar-id", "Spelare", "Lag", "Position"]] if G is not None else None])
        who = who.drop_duplicates("Spelar-id")
        es, eg = fetch_edge(f, season, who)
        tables["Edge utespelare"] = es
        tables["Edge målvakter"] = eg
        if not len(es) and not len(eg):
            log("  Ingen Edge-data kom tillbaka. NHL kan ha ändrat adresserna.")

    out = write_outputs(root / season, season, tables, excel=not a.utan_excel)
    log("")
    log(f"Klart: {len(S)} utespelare, {len(G) if G is not None else 0} målvakter, {len(L)} lag, {len(done)} matcher.")
    if out:
        log(f"Excel: {out}")
    log(f"CSV:   {root / season / 'csv'}")
    missing = int(P.groupby("Match-id")["Byteslista"].first().eq("saknas").sum())
    if missing:
        log(f"Obs: byteslista saknades för {missing} av {len(done)} matcher (CF/GF/xGF och istid per läge saknas där).")
    if problems:
        log(f"Obs: {len(problems)} avvikelser mot NHL:s egna siffror eller tolkningsfel:")
        for p in problems[:15]:
            log("  - " + p)
        if len(problems) > 15:
            log(f"  … och {len(problems) - 15} till (se avvikelser.txt).")
        (root / season / "avvikelser.txt").write_text("\n".join(problems), encoding="utf-8")


if __name__ == "__main__":
    main()
