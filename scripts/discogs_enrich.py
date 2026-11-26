#!/usr/bin/env python3
"""Busca os estilos do Discogs (por lancamento) para suas faixas.

Chave: DISCOGS_TOKEN no ambiente ou no .env.
Saida: data/discogs_styles.csv (Track URI -> estilos), usado automaticamente por scripts/classify.py.

Uso:
  python3 scripts/discogs_enrich.py            # so as curtidas (padrao)
  python3 scripts/discogs_enrich.py --all      # todas as faixas unicas (lento: limite de 60 req/min)
Cache em data/cache/discogs; pode interromper e rodar de novo que continua de onde parou.
"""
import argparse
import csv
import glob
import hashlib
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache", "discogs")
OUT = os.path.join(ROOT, "data", "discogs_styles.csv")


def load_token():
    tok = os.environ.get("DISCOGS_TOKEN")
    env = os.path.join(ROOT, ".env")
    if not tok and os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            if line.strip().startswith("DISCOGS_TOKEN="):
                tok = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not tok:
        raise SystemExit("Defina DISCOGS_TOKEN no arquivo .env (DISCOGS_TOKEN=seutoken)")
    return tok


_last = [0.0]


def search(token, **params):
    params = {"type": "release", "per_page": 5, **params}
    cid = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()
    path = os.path.join(CACHE, cid + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    url = "https://api.discogs.com/database/search?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        wait = 1.05 - (time.time() - _last[0])  # 60 req/min autenticado
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "DJLibraryTool/0.1",
                                                       "Authorization": f"Discogs token={token}"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise SystemExit("Discogs recusou o token (401).")
            if e.code in (429, 500, 502, 503):
                time.sleep(5 * (attempt + 1))
                continue
            data = {"results": []}
            break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(3 * (attempt + 1))
    else:
        return {"results": []}
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return data


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def clean_title(t):
    t = t.split(" - ")[0]
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def styles_for(token, artist, title, album):
    tries = [dict(artist=artist, track=clean_title(title)),
             dict(q=f"{artist} {clean_title(title)}")]
    if album and norm(album) != norm(clean_title(title)):
        tries.insert(1, dict(artist=artist, release_title=clean_title(album)))
    for p in tries:
        res = search(token, **p).get("results") or []
        # confere que o artista aparece no titulo do resultado ("Artista - Release")
        good = [r for r in res if norm(artist) in norm(r.get("title", ""))]
        if good:
            votes = Counter()
            for i, r in enumerate(good[:3]):
                for s in r.get("style") or []:
                    votes[s] += 3 - i
            genres = sorted({g for r in good[:3] for g in r.get("genre") or []})
            r0 = good[0]
            return {"Discogs styles": ", ".join(s for s, _ in votes.most_common()),
                    "Discogs genres": ", ".join(genres), "Discogs release": r0.get("title", ""),
                    "Discogs year": r0.get("year", ""), "Discogs url": "https://www.discogs.com" + r0.get("uri", "")}
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="todas as faixas, nao so curtidas")
    args = ap.parse_args()
    token = load_token()

    files = glob.glob(os.path.join(ROOT, "data", "spotify_raw", "*.csv")) if args.all else \
        [os.path.join(ROOT, "data", "spotify_raw", "Liked_Songs.csv")]
    tracks = {}
    for f in files:
        for r in csv.DictReader(open(f, newline="", encoding="utf-8")):
            if r.get("Track URI"):
                tracks.setdefault(r["Track URI"], r)

    done = {}
    if os.path.exists(OUT):
        for r in csv.DictReader(open(OUT, encoding="utf-8")):
            done[r["Track URI"]] = r

    fields = ["Track URI", "Discogs styles", "Discogs genres", "Discogs release", "Discogs year", "Discogs url"]
    todo = [u for u in tracks if u not in done]
    print(f"{len(tracks)} faixas · {len(done)} já feitas · {len(todo)} a buscar (~{len(todo) * 1.5 / 60:.0f} min no pior caso)")
    found = 0
    for i, uri in enumerate(todo, 1):
        r = tracks[uri]
        artist = r["Artist Name(s)"].split(";")[0].strip()
        info = styles_for(token, artist, r["Track Name"], r.get("Album Name", ""))
        done[uri] = {"Track URI": uri, **(info or {k: "" for k in fields[1:]})}
        found += bool(info and info["Discogs styles"])
        if i % 50 == 0 or i == len(todo):
            with open(OUT, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=fields)
                w.writeheader()
                w.writerows(done.values())
            print(f"  {i}/{len(todo)} · com estilos: {found}", flush=True)
    print(f"OK: {OUT}")


if __name__ == "__main__":
    main()
