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

# ── PORTTI: jonorivin pakolliset kentät (lisätty 2026-09-29). julkaise.py ja
# paikallinen ajastin ohittavat HILJAA rivin jonka tila ei ole "odottaa" —
# myös rivin jolta tila puuttuu kokonaan. Mitattu 28.9. (j25-k1): käsin
# kirjoitetusta rivistä puuttui tila, push onnistui ja klippi myöhästyi 1 h 7 min
# ilman yhtään virheilmoitusta. Tarkistetaan committoitu HEAD, koska se lähtee.
if ! git -C "$DIR" show HEAD:jono.json | python3 -c '
import json, sys
from datetime import datetime
try:
    jono = json.load(sys.stdin)
except Exception as e:
    print(f"  jono.json ei ole kelvollista JSONia: {e}"); sys.exit(1)
viat, idt = [], set()
for i, r in enumerate(jono):
    tunnus = r.get("id") or f"rivi {i+1}"
    if not r.get("id"): viat.append(f"{tunnus}: id puuttuu")
    elif r["id"] in idt: viat.append(f"{tunnus}: sama id kahdesti")
    idt.add(r.get("id"))
    tila, aika = r.get("tila"), r.get("aika")
    if tila not in ("odottaa", "julkaistu", "virhe"):
        viat.append(f"{tunnus}: tila = {tila!r} (pitää olla odottaa, julkaistu tai virhe)")
    if not r.get("tili"): viat.append(f"{tunnus}: tili puuttuu")
    try:
        if datetime.fromisoformat(r["aika"]).tzinfo is None:
            viat.append(f"{tunnus}: aika ilman aikavyöhykettä (+03:00)")
    except Exception:
        viat.append(f"{tunnus}: aika puuttuu tai ei aukea: {aika!r}")
    if not (r.get("video") or r.get("video_url") or r.get("kuva")):
        viat.append(f"{tunnus}: ei videota, video_urlia eikä kuvaa")
for v in viat: print("  " + v)
sys.exit(1 if viat else 0)
' >&2; then
  echo "✗ Jonossa on rivi jota ajastin ei julkaisisi — EI TYÖNNETTY MITÄÄN. Korjaa, committoi ja aja uudelleen." >&2
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
