#!/usr/bin/env python3
"""Classifica faixas exportadas pelo Exportify em subgeneros eletronicos (taxonomia Beatport).

Uso: python3 scripts/classify.py [pasta_csvs] [pasta_saida]
Padrao: data/spotify_raw -> output

Saidas:
  output/curtidas_classificadas.csv   Liked Songs com subgenero, Camelot, BPM
  output/todas_faixas.csv             todas as faixas unicas + playlists onde aparecem
  output/recomendacoes_internas.csv   faixas das suas playlists (nao curtidas) mais parecidas com suas curtidas
  output/resumo.md                    perfil por subgenero
"""
import csv
import glob
import os
import re
import statistics
import sys
from collections import Counter, defaultdict

SRC = sys.argv[1] if len(sys.argv) > 1 else "data/spotify_raw"
OUT = sys.argv[2] if len(sys.argv) > 2 else "output"

# tag (como vem do Exportify) -> genero Beatport. Peso = especificidade da tag.
TAG_MAP = {
    # Melodic House & Techno
    "techno melódico": ("Melodic House & Techno", 3), "house melódico": ("Melodic House & Techno", 3),
    "melodic techno": ("Melodic House & Techno", 3), "melodic house": ("Melodic House & Techno", 3),
    # Progressive
    "house progressivo": ("Progressive House", 3), "progressive house": ("Progressive House", 3),
    # Organic / Downtempo / Ambient
    "organic house": ("Organic House", 4),
    "downtempo": ("Downtempo", 2), "trip hop": ("Downtempo", 2), "chillstep": ("Downtempo", 2),
    "lo-fi beats": ("Downtempo", 2), "chillwave": ("Downtempo", 2), "nu-jazz": ("Downtempo", 1),
    "música ambiente": ("Ambient", 3), "dark ambient": ("Ambient", 3), "drone": ("Ambient", 2),
    "space music": ("Ambient", 2), "jazz ambiente": ("Ambient", 1),
    # Afro
    "afro house": ("Afro House", 4), "afro tech": ("Afro House", 4), "amapiano": ("Afro House", 3),
    "gqom": ("Afro House", 3), "3 step": ("Afro House", 3),
    # Tech House / Minimal
    "tech house": ("Tech House", 3), "tribal house": ("Tech House", 1), "rally house": ("Tech House", 2),
    "minimal techno": ("Minimal / Deep Tech", 3),
    # Techno
    "tecno": ("Techno (Peak Time / Driving)", 2), "techno": ("Techno (Peak Time / Driving)", 2),
    "tekno": ("Techno (Peak Time / Driving)", 2),
    "dub techno": ("Techno (Raw / Deep / Hypnotic)", 4), "acid techno": ("Techno (Raw / Deep / Hypnotic)", 3),
    "hard techno": ("Hard Techno", 4), "hyper techno": ("Hard Techno", 4), "hardcore techno": ("Hard Techno", 3),
    "hard house": ("Hard Techno", 2), "hardstyle": ("Hard Techno", 1),
    # House family
    "deep house": ("Deep House", 3), "lo-fi house": ("Deep House", 3), "jazz house": ("Deep House", 3),
    "house": ("House", 1), "chicago house": ("House", 3), "acid house": ("House", 3),
    "house francês": ("House", 3), "stutter house": ("House", 3), "hip house": ("House", 2),
    "house latino": ("House", 2),
    "funky house": ("Jackin House", 3), "disco house": ("Jackin House", 3),
    "nu disco": ("Nu Disco / Disco", 3), "disco": ("Nu Disco / Disco", 1), "italo disco": ("Nu Disco / Disco", 2),
    "indie dance": ("Indie Dance", 3), "electroclash": ("Indie Dance", 3), "darkwave": ("Indie Dance", 2),
    "ebm": ("Indie Dance", 2), "new rave": ("Indie Dance", 2), "dance alternativo": ("Indie Dance", 2),
    "cold wave": ("Indie Dance", 2),
    "bass house": ("Bass House", 3), "g-house": ("Bass House", 3), "future house": ("Bass House", 2),
    "bassline": ("UK Garage / Bassline", 3), "garage reino unido": ("UK Garage / Bassline", 3),
    "funky do reino unido": ("UK Garage / Bassline", 2),
    # Trance
    "trance": ("Trance", 2), "trance progressivo": ("Trance", 3),
    "trance psicodélico": ("Psy-Trance", 4),
    # Bass
    "drum and bass": ("Drum & Bass", 4), "liquid funk": ("Drum & Bass", 4), "jungle": ("Drum & Bass", 4),
    "drumstep": ("Drum & Bass", 2),
    "dubstep": ("Dubstep / Bass", 3), "riddim": ("Dubstep / Bass", 3), "deathstep": ("Dubstep / Bass", 3),
    "bass music": ("Dubstep / Bass", 2), "melodic bass": ("Dubstep / Bass", 2), "future bass": ("Dubstep / Bass", 2),
    "breakbeat": ("Breaks", 3), "big beat": ("Breaks", 3),
    "electro": ("Electro", 2), "miami bass": ("Electro", 1),
    # Mainstage / Brazilian
    "brazilian bass": ("Brazilian Bass / Slap House", 4), "slap house": ("Brazilian Bass / Slap House", 4),
    "edm": ("Mainstage / EDM", 1), "big room": ("Mainstage / EDM", 3), "eletrohouse": ("Mainstage / EDM", 2),
    "melbourne bounce": ("Mainstage / EDM", 3), "tropical house": ("Mainstage / EDM", 2),
    "eurodance": ("Dance / Pop", 2), "italo dance": ("Dance / Pop", 2), "hi-nrg": ("Dance / Pop", 2),
    # Electronica
    "idm": ("Electronica", 3), "glitch": ("Electronica", 2), "eletrônica indie": ("Electronica", 2),
    "synthwave": ("Electronica", 2), "música clássica eletrônica": ("Electronica", 2),
    "phonk": ("Phonk", 3), "drift phonk": ("Phonk", 3), "phonk brasileiro": ("Phonk", 3),
    # genericas
    "eletronic": ("Eletrônica (genérica)", 0), "eletrônica": ("Eletrônica (genérica)", 0),
    "electronic": ("Eletrônica (genérica)", 0), "pop eletrônico": ("Eletrônica (genérica)", 0),
}

