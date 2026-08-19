#!/usr/bin/env python3
"""
Vie paikallinen mp4 julkiseen osoitteeseen GitHub Release -liitteenä, jotta
julkaise.py voi antaa sen Metalle video_url-parametrina.

    python3 laheta_video.py <video.mp4> [tagi]      # vie ja tulostaa jonokentän
    python3 laheta_video.py --poista <tagi>/<tiedosto.mp4>

Miksi Release-liite eikä repo: 40–60 MB video jäisi julkiseen git-historiaan
pysyvästi. Liite ei kasvata repoa, ja Meta seuraa GitHubin 302-uudelleenohjauksen
allekirjoitettuun osoitteeseen [mitattu 2026-08-19].

Liite on POISTETTAVISSA heti kun postaus on julkaistu: Instagram hakee median
kerran ja tallentaa oman kopionsa (sama kuin kuvat/ — todennettu 08-08).

GH_TOKEN luetaan tämän kansion .env:stä, ei tulostu.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = "8429t4m98y-blip/cdb-julkaisin"
API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"
HERE = os.path.dirname(os.path.abspath(__file__))
OLETUSTAGI = "media"


def token():
    env_path = os.path.join(HERE, ".env")
    if not os.path.exists(env_path):
        sys.exit(f"✗ .env ei löytynyt: {env_path}")
    for line in open(env_path, encoding="utf-8"):
        if line.strip().startswith("GH_TOKEN="):
            return line.strip().partition("=")[2].strip()
    sys.exit("✗ GH_TOKEN puuttuu .env:stä.")


def api(method, url, data=None, headers=None, raw=False, salli=()):
    """salli = HTTP-koodit joista palautetaan None sen sijaan että pysähdyttäisiin."""
    h = {"Authorization": f"Bearer {token()}", "Accept": "application/vnd.github+json"}
    h.update(headers or {})
    body = data if raw else (json.dumps(data).encode() if data is not None else None)
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            teksti = r.read()
            return json.loads(teksti) if teksti else {}
    except urllib.error.HTTPError as e:
        if e.code in salli:
            return None
        sys.exit(f"✗ GitHub {method} {url.split('?')[0]} → {e.code}: {e.read().decode()[:300]}")


def hae_tai_luo_release(tagi):
    rel = api("GET", f"{API}/repos/{REPO}/releases/tags/{urllib.parse.quote(tagi)}", salli=(404,))
    if rel:
        return rel
    return api("POST", f"{API}/repos/{REPO}/releases", {
        "tag_name": tagi,
        "name": f"Media: {tagi}",
        "body": "Julkaisujonon mediatiedostot. Meta hakee nämä itse; liite voi poistua julkaisun jälkeen.",
        "prerelease": True,
    })


def julkinen_osoite(tagi, nimi):
    return (f"https://github.com/{REPO}/releases/download/"
            f"{urllib.parse.quote(tagi)}/{urllib.parse.quote(nimi)}")


def vie(polku, tagi):
    if not os.path.isfile(polku):
        sys.exit(f"✗ tiedostoa ei ole: {polku}")
    nimi = os.path.basename(polku)
    if nimi != nimi.encode("ascii", "ignore").decode() or " " in nimi:
        sys.exit(f"✗ tiedostonimessä on välilyönti tai ääkkösiä: {nimi!r} — nimeä uudelleen.")
    koko = os.path.getsize(polku)

    rel = hae_tai_luo_release(tagi)
    if any(a["name"] == nimi for a in rel.get("assets", [])):
        sys.exit(f"✗ liite {nimi!r} on jo tagissa {tagi!r}. Poista ensin: "
                 f"python3 laheta_video.py --poista {tagi}/{nimi}")

    print(f"→ Viedään {nimi} ({koko / 1_000_000:.1f} MB) → release {tagi} …")
    with open(polku, "rb") as f:
        res = api("POST",
                  f"{UPLOADS}/repos/{REPO}/releases/{rel['id']}/assets?name={urllib.parse.quote(nimi)}",
                  data=f.read(), headers={"Content-Type": "video/mp4"}, raw=True)
    if res.get("state") != "uploaded":
        sys.exit(f"✗ lataus ei valmistunut: {res.get('state')}")

    # Todennetaan että Meta pystyy hakemaan sen — julkinen, ilman kirjautumista.
    osoite = julkinen_osoite(tagi, nimi)
    try:
        with urllib.request.urlopen(urllib.request.Request(osoite, headers={"Range": "bytes=0-1023"})) as r:
            koodi = r.status
    except urllib.error.HTTPError as e:
        sys.exit(f"✗ julkinen osoite ei vastaa ({e.code}): {osoite}")
    print(f"  ✓ julkinen osoite vastaa ({koodi}): {osoite}")
    print(f"\nLisää jonoriville:\n  \"video\": \"{tagi}/{nimi}\"")


def poista(viite):
    tagi, _, nimi = viite.partition("/")
    if not nimi:
        sys.exit("✗ anna muodossa <tagi>/<tiedosto.mp4>")
    rel = api("GET", f"{API}/repos/{REPO}/releases/tags/{urllib.parse.quote(tagi)}")
    for a in rel.get("assets", []):
        if a["name"] == nimi:
            api("DELETE", f"{API}/repos/{REPO}/releases/assets/{a['id']}")
            print(f"✓ poistettu liite {nimi} tagista {tagi}")
            return
    sys.exit(f"✗ liitettä {nimi!r} ei ole tagissa {tagi!r}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__.strip())
    if sys.argv[1] == "--poista":
        poista(sys.argv[2])
    else:
        vie(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else OLETUSTAGI)
