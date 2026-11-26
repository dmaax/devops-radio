#!/usr/bin/env python3
"""Cria/atualiza playlists privadas no seu Spotify a partir da classificacao.

Pre-requisitos: SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET no .env; redirect URI do app =
http://127.0.0.1:8888/callback . Na primeira vez abre um link de login (token fica em data/cache/spotify_token.json).

Uso:
  python3 scripts/spotify_playlists.py recs     # "Descobertas – <subgenero>" a partir de output/recomendacoes_lastfm.csv
  python3 scripts/spotify_playlists.py liked    # "Curtidas – <subgenero>" a partir de output/curtidas_classificadas.csv
  opcoes: --dry-run (nao cria nada), --min 5 (tamanho minimo da playlist), --only "Afro House,Tech House"

Rodar de novo SUBSTITUI o conteudo das playlists criadas por este script (ids em data/spotify_playlists.json),
nao cria duplicadas.  API conforme regras de Development Mode de fev/2026 (POST /me/playlists, /items, search limit 10).
"""
import argparse
import base64
import csv
import hashlib
import http.server
import json
import os
import re
import secrets
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.spotify.com/v1"
REDIRECT = "http://127.0.0.1:8888/callback"
SCOPES = "playlist-modify-private playlist-modify-public playlist-read-private"
TOKEN_PATH = os.path.join(ROOT, "data", "cache", "spotify_token.json")
SEARCH_CACHE = os.path.join(ROOT, "data", "cache", "spotify_search")
STATE_PATH = os.path.join(ROOT, "data", "spotify_playlists.json")
SKIP = {"Fora da eletrônica", "Sem dados", "Eletrônica (genérica)"}


def env(name):
    v = os.environ.get(name)
    if not v and os.path.exists(os.path.join(ROOT, ".env")):
        for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
            if line.strip().startswith(name + "="):
                v = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not v:
        raise SystemExit(f"Falta {name} no .env")
    return v


CID, SECRET = env("SPOTIFY_CLIENT_ID"), env("SPOTIFY_CLIENT_SECRET")