# faixa de BPM tipica de cada genero (para desempate)
BPM_RANGE = {
    "Melodic House & Techno": (118, 128), "Progressive House": (118, 128), "Organic House": (105, 124),
    "Afro House": (115, 126), "Tech House": (122, 130), "Minimal / Deep Tech": (120, 130),
    "Techno (Peak Time / Driving)": (125, 140), "Techno (Raw / Deep / Hypnotic)": (118, 135),
    "Hard Techno": (135, 165), "Deep House": (115, 125), "House": (118, 128), "Jackin House": (120, 128),
    "Nu Disco / Disco": (105, 124), "Indie Dance": (100, 126), "Bass House": (122, 130),
    "UK Garage / Bassline": (128, 140), "Trance": (128, 142), "Psy-Trance": (135, 150),
    "Drum & Bass": (160, 180), "Dubstep / Bass": (135, 152), "Breaks": (120, 140), "Electro": (115, 135),
    "Brazilian Bass / Slap House": (118, 127), "Mainstage / EDM": (124, 132), "Dance / Pop": (118, 140),
    "Downtempo": (60, 115), "Ambient": (50, 125), "Electronica": (60, 180), "Phonk": (120, 160),
}

# estilos do Discogs (por lancamento, nao por artista) -> genero Beatport
DISCOGS_MAP = {
    "Tech House": ("Tech House", 4), "Minimal": ("Minimal / Deep Tech", 4), "Minimal Techno": ("Minimal / Deep Tech", 4),
    "Deep Tech": ("Minimal / Deep Tech", 4), "Deep House": ("Deep House", 4), "Progressive House": ("Progressive House", 4),
    "Afro House": ("Afro House", 5), "Afrobeat": ("Afro House", 1), "Tribal House": ("Tech House", 2),
    "Techno": ("Techno (Peak Time / Driving)", 2), "Dub Techno": ("Techno (Raw / Deep / Hypnotic)", 5),
    "Acid": ("Techno (Raw / Deep / Hypnotic)", 2), "Hard Techno": ("Hard Techno", 5), "Hardcore": ("Hard Techno", 2),
    "Hard House": ("Hard Techno", 2), "Melodic Techno": ("Melodic House & Techno", 5),
    "House": ("House", 1), "Acid House": ("House", 4), "Chicago House": ("House", 4), "Garage House": ("House", 3),
    "Disco": ("Nu Disco / Disco", 2), "Nu-Disco": ("Nu Disco / Disco", 4), "Italo-Disco": ("Nu Disco / Disco", 3),
    "Electro House": ("Mainstage / EDM", 3), "Big Room": ("Mainstage / EDM", 4), "Euro House": ("Dance / Pop", 3),
    "Bass House": ("Bass House", 5), "Future House": ("Bass House", 3), "UK Garage": ("UK Garage / Bassline", 5),
    "Bassline": ("UK Garage / Bassline", 5), "Speed Garage": ("UK Garage / Bassline", 4),
    "Trance": ("Trance", 3), "Progressive Trance": ("Trance", 4), "Psy-Trance": ("Psy-Trance", 5),
    "Goa Trance": ("Psy-Trance", 4), "Drum n Bass": ("Drum & Bass", 5), "Jungle": ("Drum & Bass", 5),
    "Dubstep": ("Dubstep / Bass", 5), "Breakbeat": ("Breaks", 3), "Breaks": ("Breaks", 4), "Big Beat": ("Breaks", 4),
    "Electro": ("Electro", 3), "Downtempo": ("Downtempo", 3), "Trip Hop": ("Downtempo", 3), "Chillout": ("Downtempo", 2),
    "Ambient": ("Ambient", 3), "IDM": ("Electronica", 4), "Leftfield": ("Electronica", 2),
    "Synth-pop": ("Indie Dance", 0), "EBM": ("Indie Dance", 3), "Electroclash": ("Indie Dance", 4),
    "Indie Dance": ("Indie Dance", 5), "Nu Disco": ("Nu Disco / Disco", 4), "Organic House": ("Organic House", 5),
    "Phonk": ("Phonk", 4), "Baile Funk": ("Fora da eletrônica", 0),
}

