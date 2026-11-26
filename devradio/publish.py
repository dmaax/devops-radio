#!/usr/bin/env python3
"""Publica a DevOps Radio do dia na conta dedicada (nao na sua conta pessoal).

Uso:
  python3 devradio/publish.py login            # login da conta DevOps Radio (token separado)
  python3 devradio/publish.py whoami           # confere qual conta esta logada
  python3 devradio/publish.py publish          # monta a playlist de hoje e atualiza no Spotify
  python3 devradio/publish.py publish --date 2026-12-02 --dry-run

Token: data/cache/spotify_token_devradio.json (ou env SPOTIFY_REFRESH_TOKEN, para GitHub Actions).
Estado (id da playlist): devradio/state.json · historico: devradio/history.json
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, HERE)

import spotify_playlists as sp  # noqa: E402  (reaproveita auth/api)
import generate  # noqa: E402

sp.TOKEN_PATH = os.path.join(ROOT, "data", "cache", "spotify_token_devradio.json")
sp.SCOPES = "playlist-modify-public playlist-modify-private playlist-read-private ugc-image-upload"
STATE = os.path.join(HERE, "state.json")

# em CI: refresh token via variavel de ambiente
if os.environ.get("SPOTIFY_REFRESH_TOKEN") and not os.path.exists(sp.TOKEN_PATH):
    sp.save_token({"refresh_token": os.environ["SPOTIFY_REFRESH_TOKEN"], "access_token": "", "expires_at": 0})


def whoami():
    me = sp.api("GET", "/me")
    print(f"Conta: {me.get('display_name')} (id {me.get('id')})")
    return me


def publish(date, dry_run):
    cfg = json.load(open(generate.CONFIG, encoding="utf-8"))
    theme = cfg["days"][str(date.weekday())]
    lib = generate.load_library()
    history = generate.load_history()
    history.pop(date.isoformat(), None)  # republicar no mesmo dia gera a mesma lista
    tracks, pool, relax = generate.build_day(lib, cfg, theme, date, history)
    name = f"{cfg['playlist_name']} · {theme['title']}"
    genres = [g for g, _ in Counter(t["genre"] for t in tracks).most_common()]
    desc = f"Hoje: {', '.join(genres)}. Atualizada todo dia."
    if cfg.get("repo_url"):
        desc += f" {cfg['repo_url']}"
    print(f"{name}\n{desc}")
    if dry_run:
        for t in tracks[:10]:
            print(f"  {t['bpm']:.0f} {t['camelot']:>3}  {t['artists'].replace(';', ', ')} - {t['title']}")
        return

    me = whoami()
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    uris = [t["uri"] for t in tracks]
    pid = state.get("playlist_id")
    if pid:
        sp.api("PUT", f"/playlists/{pid}", body={"name": name, "description": desc, "public": True})
        sp.api("PUT", f"/playlists/{pid}/items", body={"uris": uris[:100]})
        for i in range(100, len(uris), 100):
            sp.api("POST", f"/playlists/{pid}/items", body={"uris": uris[i:i + 100]})
        print("Playlist atualizada")
    else:
        pl = sp.api("POST", "/me/playlists", body={"name": name, "description": desc, "public": True})
        pid = pl["id"]
        for i in range(0, len(uris), 100):
            sp.api("POST", f"/playlists/{pid}/items", body={"uris": uris[i:i + 100]})
        state = {"playlist_id": pid, "owner": me.get("id"), "created": date.isoformat()}
        print("Playlist criada")
    state["last_published"] = date.isoformat()
    json.dump(state, open(STATE, "w"), indent=1)

    history[date.isoformat()] = uris
    cutoff = (date - dt.timedelta(days=90)).isoformat()
    history = {d: u for d, u in history.items() if d >= cutoff}
    json.dump(history, open(generate.HISTORY, "w"), indent=0)
    print(f"https://open.spotify.com/playlist/{pid}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["login", "whoami", "publish"])
    ap.add_argument("--date")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.mode == "login":
        if os.path.exists(sp.TOKEN_PATH):
            os.remove(sp.TOKEN_PATH)
        sp._tok[0] = sp.login()
        whoami()
    elif args.mode == "whoami":
        whoami()
    else:
        publish(dt.date.fromisoformat(args.date) if args.date else dt.date.today(), args.dry_run)


if __name__ == "__main__":
    main()
