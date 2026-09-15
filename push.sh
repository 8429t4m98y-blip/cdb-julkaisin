#!/usr/bin/env bash
# CDB-julkaisin — pysyvä push GitHubiin.
# Lukee GH_TOKEN:n TÄMÄN kansion omasta .env:stä, ei tallenna tokenia
# git-configiin eikä tulosta sitä. Työntää nykyisen mainin originiin,
# jonka jälkeen GitHub Actions -cron julkaisee erääntyneet postaukset.
#
# Eriytetty Instagram API:n .env:stä 2026-08-06 (Miikan päätös): yhdessä
# tiedostossa olivat sekä Metan julkaisutoken että GitHub-token, jolloin
# yhden tiedoston vuoto olisi kaatanut molemmat. Blast radius pienempi kun
# jokainen salaisuus asuu sen työn vieressä joka sitä käyttää.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$DIR/.env"
REPO="github.com/8429t4m98y-blip/cdb-julkaisin.git"

if [ ! -f "$ENV_FILE" ]; then
  echo "✗ .env ei löytynyt: $ENV_FILE" >&2; exit 1
fi

TOKEN="$(grep -E '^GH_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '[:space:]')"
if [ -z "${TOKEN:-}" ]; then
  echo "✗ GH_TOKEN puuttuu .env:stä. Lisää rivi: GH_TOKEN=github_pat_..." >&2; exit 1
fi

# ── PORTTI: committoimaton työ ei mene ulos, eikä ajo saa raportoida onnistumista
# sen yli. `git push HEAD:main` työntää viimeisimmän COMMITIN — levyllä oleva
# muokkaus ei ole sellainen, joten push onnistuu tyhjänä ja vanha tuloste sanoi
# silti "✓ Työnnetty GitHubiin". Mitattu 2026-09-15 kahdesti samana päivänä
# (j23 klipit 2 ja 4): jonorivi jäi paikalliseksi, mitään ei mennyt ulos, ja
# vika löytyi vain lukemalla origin/main takaisin. Skripti EI committaa
# puolestasi — se kieltäytyy, koska polkujen valinta on sinun (periaatteet.md §GIT).
LIKAINEN="$(git -C "$DIR" status --porcelain)"
if [ -n "$LIKAINEN" ]; then
  {
    echo "✗ Committoimatonta työtä — EI TYÖNNETTY MITÄÄN."
    echo "$LIKAINEN" | sed 's/^/    /'
    echo "  Committoi ensin ne polut jotka itse muutit:"
    echo "    git -C \"$DIR\" commit -m \"jono: …\" -- jono.json"
    echo "  Uusi tiedosto vaatii lisäyksen ensin: git -C \"$DIR\" add -- <polku>"
  } >&2
  exit 1
fi

echo "→ Haetaan origin ja työnnetään main …"
git -C "$DIR" fetch origin --quiet

# Toinen puoli samaa vikaa: no-op push ei ole julkaisu. Jos HEAD on jo
# originissa, sano se — älä kaiuta onnistumisriviä jonka lukija tulkitsee
# "jono lähti ulos".
if [ "$(git -C "$DIR" rev-parse HEAD)" = "$(git -C "$DIR" rev-parse origin/main)" ]; then
  echo "ℹ️  HEAD on jo sama kuin origin/main — ei mitään työnnettävää. Jono ei muuttunut."
  exit 0
fi

# Työnnä token-URL:lla; kaiutetaan vain onnistuminen, ei tokenia.
if git -C "$DIR" push "https://x-access-token:${TOKEN}@${REPO}" HEAD:main 2>/tmp/cdb_push_err; then
  echo "✓ Työnnetty GitHubiin. Erääntyneet postaukset lähtevät seuraavassa ajossa; pääherättäjä on Hostingerin cron 10 min välein (mitattu 31.8.). ⛔ Älä lupaa kellonaikaa - katso jonon tila: bash ~/Library/Application\ Support/julkaisin-ajastin/tila.sh"
else
  # Siivotaan mahdollinen token pois virheviestistä ennen näyttöä.
  sed "s#x-access-token:[^@]*@#x-access-token:***@#g" /tmp/cdb_push_err >&2
  rm -f /tmp/cdb_push_err
  exit 1
fi
rm -f /tmp/cdb_push_err
