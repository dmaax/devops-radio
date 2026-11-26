#!/usr/bin/env python3
"""DevOps Radio: monta a playlist do dia a partir da sua biblioteca classificada.

Uso:
  python3 devradio/generate.py                    # previa do dia de hoje
  python3 devradio/generate.py --week             # previa da semana inteira (a partir de hoje)
  python3 devradio/generate.py --date 2026-12-02  # previa de uma data
Previa nao altera historico nem publica nada. Saida em devradio/preview.md.

Fontes: output/todas_faixas.csv (subgenero, BPM) + data/spotify_raw/*.csv (energia, instrumentalidade, duracao).
Temas por dia em devradio/config.json. Historico de faixas tocadas em devradio/history.json.
"""
import argparse
import csv
import datetime as dt
import glob
import json
import os
import random
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG = os.path.join(HERE, "config.json")
HISTORY = os.path.join(HERE, "history.json")
WEEKDAY = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


LIBRARY = os.path.join(HERE, "library.csv")
LIB_FIELDS = ["uri", "title", "artists", "main_artist", "genre", "conf", "liked", "bpm", "camelot",
              "energy", "instr", "speech", "dur", "pop"]


def load_library():
    """Usa os CSVs completos se existirem (maquina local); senao devradio/library.csv (GitHub Actions)."""
    if not os.path.exists(os.path.join(ROOT, "output", "todas_faixas.csv")):
        lib = []
        for r in csv.DictReader(open(LIBRARY, encoding="utf-8")):
            r["liked"] = r["liked"] == "1"
            for k in ("bpm", "energy", "instr", "speech", "dur", "pop"):
                r[k] = f(r[k])
            lib.append(r)
        return lib
    return build_library()


def export_library():
    lib = [t for t in build_library() if t["genre"] not in ("Fora da eletrônica", "Sem dados")]
    with open(LIBRARY, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LIB_FIELDS)
        w.writeheader()
        for t in lib:
            w.writerow({**t, "liked": "1" if t["liked"] else "0"})
    print(f"{len(lib)} faixas -> {LIBRARY}")


def build_library():
    raw = {}
    for p in glob.glob(os.path.join(ROOT, "data", "spotify_raw", "*.csv")):
        for r in csv.DictReader(open(p, newline="", encoding="utf-8")):
            if r.get("Track URI"):
                raw.setdefault(r["Track URI"], r)
    lib = []
    for r in csv.DictReader(open(os.path.join(ROOT, "output", "todas_faixas.csv"), encoding="utf-8")):
        x = raw.get(r["Track URI"], {})
        lib.append({
            "uri": r["Track URI"], "title": r["Musica"], "artists": r["Artistas"],
            "main_artist": r["Artistas"].split(";")[0].strip().lower(),
            "genre": r["Subgenero"], "conf": r["Confianca"], "liked": r["Curtida"] == "sim",
            "bpm": f(r["BPM"]), "camelot": r["Camelot"], "energy": f(x.get("Energy")),
            "instr": f(x.get("Instrumentalness")), "speech": f(x.get("Speechiness")),
            "dur": f(x.get("Duration (ms)")) / 1000, "pop": f(x.get("Popularity")),
        })
    # remove duplicatas (mesma faixa com URIs diferentes)
    seen, out = set(), []
    for t in sorted(lib, key=lambda t: not t["liked"]):
        k = (t["main_artist"], t["title"].lower().split(" - ")[0])
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out


def load_history():
    return json.load(open(HISTORY, encoding="utf-8")) if os.path.exists(HISTORY) else {}


def last_played(history):
    lp = {}
    for day, uris in history.items():
        for u in uris:
            lp[u] = max(lp.get(u, ""), day)
    return lp


