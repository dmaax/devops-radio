# DevOps Radio 📻

Playlist do Spotify para devs/devops que **muda todo dia** conforme o dia da semana:

| Dia | Tema |
|---|---|
| Segunda | Aquecendo a sprint ☕ — organic house / downtempo |
| Terça | Deep focus 🎧 — minimal, deep tech, deep house instrumental |
| Quarta | On-call 🔥 — techno peak time |
| Quinta | Flow state 🌊 — melodic house & techno, progressive |
| Sexta | Sem deploy hoje 🪩 — house, nu disco, indie dance |
| Sáb/Dom | Side project 🛠️ — ambient, electronica, downtempo |

▶️ **[Ouvir no Spotify](https://open.spotify.com/playlist/7D7kQLmpgm0OjGukyzmdDZ)** · 🌐 **[Site com a playlist do dia](https://radio.dmaax.pro)**

## Como funciona

- `devradio/library.csv` — biblioteca de faixas eletrônicas classificadas por subgênero (taxonomia Beatport), com BPM, tom (Camelot), energia e instrumentalidade.
- `devradio/config.json` — temas de cada dia (subgêneros, faixa de BPM, energia, quanto de voz é aceitável).
- `devradio/generate.py` — escolhe ~40 faixas do tema, no máximo 2 por artista, ordenadas por BPM, sem repetir o que tocou nos últimos 28 dias. Mesma data → mesma playlist.
- `devradio/publish.py` — atualiza a playlist no Spotify.
- `docs/` — site estático (GitHub Pages) que mostra a playlist do dia; os dados ficam em `docs/data/`.
- `.github/workflows/devradio.yml` — roda todo dia às 06:00 (Brasília) e salva o histórico no repo.

Prévia local da semana: `python3 devradio/generate.py --week`

A classificação da biblioteca vem de `scripts/` (Exportify → tags de gênero + estilos do Discogs + BPM).

## Quer fazer a sua?

Veja o passo a passo em **[COMO-FAZER.md](COMO-FAZER.md)**: fork, classificação da sua biblioteca, conta dedicada no Spotify, GitHub Actions e site com domínio próprio.
