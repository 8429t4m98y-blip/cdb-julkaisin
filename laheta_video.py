#!/usr/bin/env python3
"""
Vie paikallinen mp4 julkiseen osoitteeseen GitHub Release -liitteenä, jotta
julkaise.py voi antaa sen Metalle video_url-parametrina.

    python3 laheta_video.py <video.mp4> [tagi]      # vie ja tulostaa jonokentän
    python3 laheta_video.py --poista <tagi>/<tiedosto.mp4>

Miksi Release-liite eikä repo: 40–60 MB video jäisi julkiseen git-historiaan
pysyvästi. Liite ei kasvata repoa, ja Meta seuraa GitHubin 302-uudelleenohjauksen
allekirjoitettuun osoitteeseen [mitattu 2026-08-19].

SÄÄNTÖ — milloin liite saa poistua: vasta kun sen jonorivi on tilassa
"julkaistu", ja samassa vaiheessa kuin rivi poistetaan jono.json:sta (vaihe 5).
EI aiemmin: uusinta hakee videon samasta osoitteesta, ja poistettu liite antaa
404:n → klippi jää julkaisematta hiljaa. Julkaisun jälkeen poisto on turvallinen,
koska Instagram hakee median kerran ja tallentaa oman kopionsa (kuten kuvat/ —
todennettu 08-08). --poista tarkistaa tämän itse **origin/mainin** jono.json:sta
(ei paikallisesta — tämä klooni on normaalisti jäljessä, ks. §jonovahti).
Jo poistettu liite ei ole virhe: --poista on idempotentti, jotta vaihe 5:n
kesken jäänyt siivous voidaan ajaa loppuun samalla komennolla.

GH_TOKEN luetaan tämän kansion .env:stä, ei tulostu.
"""
import json
import os
import subprocess
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


def _tulkitse_jono(teksti, mista):
    try:
        data = json.loads(teksti)
    except ValueError:
        sys.exit(f"✗ jono.json ({mista}) ei ole luettavissa — en poista liitettä sokkona.")
    return data if isinstance(data, list) else []


def _origin_jono():
    """jono.json GitHubin mainista — SAMA LÄHDE kuin viimeistele.py §etarivi().

    ⛔ Älä lue jonon tilaa paikallisesta tiedostosta. Tämä klooni on normaalisti
    jäljessä, koska paikallinen-ajastin ja cdb-julkaisin-botti committaavat
    originiin sen ulkopuolelta: vahti näki rivin `odottaa` vaikka origin sanoi
    `julkaistu`, esti poiston 2 kertaa 10 ajossa ja MOLEMMILLA kerroilla jäi
    orpo liite [mitattu 08-30].
    """
    f = subprocess.run(["git", "-C", HERE, "fetch", "origin", "--quiet"],
                       capture_output=True, text=True)
    if f.returncode != 0:
        sys.exit("✗ git fetch epäonnistui — en lue vanhaa origin/mainia sokkona: "
                 f"{f.stderr.strip()[:200]}")
    r = subprocess.run(["git", "-C", HERE, "show", "origin/main:jono.json"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"✗ jono.json ei luettavissa originista: {r.stderr.strip()[:200]}")
    return _tulkitse_jono(r.stdout, "origin/main")


def _paikallinen_jono():
    jono_path = os.path.join(HERE, "jono.json")
    if not os.path.exists(jono_path):
        return []
    return _tulkitse_jono(open(jono_path, encoding="utf-8").read(), "paikallinen")


def jonovahti(viite):
    """Kieltäydy poistamasta liitettä jota jono yhä tarvitsee.

    Rivin tila luetaan **originista**. Paikallisesta katsotaan vain ne rivit
    joiden id:tä originissa EI vielä ole (= juuri lisätty, ei vielä pushattu),
    jotta tuore odottava rivi ei jää suojaamatta. Stale paikallinen kopio
    rivistä ei siis enää estä poistoa — origin ratkaisee.
    """
    origin = _origin_jono()
    origin_idt = {r.get("id") for r in origin if r.get("id")}
    tarkistettavat = list(origin) + [r for r in _paikallinen_jono()
                                     if r.get("id") not in origin_idt]
    for item in tarkistettavat:
        if item.get("video") == viite and item.get("tila") != "julkaistu":
            sys.exit(
                f"✗ jonossa on rivi {item.get('id')!r} tilassa "
                f"{item.get('tila')!r} joka viittaa tähän liitteeseen.\n"
                "  Uusinta hakee videon tästä osoitteesta — poisto tekisi siitä "
                "404:n ja klippi jäisi julkaisematta.\n"
                "  Poista vasta kun rivi on 'julkaistu' (vaihe 5), tai poista "
                "rivi ensin käsin."
            )


def poista(viite):
    tagi, _, nimi = viite.partition("/")
    if not nimi:
        sys.exit("✗ anna muodossa <tagi>/<tiedosto.mp4>")
    jonovahti(viite)
    rel = api("GET", f"{API}/repos/{REPO}/releases/tags/{urllib.parse.quote(tagi)}",
              salli=(404,))
    for a in (rel or {}).get("assets", []):
        if a["name"] == nimi:
            api("DELETE", f"{API}/repos/{REPO}/releases/assets/{a['id']}")
            print(f"✓ poistettu liite {nimi} tagista {tagi}")
            return
    # Poissa = ei tehtävää, EI virhe. Vaihe 5 uusii saman komennon kun siivous
    # jäi kesken (koodi 4); jo poistettu liite pysäyttäisi uusinnan ennen kuin
    # jonorivi ehditään poistaa, ja jättäisi rivin ikuisesti jonoon.
    print(f"✓ liitettä {nimi} ei ole tagissa {tagi} — jo poistettu, ei tehtävää")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__.strip())
    if sys.argv[1] == "--poista":
        poista(sys.argv[2])
    else:
        vie(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else OLETUSTAGI)