# Discogs nao tem "Melodic Techno"/"Organic House": rotula esse som como Progressive/Deep/Techno etc.
# Esses estilos contam como compativeis (meio peso) quando as tags do Spotify ja apontam o genero.
DISCOGS_COMPAT = {
    "Melodic House & Techno": {"Progressive House", "Deep House", "Techno", "Minimal", "Neo Trance",
                               "Progressive Trance", "Melodic Techno", "Deep Techno"},
    "Organic House": {"Deep House", "Downtempo", "Tribal", "Afro House", "Ambient", "Balearic", "Progressive House"},
    "Afro House": {"Deep House", "Tribal", "Tribal House", "Afro House", "Afrobeat", "Tech House", "Afro-Cuban"},
}

CAMELOT_MAJOR = ["8B", "3B", "10B", "5B", "12B", "7B", "2B", "9B", "4B", "11B", "6B", "1B"]
CAMELOT_MINOR = ["5A", "12A", "7A", "2A", "9A", "4A", "11A", "6A", "1A", "8A", "3A", "10A"]
NOTE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def camelot(key, mode):
    try:
        k, m = int(key), int(mode)
    except (TypeError, ValueError):
        return "", ""
    if not 0 <= k <= 11:
        return "", ""
    return (CAMELOT_MAJOR if m == 1 else CAMELOT_MINOR)[k], NOTE[k] + ("" if m == 1 else "m")


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def tags_of(row):
    return [t.strip().lower() for t in (row.get("Genres") or "").split(",") if t.strip()]


def bpm_fit(genre, bpm):
    if not bpm or genre not in BPM_RANGE:
        return 0
    lo, hi = BPM_RANGE[genre]
    for b in (bpm, bpm * 2, bpm / 2):  # Spotify as vezes reporta metade/dobro
        if lo - 2 <= b <= hi + 2:
            return 2 if b == bpm else 1
    return -1