# ---------------- auth ----------------
def token_request(data):
    auth = base64.b64encode(f"{CID}:{SECRET}".encode()).decode()
    req = urllib.request.Request("https://accounts.spotify.com/api/token", data=urllib.parse.urlencode(data).encode(),
                                 headers={"Authorization": "Basic " + auth,
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        tok = json.load(r)
    tok["expires_at"] = time.time() + tok.get("expires_in", 3600) - 60
    return tok


def save_token(tok):
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    fd = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(tok, fh)


def login():
    state = secrets.token_urlsafe(16)
    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(
        {"client_id": CID, "response_type": "code", "redirect_uri": REDIRECT, "scope": SCOPES, "state": state})
    print("\n>>> Abra este link no navegador e autorize o app:\n" + url + "\n", flush=True)
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state and "code" in q:
                got["code"] = q["code"][0]
                msg = "Pronto! Pode fechar esta aba e voltar ao terminal."
            else:
                msg = "Falhou: " + q.get("error", ["state invalido"])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(msg.encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 8888), H)
    srv.timeout = 600
    while "code" not in got:
        srv.handle_request()
    srv.server_close()
    tok = token_request({"grant_type": "authorization_code", "code": got["code"], "redirect_uri": REDIRECT})
    save_token(tok)
    print("Login OK, token salvo.", flush=True)
    return tok


def get_token():
    if os.path.exists(TOKEN_PATH):
        tok = json.load(open(TOKEN_PATH))
        if time.time() < tok.get("expires_at", 0):
            return tok
        if tok.get("refresh_token"):
            new = token_request({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
            new.setdefault("refresh_token", tok["refresh_token"])
            save_token(new)
            return new
    return login()


_tok = [None]


def api(method, path, params=None, body=None):
    for attempt in range(6):
        if not _tok[0] or time.time() >= _tok[0]["expires_at"]:
            _tok[0] = get_token()
        url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": "Bearer " + _tok[0]["access_token"],
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                ra = int(e.headers.get("Retry-After", "5") or 5)
                print(f"  [limite do Spotify] pediu {ra}s de espera; aguardando {min(ra, 90)}s", flush=True)
                time.sleep(min(ra, 90) + 1)
                continue
            if e.code == 401 and attempt == 0:
                _tok[0] = None
                if os.path.exists(TOKEN_PATH):
                    os.remove(TOKEN_PATH)
                continue
            if e.code >= 500:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"Spotify {method} {path} -> {e.code}: {e.read()[:300].decode(errors='ignore')}")
        except (urllib.error.URLError, TimeoutError, ConnectionError):  # queda de rede: espera e tenta de novo
            time.sleep(5 * (attempt + 1))
    raise SystemExit(f"Spotify {method} {path}: muitas tentativas")


# ---------------- busca ----------------
def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = re.sub(r"\b(feat|ft)\.?\s.*", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def remix_tag(s):
    m = re.search(r"[\(\[-]\s*([^\)\]-]*(remix|rework|edit|dub|version)[^\)\]]*)", s or "", re.I)
    return norm(m.group(1)) if m else ""


CACHED_ONLY = [False]


class NotCached(Exception):
    pass


def find_track(artist, title):
    key = hashlib.sha1(f"{artist}|{title}".encode()).hexdigest()
    path = os.path.join(SEARCH_CACHE, key + ".json")
    if os.path.exists(path):
        return json.load(open(path)).get("uri")
    if CACHED_ONLY[0]:
        raise NotCached
    base = re.sub(r"\(.*?\)|\[.*?\]", " ", title).split(" - ")[0].strip()
    best = None
    for q in (f'track:"{base}" artist:"{artist}"', f"{artist} {base}"):
        time.sleep(0.35)  # ritmo gentil para nao estourar o limite do modo desenvolvedor
        items = (api("GET", "/search", {"q": q, "type": "track", "limit": 10}).get("tracks") or {}).get("items") or []
        want_a, want_t, want_r = norm(artist), norm(base), remix_tag(title)
        scored = []
        for it in items:
            arts = [norm(a["name"]) for a in it.get("artists", [])]
            if not any(want_a == a or want_a in a or a in want_a for a in arts if a):
                continue
            if norm(it["name"]).split(" - ")[0] != want_t and not norm(it["name"]).startswith(want_t):
                continue
            s = 2 if remix_tag(it["name"]) == want_r else 0  # mesma versao (original x remix)
            scored.append((s, it["uri"]))
        if scored:
            best = max(scored)[1]
            break
    os.makedirs(SEARCH_CACHE, exist_ok=True)
    json.dump({"uri": best}, open(path, "w"))
    return best


# ---------------- playlists ----------------
def upsert_playlist(state, name, description, uris):
    pid = state.get(name)
    if pid:
        api("PUT", f"/playlists/{pid}/items", body={"uris": uris[:100]})  # substitui
        for i in range(100, len(uris), 100):
            api("POST", f"/playlists/{pid}/items", body={"uris": uris[i:i + 100]})
        api("PUT", f"/playlists/{pid}", body={"description": description})
        return pid, "atualizada"
    pl = api("POST", "/me/playlists", body={"name": name, "description": description, "public": False})
    pid = pl["id"]
    state[name] = pid
    for i in range(0, len(uris), 100):
        api("POST", f"/playlists/{pid}/items", body={"uris": uris[i:i + 100]})
    return pid, "criada"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["recs", "liked", "login"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min", type=int, default=5)
    ap.add_argument("--only", default="")
    ap.add_argument("--cached-only", action="store_true", help="nao faz buscas novas (usa so o cache)")
    args = ap.parse_args()
    CACHED_ONLY[0] = args.cached_only
    only = {g.strip() for g in args.only.split(",") if g.strip()}

    if args.mode == "login":
        _tok[0] = get_token()
        print("Logado como:", api("GET", "/me").get("display_name"))
        return

    groups = defaultdict(list)
    missing = []
    if args.mode == "recs":
        rows = list(csv.DictReader(open(os.path.join(ROOT, "output", "recomendacoes_lastfm.csv"), encoding="utf-8")))
        rows = [r for r in rows if r["Subgenero"] not in SKIP and (not only or r["Subgenero"] in only)]
        print(f"Buscando {len(rows)} faixas no Spotify...", flush=True)
        pending = 0
        for i, r in enumerate(rows, 1):
            try:
                uri = find_track(r["Artista"], r["Musica"])
            except NotCached:
                pending += 1
                continue
            if uri:
                groups[r["Subgenero"]].append(uri)
            else:
                missing.append(r)
            if i % 100 == 0:
                print(f"  {i}/{len(rows)} · não encontradas: {len(missing)}", flush=True)
        if pending:
            print(f"{pending} ainda não buscadas (ficam para a próxima execução)")
        prefix, desc = "Descobertas – ", "Recomendações Last.fm a partir das suas curtidas ({}). Gerada por script."
    else:
        rows = list(csv.DictReader(open(os.path.join(ROOT, "output", "curtidas_classificadas.csv"), encoding="utf-8")))
        for r in sorted(rows, key=lambda r: float(r["BPM"] or 0)):
            if r["Subgenero"] not in SKIP and (not only or r["Subgenero"] in only):
                groups[r["Subgenero"]].append(r["Track URI"])
        prefix, desc = "Curtidas – ", "Suas curtidas classificadas como {} (ordem de BPM). Gerada por script."

    state = json.load(open(STATE_PATH)) if os.path.exists(STATE_PATH) else {}
    for g in sorted(groups):
        uris = list(dict.fromkeys(groups[g]))
        if len(uris) < args.min:
            continue
        name = prefix + g
        if args.dry_run:
            print(f"[dry-run] {name}: {len(uris)} faixas")
            continue
        _, what = upsert_playlist(state, name, desc.format(g), uris)
        print(f"{name}: {len(uris)} faixas ({what})", flush=True)
        json.dump(state, open(STATE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    if missing:
        path = os.path.join(ROOT, "output", "spotify_nao_encontradas.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(missing[0].keys()))
            w.writeheader()
            w.writerows(missing)
        print(f"{len(missing)} não encontradas no Spotify -> {path}")


if __name__ == "__main__":
    main()