def build_day(lib, cfg, theme, date, history):
    rng = random.Random(date.isoformat())  # mesma data = mesma playlist
    lp = last_played(history)
    cutoff = (date - dt.timedelta(days=cfg["no_repeat_days"])).isoformat()

    def candidates(relax):
        lo, hi = theme["bpm"]
        elo, ehi = theme["energy"]
        mi = theme["min_instrumental"] * (1 - 0.5 * relax)
        ms = theme["max_speech"] * (1 + relax)
        pad = 3 * relax
        return [t for t in lib if t["genre"] in theme["genres"]
                and lo - pad <= t["bpm"] <= hi + pad and elo - 0.1 * relax <= t["energy"] <= ehi + 0.1 * relax
                and t["instr"] >= mi and t["speech"] <= ms and 90 <= t["dur"] <= 900]

    relax, pool = 0, candidates(0)
    while len(pool) < cfg["size"] * 2 and relax < 3:  # biblioteca pequena no tema: afrouxa filtros
        relax += 1
        pool = candidates(relax)

    def score(t):
        s = rng.random() * 3
        s += cfg["liked_bonus"] if t["liked"] else 0
        s += {"alta": 1.0, "media": 0.5}.get(t["conf"], 0)
        s += t["instr"]  # foco: menos voz
        played = lp.get(t["uri"], "")
        if played and played >= cutoff:
            s -= 100  # tocou recentemente: so entra se faltar opcao
        return s

    per_artist, picked = Counter(), []
    for t in sorted(pool, key=score, reverse=True):
        if per_artist[t["main_artist"]] >= cfg["max_per_artist"]:
            continue
        per_artist[t["main_artist"]] += 1
        picked.append(t)
        if len(picked) >= cfg["size"]:
            break
    picked.sort(key=lambda t: (t["bpm"], t["energy"]))
    return picked, len(pool), relax


def render(date, theme, tracks, pool, relax, cfg):
    mins = sum(t["dur"] for t in tracks) / 60
    bpms = [t["bpm"] for t in tracks]
    liked = sum(t["liked"] for t in tracks)
    gen = Counter(t["genre"] for t in tracks)
    L = [f"## {WEEKDAY[date.weekday()]} {date.strftime('%d/%m')} — {cfg['playlist_name']} · {theme['title']}",
         f"_{theme['description']}_", "",
         f"{len(tracks)} faixas · {mins / 60:.1f} h · BPM {min(bpms):.0f}–{max(bpms):.0f} · "
         f"{liked} curtidas · pool {pool} faixas" + (f" · filtros afrouxados (nível {relax})" if relax else ""),
         "· " + ", ".join(f"{g} {n}" for g, n in gen.most_common()), "",
         "| # | Artista | Faixa | BPM | Camelot | Energia | Instr. |", "|--:|---|---|--:|---|--:|--:|"]
    for i, t in enumerate(tracks, 1):
        L.append(f"| {i} | {t['artists'].replace(';', ', ')} | {t['title']} | {t['bpm']:.0f} | {t['camelot']} | "
                 f"{t['energy']:.2f} | {t['instr']:.2f} |{' ♥' if t['liked'] else ''}")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="AAAA-MM-DD (padrao: hoje)")
    ap.add_argument("--week", action="store_true", help="previa de 7 dias a partir da data")
    ap.add_argument("--export-library", action="store_true", help="gera devradio/library.csv (para o CI)")
    args = ap.parse_args()
    if args.export_library:
        export_library()
        return
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    start = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    lib = load_library()
    history = load_history()

    out = [f"# Prévia {cfg['playlist_name']}\n", f"Biblioteca: {len(lib)} faixas únicas\n"]
    for i in range(7 if args.week else 1):
        d = start + dt.timedelta(days=i)
        theme = cfg["days"][str(d.weekday())]
        tracks, pool, relax = build_day(lib, cfg, theme, d, history)
        if args.week:  # simula o historico para a semana nao repetir faixas
            history[d.isoformat()] = [t["uri"] for t in tracks]
        out.append(render(d, theme, tracks, pool, relax, cfg))
        print(f"{WEEKDAY[d.weekday()]} {d}: {len(tracks)} faixas · pool {pool} · relax {relax} · "
              f"{sum(t['dur'] for t in tracks) / 3600:.1f} h · curtidas {sum(t['liked'] for t in tracks)}")
    with open(os.path.join(HERE, "preview.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print("Prévia em", os.path.join(HERE, "preview.md"))


if __name__ == "__main__":
    main()