def classify(tags, bpm, dstyles=(), title=""):
    """Retorna (genero, confianca, candidatos)."""
    scores = Counter()
    for i, t in enumerate(tags):
        if t in TAG_MAP:
            g, w = TAG_MAP[t]
            scores[g] += w + (1 if i == 0 else 0)
    for i, s in enumerate(dstyles):
        if s in DISCOGS_MAP and DISCOGS_MAP[s][1] > 0:
            g, w = DISCOGS_MAP[s]
            # Discogs descreve a faixa; quando o artista ja tem esse genero, reforca
            scores[g] += w + (2 if i == 0 else 0) + (2 if g in scores else 0)
        for g, compat in DISCOGS_COMPAT.items():
            if g in scores and s in compat:
                scores[g] += (DISCOGS_MAP.get(s, ("", 3))[1] + (2 if i == 0 else 0)) / 2
    if not scores:
        return None, 0, {}
    total = Counter()
    for g, s in scores.items():
        total[g] = s + bpm_fit(g, bpm) * 1.5
    # generico so ganha se nao houver mais nada
    if len(total) > 1 and "Eletrônica (genérica)" in total:
        del total["Eletrônica (genérica)"]
    best, bs = total.most_common(1)[0]
    # tag principal nao-eletronica (ex.: new wave, rock) + sinal eletronico fraco -> nao e eletronica
    is_remix = bool(re.search(r"remix|rework|re-edit|edit|dub\b|version", title, re.I))
    if tags and tags[0] not in TAG_MAP and bs < 4 and not is_remix:
        return None, 0, {}
    second = total.most_common(2)[1][1] if len(total) > 1 else 0
    conf = "alta" if bs - second >= 3 else ("media" if bs - second >= 1 else "baixa")
    return best, conf, dict(total)


