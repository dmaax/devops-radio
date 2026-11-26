# Como fazer a sua própria rádio

Guia para montar uma playlist do Spotify que **muda todo dia conforme o dia da semana**, a partir da **sua** biblioteca, com publicação automática pelo GitHub Actions e um site no GitHub Pages, igual à [DevOps Radio](https://radio.dmaax.pro).

Tempo estimado: ~1 hora na primeira vez, quase tudo esperando scripts rodarem.

## O que você vai precisar

- **Spotify Premium** na sua conta pessoal. Desde fevereiro de 2026, o Spotify exige Premium para o dono de apps em modo desenvolvedor.
- **Uma segunda conta Spotify** (grátis), que vai ser a dona da playlist. Assim a rádio não fica no seu nome.
- **Python 3.10+**. Os scripts não têm dependências; o Pillow só é usado para gerar a capa em JPEG.
- **Conta no GitHub**. O [`gh`](https://cli.github.com/) ajuda, mas é opcional.
- **Opcional:** API key do [Last.fm](https://www.last.fm/api/account/create) e token do [Discogs](https://www.discogs.com/settings/developers), para melhorar a classificação e gerar recomendações.

## Visão geral

```
Exportify (CSV da sua biblioteca)
   └─ scripts/classify.py ........ classifica cada faixa em subgênero (taxonomia Beatport) + BPM, Camelot
        └─ devradio/generate.py .. escolhe ~40 faixas do tema do dia → devradio/library.csv
             └─ devradio/publish.py  atualiza a playlist na conta da rádio + gera docs/data (site)
                  └─ GitHub Actions: roda todo dia às 06:00 e faz commit do histórico
                  └─ GitHub Pages: publica docs/ (site com a playlist do dia)
```

## 1. Faça um fork e limpe o que é da DevOps Radio

```bash
gh repo fork dmaax/devops-radio --clone && cd devops-radio
# ou: fork pelo site do GitHub + git clone

# remove o estado da rádio original (id da playlist, histórico, site, domínio)
rm -f devradio/state.json devradio/history.json docs/CNAME
rm -rf docs/data
```

No `devradio/config.json`, troque:
- `playlist_name`: o nome da sua rádio;
- `repo_url`: o endereço do **seu** repositório ou site. Ele aparece na descrição da playlist e no rodapé do site;
- os **temas de cada dia** (veja o passo 5).

No `README.md`, troque os links da playlist e do site pelos seus.

## 2. Exporte e classifique a sua biblioteca

> Pode pular este passo e usar o `devradio/library.csv` que já vem no repositório, mas aí a rádio toca a biblioteca da DevOps Radio, não a sua.

1. Entre no [Exportify](https://exportify.net), faça login com a **sua conta pessoal** e clique em **Export All**.
2. Extraia o zip em `data/spotify_raw/`:
   ```bash
   mkdir -p data/spotify_raw && unzip spotify_playlists.zip -d data/spotify_raw
   ```
3. *(Opcional, ~40–60 min para 2.500 músicas curtidas)* Busque os estilos do Discogs, que descrevem o lançamento e não só o artista:
   ```bash
   echo 'DISCOGS_TOKEN=seu_token' >> .env
   python3 scripts/discogs_enrich.py
   ```
4. Classifique:
   ```bash
   python3 scripts/classify.py
   ```
   Isso gera `output/curtidas_classificadas.csv`, `output/todas_faixas.csv` e `output/resumo.md`, com o seu perfil por subgênero.
5. Gere a biblioteca enxuta que o GitHub Actions usa:
   ```bash
   python3 devradio/generate.py --export-library
   ```

`data/`, `output/` e `.env` estão no `.gitignore`: nenhum dado bruto nem chave vai para o repositório. **O `devradio/library.csv` vai.** Ele lista as faixas da sua biblioteca e quais você curtiu; se não quiser isso público, deixe o repositório privado. O Pages funciona com repositório privado só nos planos pagos do GitHub.

## 3. Crie o app no Spotify

1. Acesse [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) logado com a **sua conta pessoal** (Premium) e clique em **Create app**.
2. Em **Redirect URI**, coloque `http://127.0.0.1:8888/callback`.
3. Em **APIs used**, marque **Web API**.
4. Copie o Client ID e o Client Secret para o `.env`:
   ```bash
   echo 'SPOTIFY_CLIENT_ID=...' >> .env
   echo 'SPOTIFY_CLIENT_SECRET=...' >> .env
   chmod 600 .env
   ```

## 4. Crie a conta da rádio e faça o login dela

1. Crie uma conta Spotify nova, de preferência pelo site (spotify.com/signup), com e-mail. Coloque o nome de exibição da rádio e uma foto (há um avatar em `devradio/assets/avatar.svg` para usar de base).
2. No dashboard do app, vá em **User Management** e adicione o **e-mail da conta nova**. Sem isso, a API responde 403.
3. Abra uma **janela anônima** e entre em open.spotify.com com a conta **da rádio**. No terminal, rode:
   ```bash
   python3 devradio/publish.py login
   ```
   Abra o link que aparecer **nessa janela anônima** e autorize. O navegador vai para `http://127.0.0.1:8888/callback?...`.
   - **Na mesma máquina:** a página mostra "Pronto!" e o login termina sozinho.
   - **Por SSH ou WSL:** a página dá erro de conexão. Isso é esperado. Copie a URL inteira da barra de endereço e, **na máquina onde o script está rodando**, entregue-a ao script:
     ```bash
     curl 'http://127.0.0.1:8888/callback?code=...&state=...'
     ```
4. Confira se entrou com a conta certa. O nome mostrado tem que ser o da rádio, não o seu:
   ```bash
   python3 devradio/publish.py whoami
   ```

## 5. Ajuste os temas e veja a prévia

Cada dia em `devradio/config.json` (`"0"` = segunda … `"6"` = domingo) tem:

| Campo | O que faz |
|---|---|
| `title` / `description` | Nome da playlist no dia e texto do site |
| `genres` | Subgêneros aceitos (os nomes de `output/resumo.md`) |
| `bpm` | Faixa de BPM `[min, max]` |
| `energy` | Faixa de energia `[0–1]` |
| `min_instrumental` | Quanto a faixa precisa ser instrumental (0–1). Bom para dias de foco |
| `max_speech` | Limite de voz falada |

E no topo do arquivo: `size` (faixas por dia), `max_per_artist`, `no_repeat_days` (dias sem repetir uma faixa) e `liked_bonus` (prioridade das curtidas).

```bash
python3 devradio/generate.py --week     # prévia dos próximos 7 dias em devradio/preview.md
```

Se algum dia tiver poucas faixas no tema, o gerador afrouxa os filtros sozinho e avisa na prévia.

## 6. Primeira publicação e capa

```bash
python3 devradio/publish.py publish     # cria a playlist pública e gera docs/data
```

O id da playlist fica salvo em `devradio/state.json`. As próximas execuções atualizam essa mesma playlist, sem criar outra.

Para a capa (JPEG de até 256 KB), edite `devradio/assets/cover.svg`, gere o `cover.jpg` e envie:

```bash
python3 -m venv .venv && .venv/bin/pip install pillow
# renderize o SVG para devradio/assets/cover.jpg (640×640), por exemplo com
# rsvg-convert -w 640 cover.svg | .venv/bin/python -c "import sys;from PIL import Image;Image.open(sys.stdin.buffer).convert('RGB').save('devradio/assets/cover.jpg',quality=90)"
python3 devradio/publish.py cover
cp devradio/assets/cover.jpg docs/cover.jpg
```

## 7. Agende no GitHub Actions

O workflow `.github/workflows/devradio.yml` já está pronto: roda todo dia às **09:00 UTC** (06:00 em Brasília; mude o `cron` para o seu fuso), publica a playlist e faz commit de `devradio/history.json`, `devradio/state.json` e `docs/data`.

1. Cadastre os 3 secrets no repositório (**Settings → Secrets and variables → Actions**) ou pelo `gh`:
   ```bash
   gh secret set SPOTIFY_CLIENT_ID      # cole o valor
   gh secret set SPOTIFY_CLIENT_SECRET  # cole o valor
   python3 -c "import json,sys;sys.stdout.write(json.load(open('data/cache/spotify_token_devradio.json'))['refresh_token'])" \
     | gh secret set SPOTIFY_REFRESH_TOKEN
   ```
2. Faça commit e push do que mudou: `config.json`, `library.csv`, `state.json`, `history.json`, `docs/`.
3. **Em forks, o GitHub desativa workflows agendados.** Abra a aba **Actions** e clique em **I understand my workflows, go ahead and enable them**.
4. Teste: **Actions → DevOps Radio → Run workflow**.

Se um dia o workflow falhar com erro de autenticação, o refresh token deixou de valer. Rode `publish.py login` de novo e atualize o secret `SPOTIFY_REFRESH_TOKEN`.

## 8. Site no GitHub Pages

1. **Settings → Pages → Build and deployment:** *Deploy from a branch*, branch `main`, pasta `/docs`.
   ```bash
   gh api -X POST repos/SEU_USUARIO/SEU_REPO/pages -f "source[branch]=main" -f "source[path]=/docs"
   ```
2. O site fica em `https://SEU_USUARIO.github.io/SEU_REPO/` e é atualizado a cada commit do workflow.

### Domínio próprio (ex.: Cloudflare)

1. **Verifique o domínio** em github.com → **Settings (da conta) → Pages → Add a domain**. Informe o domínio principal (`seudominio.com`) e crie na Cloudflare o registro TXT que o GitHub mostrar.
2. Na Cloudflare, crie um **CNAME** `radio` → `SEU_USUARIO.github.io` com **proxy desligado (nuvem cinza)**. Com o proxy ligado, o GitHub não consegue emitir o certificado HTTPS.
3. Coloque o domínio em `docs/CNAME` (ex.: `radio.seudominio.com`), faça push e configure:
   ```bash
   gh api -X PUT repos/SEU_USUARIO/SEU_REPO/pages -f cname=radio.seudominio.com
   # quando o certificado sair (minutos até ~1h):
   gh api -X PUT repos/SEU_USUARIO/SEU_REPO/pages -F https_enforced=true
   ```

## Extras (opcionais)

Estes scripts são para a sua conta pessoal, não para a rádio:

| Comando | O que faz |
|---|---|
| `python3 scripts/lastfm_recs.py` | Recomendações por subgênero via Last.fm, sem faixas que você já tem (precisa de `LASTFM_API_KEY`) |
| `python3 scripts/spotify_playlists.py recs` | Cria playlists privadas "Descobertas – <subgênero>" na **sua** conta |
| `python3 scripts/spotify_playlists.py liked` | Cria "Curtidas – <subgênero>", ordenadas por BPM |

`spotify_playlists.py` usa outro login, o da sua conta pessoal (`python3 scripts/spotify_playlists.py login`), salvo em `data/cache/spotify_token.json`.

## Limites do Spotify que vale conhecer

- **Modo desenvolvedor:** dono do app com Premium, até 5 usuários em User Management, e endpoints novos: `POST /me/playlists`, `/playlists/{id}/items`.
- **Busca (`/search`):** no máximo 10 resultados por chamada. Muitas buscas seguidas podem gerar um bloqueio de **~24 h** só da busca. Os scripts guardam as respostas em cache e fazem pausas, mas evite rodar várias vezes seguidas. A rádio em si não faz buscas.
- **Recomendações, audio features e related artists** foram fechados para apps novos em 2024. Por isso o BPM e a energia vêm do Exportify, e as recomendações vêm do Last.fm.
