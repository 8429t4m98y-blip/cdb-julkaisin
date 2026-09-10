#!/usr/bin/env python3
"""
Todentaa vaihe 5:n MOLEMMAT päät erikseen — ei `viimeistele.py`:n omasta
tulosteesta vaan elävistä lähteistä.

    python3 todenna_siivous.py --id era-k9

Miksi erillinen skripti: `viimeistele.py` on kertaalleen raportoinut
"✅ liite poistettu" liitteelle joka löytyi Releasesta 4 vrk myöhemmin
[08-23 j19-k7]. Ajon oma tuloste ei siis ole todiste.

Kaksi ansaa jotka tämä kiertää:
  ① Paikallinen `jono.json` on normaalisti jäljessä ⇒ rivi luetaan
    **origin/main:sta**, ei levyltä.
  ② Ennen ajoa haettu allekirjoitettu asset-URL pysyy voimassa vaikka liite on
    poistettu, ja `curl -L` seuraa sen läpi ⇒ näyttää 200:aa vaikka poisto
    onnistui [mitattu 09-04]. Siksi liite tarkistetaan **GitHub-API:sta**
    (assets-lista) ja julkinen osoite vain cache-bust-parametrilla ILMAN
    redirectin seuraamista.

Poistumiskoodit:
  0 = MOLEMMAT PÄÄT PUHTAAT — jonorivi poissa JA liite poissa ⇒ rivi voidaan
      kirjata kiinni
  2 = EI VIELÄ — jonorivi on yhä tilassa "odottaa" (klippi ei ole ulkona)
  3 = KESKEN — jompikumpi pää jäi: rivi poissa mutta liite jäljellä, tai
      päinvastoin. Aja `viimeistele.py --id <id>` uudelleen.
  4 = EI VOITU TODENTAA — fetch, API tai videopolun johtaminen epäonnistui.
      ⛔ Tämä EI ole puhdas tuomio.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = "8429t4m98y-blip/cdb-julkaisin"
API = "https://api.github.com"


def token():
    env_path = os.path.join(HERE, ".env")
    if not os.path.exists(env_path):
        sys.exit(f"✗ .env ei löytynyt: {env_path}")
    for line in open(env_path, encoding="utf-8"):
        if line.strip().startswith("GH_TOKEN="):
            return line.strip().partition("=")[2].strip()
    sys.exit("✗ GH_TOKEN puuttuu .env:stä.")


def git(*args):
    r = subprocess.run(["git", "-C", HERE, *args], capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def jono_originista():
    koodi, ulos, virhe = git("show", "origin/main:jono.json")
    if koodi:
        return None, virhe.strip()
    try:
        return json.loads(ulos), None
    except json.JSONDecodeError as e:
        return None, f"origin/main:jono.json ei jäsenny: {e}"


def etsi_video(tunnus, jono):
    """Videopolku jonosta; jos rivi on jo poistettu, kävellään historiaa."""
    for rivi in (jono or []):
        if rivi.get("id") == tunnus and rivi.get("video"):
            return rivi["video"], "origin/main"
    koodi, ulos, _ = git("log", "--format=%H", "-n", "40", "origin/main", "--", "jono.json")
    if koodi:
        return None, None
    for commit in ulos.split():
        k, teksti, _ = git("show", f"{commit}:jono.json")
        if k:
            continue
        try:
            vanha = json.loads(teksti)
        except json.JSONDecodeError:
            continue
        for rivi in vanha:
            if rivi.get("id") == tunnus and rivi.get("video"):
                return rivi["video"], commit[:8]
    return None, None


def liitteet(tagi):
    url = f"{API}/repos/{REPO}/releases/tags/{urllib.parse.quote(tagi)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token()}",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req) as r:
            return [a["name"] for a in json.loads(r.read()).get("assets", [])], None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return [], None          # koko releasea ei ole ⇒ ei liitteitä
        return None, f"GitHub-API {e.code}"
    except OSError as e:
        return None, f"GitHub-API ei vastannut: {e}"


def julkinen_koodi(tagi, nimi):
    """HTTP-koodi ILMAN redirectin seuraamista, cache-bustilla. 404 = poissa."""
    url = (f"https://github.com/{REPO}/releases/download/"
           f"{urllib.parse.quote(tagi)}/{urllib.parse.quote(nimi)}?cb={int(time.time())}")

    class EiOhjausta(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    avaaja = urllib.request.build_opener(EiOhjausta)
    try:
        with avaaja.open(urllib.request.Request(url, method="HEAD"), timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--id", dest="tunnus", required=True)
    p.add_argument("--video", help="media/tiedosto.mp4 — vain jos johtaminen ei onnistu")
    a = p.parse_args()

    koodi, _, virhe = git("fetch", "origin", "--quiet")
    if koodi:
        print(f"✗ EI VOITU TODENTAA — fetch epäonnistui: {virhe.strip()}")
        return 4

    jono, virhe = jono_originista()
    if jono is None:
        print(f"✗ EI VOITU TODENTAA — {virhe}")
        return 4

    rivi = next((r for r in jono if r.get("id") == a.tunnus), None)
    if rivi is not None and rivi.get("tila") != "julkaistu":
        print(f"⏳ EI VIELÄ — jonorivi '{a.tunnus}' on tilassa '{rivi.get('tila')}' "
              f"(aika {rivi.get('aika')}). Klippi ei ole ulkona; älä aja viimeistelyä.")
        return 2

    rivi_poissa = rivi is None
    video = a.video
    lahde = "--video"
    if not video:
        video, lahde = etsi_video(a.tunnus, jono)
    if not video:
        print(f"✗ EI VOITU TODENTAA — videopolkua ei saatu johdettua id:lle '{a.tunnus}'. "
              f"Anna se käsin: --video media/<tiedosto>.mp4")
        return 4

    tagi, _, nimi = video.partition("/")
    if not nimi:
        tagi, nimi = "media", video

    nimet, virhe = liitteet(tagi)
    if nimet is None:
        print(f"✗ EI VOITU TODENTAA — {virhe}")
        return 4
    liite_poissa = nimi not in nimet
    http = julkinen_koodi(tagi, nimi)

    print(f"id            : {a.tunnus}")
    print(f"videopolku    : {video}   (lähde: {lahde})")
    print(f"① jonorivi     : {'POISSA ✅' if rivi_poissa else 'JÄLJELLÄ ❌'}  "
          f"(origin/main:jono.json, {len(jono)} riviä)")
    print(f"② liite (API)  : {'POISSA ✅' if liite_poissa else 'JÄLJELLÄ ❌'}  "
          f"(releases/tags/{tagi}: {len(nimet)} liitettä)")
    print(f"③ julkinen URL : HTTP {http}  "
          f"{'✅ (404 = poissa)' if http == 404 else '⚠️ (302/200 = liite vastaa yhä)'}"
          f"{'  ⛔ ei saatu yhteyttä' if http is None else ''}")

    if rivi_poissa and liite_poissa:
        if http != 404:
            print("\n⚠️ API sanoo POISSA mutta julkinen osoite vastaa yhä — "
                  "todennäköisesti GitHubin reunavälimuisti. API on ratkaiseva.")
        print("\n✅ MOLEMMAT PÄÄT PUHTAAT — rivi voidaan kirjata kiinni.")
        return 0

    print(f"\n❌ KESKEN — jonorivi {'poissa' if rivi_poissa else 'JÄLJELLÄ'}, "
          f"liite {'poissa' if liite_poissa else 'JÄLJELLÄ'}. "
          f"Aja: python3 viimeistele.py --id {a.tunnus}")
    return 3


if __name__ == "__main__":
    sys.exit(main())