def main():
    rows_by_uri = {}
    playlists = defaultdict(set)
    liked = []
    for f in sorted(glob.glob(os.path.join(SRC, "*.csv"))):
        name = os.path.basename(f)[:-4]
        with open(f, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                uri = r.get("Track URI")
                if not uri:
                    continue
                rows_by_uri.setdefault(uri, r)
                if name != "Liked_Songs":
                    playlists[uri].add(name)
                else:
                    liked.append(r)
    liked_uris = {r["Track URI"] for r in liked}

    # inferencia para faixas sem tag: genero majoritario do artista / gravadora no dataset todo
    artist_tags, label_tags = defaultdict(Counter), defaultdict(Counter)
    for r in rows_by_uri.values():
        tg = tags_of(r)
        if not tg:
            continue
        for a in r["Artist Name(s)"].split(";"):
            artist_tags[a.strip()].update(tg)
        if r.get("Record Label"):
            label_tags[r["Record Label"].strip()].update(tg)

    def enrich(r):
        tg = tags_of(r)
        if tg:
            return tg, "spotify"
        c = Counter()
        for a in r["Artist Name(s)"].split(";"):
            c.update(artist_tags.get(a.strip(), {}))
        if c:
            return [t for t, _ in c.most_common(4)], "artista"
        lt = label_tags.get((r.get("Record Label") or "").strip())
        if lt and sum(lt.values()) >= 5:
            return [t for t, _ in lt.most_common(3)], "gravadora"
        return [], "sem dados"

    discogs = {}
    dpath = os.path.join(os.path.dirname(SRC.rstrip("/")) or ".", "discogs_styles.csv")
    if os.path.exists(dpath):
        for d in csv.DictReader(open(dpath, encoding="utf-8")):
            discogs[d["Track URI"]] = [s.strip() for s in d["Discogs styles"].split(",") if s.strip()]

    out_rows = {}
    for uri, r in rows_by_uri.items():
        tg, src = enrich(r)
        ds = discogs.get(uri, [])
        if ds:
            src += "+discogs"
        bpm = fnum(r.get("Tempo"))
        g, conf, _ = classify(tg, bpm, ds, r["Track Name"])
        if g is None:
            g = "Fora da eletrônica" if tg else "Sem dados"
            conf = ""
        cam, note = camelot(r.get("Key"), r.get("Mode"))
        out_rows[uri] = {
            "Subgenero": g, "Confianca": conf, "Fonte genero": src,
            "Musica": r["Track Name"], "Artistas": r["Artist Name(s)"], "Gravadora": r.get("Record Label", ""),
            "BPM": round(bpm) if bpm else "", "Camelot": cam, "Tom": note,
            "Energia": r.get("Energy", ""), "Dancabilidade": r.get("Danceability", ""),
            "Lancamento": r.get("Release Date", ""), "Popularidade": r.get("Popularity", ""),
            "Tags": ", ".join(tg), "Discogs": ", ".join(ds), "ISRC": r.get("ISRC", ""), "Track URI": uri,
            "Curtida": "sim" if uri in liked_uris else "",
            "Playlists": " | ".join(sorted(playlists.get(uri, ()))),
        }

    os.makedirs(OUT, exist_ok=True)
    fields = list(next(iter(out_rows.values())).keys())

    def write(path, rows):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    liked_out = [out_rows[r["Track URI"]] for r in liked]
    liked_out.sort(key=lambda x: (x["Subgenero"], x["BPM"] or 0))
    write(os.path.join(OUT, "curtidas_classificadas.csv"), liked_out)
    write(os.path.join(OUT, "todas_faixas.csv"), sorted(out_rows.values(), key=lambda x: (x["Subgenero"], x["Artistas"])))

    # ---- perfil das curtidas ----
    by_g = defaultdict(list)
    for x in liked_out:
        by_g[x["Subgenero"]].append(x)
    liked_artists, liked_labels = Counter(), Counter()
    for x in liked_out:
        for a in x["Artistas"].split(";"):
            liked_artists[a.strip()] += 1
        if x["Gravadora"]:
            liked_labels[x["Gravadora"]] += 1

    # ---- recomendacoes internas: faixas nao curtidas, mesmo subgenero, artistas/gravadoras que voce curte ----
    recs = []
    for uri, x in out_rows.items():
        if uri in liked_uris or x["Subgenero"] in ("Fora da eletrônica", "Sem dados", "Eletrônica (genérica)"):
            continue
        g_items = by_g.get(x["Subgenero"])
        if not g_items or len(g_items) < 5:
            continue
        a_score = sum(min(liked_artists.get(a.strip(), 0), 10) for a in x["Artistas"].split(";"))
        l_score = min(liked_labels.get(x["Gravadora"], 0), 10)
        bpms = [i["BPM"] for i in g_items if i["BPM"]]
        med = statistics.median(bpms) if bpms else 0
        bpm_pen = abs((x["BPM"] or med) - med) / 4
        pl_score = len(x["Playlists"].split(" | ")) if x["Playlists"] else 0
        score = a_score * 1.0 + l_score * 0.7 + min(pl_score, 5) - bpm_pen
        if x["Confianca"] == "baixa":
            score -= 2
        recs.append((score, x))
    recs.sort(key=lambda t: -t[0])
    def tkey(x):
        return (x["Artistas"].lower(), x["Musica"].lower().split(" - ")[0].strip())

    seen = {tkey(x) for x in liked_out}  # mesma faixa com outro URI = ja curtida
    per_g, chosen = Counter(), []
    for s, x in recs:
        if tkey(x) in seen:
            continue
        seen.add(tkey(x))
        if per_g[x["Subgenero"]] < 15:
            per_g[x["Subgenero"]] += 1
            chosen.append(dict(x, Score=round(s, 1)))
    chosen.sort(key=lambda x: (x["Subgenero"], -x["Score"]))
    with open(os.path.join(OUT, "recomendacoes_internas.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["Score"] + fields)
        w.writeheader()
        w.writerows(chosen)

    # ---- resumo ----
    L = ["# Perfil das suas Músicas Curtidas\n",
         f"Total de curtidas: **{len(liked_out)}** · faixas únicas em todas as playlists: **{len(out_rows)}**\n",
         "| Subgênero | Faixas | % | BPM mediano | Camelot mais comum | Top artistas | Top gravadoras |",
         "|---|---:|---:|---:|---|---|---|"]
    for g, items in sorted(by_g.items(), key=lambda kv: -len(kv[1])):
        bpms = [i["BPM"] for i in items if i["BPM"]]
        arts, labs = Counter(), Counter()
        for i in items:
            for a in i["Artistas"].split(";"):
                arts[a.strip()] += 1
            if i["Gravadora"]:
                labs[i["Gravadora"]] += 1
        cams = Counter(i["Camelot"] for i in items if i["Camelot"])
        L.append(f"| {g} | {len(items)} | {100*len(items)/len(liked_out):.1f} | "
                 f"{round(statistics.median(bpms)) if bpms else ''} | "
                 f"{', '.join(c for c, _ in cams.most_common(3))} | "
                 f"{', '.join(a for a, _ in arts.most_common(5))} | {', '.join(l for l, _ in labs.most_common(3))} |")
    src = Counter(x["Fonte genero"] for x in liked_out)
    conf = Counter(x["Confianca"] for x in liked_out if x["Confianca"])
    L += ["", f"Fonte do gênero: {dict(src)}", f"Confiança: {dict(conf)}"]
    with open(os.path.join(OUT, "resumo.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
