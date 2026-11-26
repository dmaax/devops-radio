#!/usr/bin/env python3
"""Recomendacoes externas via Last.fm a partir das suas curtidas classificadas.

Pre-requisito: rodar scripts/classify.py antes (gera output/curtidas_classificadas.csv e output/todas_faixas.csv).
Chave: LASTFM_API_KEY no ambiente ou no arquivo .env na raiz do projeto.

Uso:
  python3 scripts/lastfm_recs.py                 # ate 25 sementes por subgenero
  python3 scripts/lastfm_recs.py --seeds 60      # mais sementes = mais recomendacoes (mais lento)
  python3 scripts/lastfm_recs.py --only "Afro House,Organic House"

Respostas da API ficam em cache em data/cache/lastfm, entao rodar de novo e rapido.
"""
import argparse
import csv
import hashlib
import json
import os
import random
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://ws.audioscrobbler.com/2.0/"
CACHE = os.path.join(ROOT, "data", "cache", "lastfm")
SKIP_GENRES = {"Fora da eletrônica", "Sem dados", "Eletrônica (genérica)"}


def load_key():
    key = os.environ.get("LASTFM_API_KEY")
    env = os.path.join(ROOT, ".env")
    if not key and os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            if line.strip().startswith("LASTFM_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit("Defina LASTFM_API_KEY no arquivo .env (LASTFM_API_KEY=suachave)")
    return key


_last_call = [0.0]


def call(key, method, **params):
    params = {"method": method, "api_key": key, "format": "json", "autocorrect": 1, **params}
    cache_id = hashlib.sha1(json.dumps({k: v for k, v in params.items() if k != "api_key"},
                                       sort_keys=True).encode()).hexdigest()
    path = os.path.join(CACHE, cache_id + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        wait = 0.22 - (time.time() - _last_call[0])  # ~4.5 req/s, abaixo do limite do Last.fm
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dj-library-tool/0.1"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503):
                time.sleep(2 ** attempt)
                continue
            try:
                data = json.load(e)
            except Exception:
                data = {"error": e.code}
            break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 ** attempt)
    else:
        return {}
    if isinstance(data, dict) and data.get("error") in (10, 26):
        raise SystemExit(f"Last.fm recusou a chave: {data.get('message')}")
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return data


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = s.split(" - ")[0]
    s = re.sub(r"\b(feat|ft)\.?\s.*", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def base_title(t):
    """Titulo como o Last.fm costuma ter: sem ' - Radio Edit', ' - Original Mix' etc. Mantem remix entre parenteses."""
    head, _, tail = t.partition(" - ")
    if tail and re.search(r"remix|rework|edit|mix|version|dub", tail, re.I) and \
            not re.search(r"original mix|radio edit|extended|remaster|edit$", tail, re.I):
        return f"{head} ({tail})"
    return head


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=25, help="sementes por subgenero")
    ap.add_argument("--per-seed", type=int, default=30, help="faixas similares buscadas por semente")
    ap.add_argument("--top", type=int, default=30, help="recomendacoes por subgenero no resultado")
    ap.add_argument("--only", default="", help="lista de subgeneros separados por virgula")
    args = ap.parse_args()
    key = load_key()
    random.seed(42)

    liked = list(csv.DictReader(open(os.path.join(ROOT, "output", "curtidas_classificadas.csv"), encoding="utf-8")))
    allt = list(csv.DictReader(open(os.path.join(ROOT, "output", "todas_faixas.csv"), encoding="utf-8")))

    known = set()  # tudo que ja esta na sua biblioteca
    for r in allt:
        for a in r["Artistas"].split(";"):
            known.add((norm(a), norm(r["Musica"])))
    liked_artists = Counter(norm(a) for r in liked for a in r["Artistas"].split(";"))

    only = {g.strip() for g in args.only.split(",") if g.strip()}
    by_g = defaultdict(list)
    for r in liked:
        g = r["Subgenero"]
        if g in SKIP_GENRES or (only and g not in only):
            continue
        by_g[g].append(r)

    # sementes: prioriza confianca alta, varia artistas
    seeds = []
    for g, items in by_g.items():
        items = sorted(items, key=lambda r: {"alta": 0, "media": 1}.get(r["Confianca"], 2) + random.random())
        used_artists, picked = Counter(), []
        for r in items:
            a = norm(r["Artistas"].split(";")[0])
            if used_artists[a] >= 2:
                continue
            used_artists[a] += 1
            picked.append(r)
            if len(picked) >= args.seeds:
                break
        seeds += [(g, r) for r in picked]
    print(f"{len(seeds)} sementes em {len(by_g)} subgêneros")

    cand = {}
    no_result = 0
    for i, (g, r) in enumerate(seeds, 1):
        artist = r["Artistas"].split(";")[0].strip()
        res = []
        for title in dict.fromkeys([base_title(r["Musica"]), r["Musica"].split(" - ")[0].strip()]):
            d = call(key, "track.getSimilar", artist=artist, track=title, limit=args.per_seed)
            res = (d.get("similartracks") or {}).get("track") or []
            if res:
                break
        if not res:  # fallback: artistas similares -> top faixas
            no_result += 1
            d = call(key, "artist.getSimilar", artist=artist, limit=8)
            for sa in ((d.get("similarartists") or {}).get("artist") or [])[:4]:
                t = call(key, "artist.getTopTracks", artist=sa["name"], limit=3)
                for tt in ((t.get("toptracks") or {}).get("track") or []):
                    res.append({"name": tt["name"], "artist": {"name": sa["name"]},
                                "match": float(sa.get("match", 0)) * 0.5, "url": tt.get("url", "")})
        for t in res:
            an, tn = t["artist"]["name"], t["name"]
            k = (norm(an), norm(tn))
            if not k[1] or k in known:
                continue
            c = cand.setdefault(k, {"Artista": an, "Musica": tn, "URL": t.get("url", ""),
                                    "score": 0.0, "seeds": [], "genres": Counter()})
            m = float(t.get("match", 0) or 0)
            c["score"] += m
            c["genres"][g] += m
            c["seeds"].append(f'{r["Artistas"].split(";")[0]} - {r["Musica"]}')
        if i % 25 == 0:
            print(f"  {i}/{len(seeds)} sementes · {len(cand)} candidatas")

    rows = []
    for c in cand.values():
        g, gs = c["genres"].most_common(1)[0]
        n = len(set(c["seeds"]))
        bonus = 0.15 if liked_artists.get(norm(c["Artista"])) else 0  # artista que voce ja curte
        rows.append({
            "Subgenero": g, "Artista": c["Artista"], "Musica": c["Musica"],
            "Score": round(c["score"] + 0.3 * (n - 1) + bonus, 3), "Sementes": n,
            "Artista conhecido": "sim" if bonus else "",
            "Parecida com": " | ".join(list(dict.fromkeys(c["seeds"]))[:3]),
            "Last.fm": c["URL"],
            "Busca Beatport": "https://www.beatport.com/search?q=" + urllib.parse.quote(f'{c["Artista"]} {c["Musica"]}'),
        })
    out = []
    for g in sorted({r["Subgenero"] for r in rows}):
        per_artist, picked = Counter(), []
        for r in sorted((r for r in rows if r["Subgenero"] == g), key=lambda r: -r["Score"]):
            a = norm(r["Artista"])
            if per_artist[a] >= 2:  # diversidade: no maximo 2 faixas por artista
                continue
            per_artist[a] += 1
            picked.append(r)
            if len(picked) >= args.top:
                break
        out += picked

    path = os.path.join(ROOT, "output", "recomendacoes_lastfm.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()) if out else ["Subgenero"])
        w.writeheader()
        w.writerows(out)

    md = ["# Recomendações Last.fm por subgênero\n",
          f"{len(seeds)} sementes · {no_result} sem similares diretos (usaram artistas similares) · "
          f"{len(cand)} candidatas novas\n"]
    for g in sorted({r["Subgenero"] for r in out}):
        md.append(f"\n## {g}\n")
        for r in [x for x in out if x["Subgenero"] == g][:10]:
            md.append(f'- **{r["Artista"]} – {r["Musica"]}** · score {r["Score"]} · parecida com: '
                      f'{r["Parecida com"].split(" | ")[0]} · [Beatport]({r["Busca Beatport"]})')
    with open(os.path.join(ROOT, "output", "recomendacoes_lastfm.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    print(f"OK: {len(out)} recomendações em {path}")


if __name__ == "__main__":
    main()
