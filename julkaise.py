#!/usr/bin/env python3
"""
CDB-julkaisin — DIY-ajastin Instagramiin.

Lukee jono.json:n, julkaisee jokaisen postauksen jonka aika on jo mennyt ja
joka on tilassa "odottaa", ja merkitsee sen julkaistuksi. Pyörii GitHub
Actionsissa cron-ajastimella (ks. .github/workflows/julkaise.yml).

Token + tili-ID luetaan ympäristömuuttujista (GitHub Secrets):
    IG_TOKEN   = pitkäkestoinen / system-user access token
    IG_ID      = @coaches.database Instagram Business Account ID
Paikallisessa ajossa fallback: ../Instagram API/.env (LONG_TOKEN + IG_COACHES_DB).

Kuvat haetaan julkisesta raw.githubusercontent.com-osoitteesta. Instagramin
palvelin hakee kuvan tästä URL:sta, joten repon on oltava julkinen.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "https://graph.facebook.com/v25.0"
HERE = os.path.dirname(os.path.abspath(__file__))
JONO_PATH = os.path.join(HERE, "jono.json")

# Uudelleenyritys saman ajon sisällä (Metan container-kilpajuoksu).
JULKAISU_YRITYKSET = 4
JULKAISU_ODOTUS = 15          # sekuntia yritysten välissä
# Montako cron-ajoa saa yrittää samaa postausta ennen kuin se jää virheeseen.
MAX_AJOYRITYKSET = 3


# --------------------------------------------------------------------------- #
# Konfiguraatio
# --------------------------------------------------------------------------- #
def load_config():
    """Token + IG-ID + kuvien raw-perusosoite. Env ensin, sitten paikallinen .env."""
    token = os.environ.get("IG_TOKEN")
    ig_id = os.environ.get("IG_ID")

    # Paikallinen fallback: keskitetty Instagram API -kansion .env
    if not token or not ig_id:
        env_path = os.path.join(HERE, "..", "..", "Instagram API", ".env")
        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip()
                    if k == "LONG_TOKEN" and not token:
                        token = v
                    elif k == "IG_COACHES_DB" and not ig_id:
                        ig_id = v

    # Kuvien julkinen perusosoite. Actionsissa rakennetaan automaattisesti.
    raw_base = os.environ.get("RAW_BASE")
    if not raw_base:
        repo = os.environ.get("GITHUB_REPOSITORY")     # "owner/repo"
        ref = os.environ.get("GITHUB_REF_NAME", "main")  # branch
        if repo:
            raw_base = f"https://raw.githubusercontent.com/{repo}/{ref}"

    if not token or not ig_id:
        sys.exit("✗ IG_TOKEN tai IG_ID puuttuu (env / .env).")
    return token, ig_id, raw_base


# --------------------------------------------------------------------------- #
# Graph API -apurit
# --------------------------------------------------------------------------- #
def api_post(path, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"{BASE}/{path}", data=data, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def api_get(path, params):
    q = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{BASE}/{path}?{q}") as r:
        return json.loads(r.read())


def on_ohimeneva(body):
    """Kannattaako sama julkaisuyritys toistaa hetken päästä?

    Metan container voi raportoida status_code=FINISHED hetkeä ennen kuin se on
    oikeasti julkaisukelpoinen; media_publish vastaa silloin 9007 / 2207027
    ("Media ID is not available"). Odottaminen korjaa sen. Todettu 2026-07-23,
    kun vt-11 kaatui juuri tähän.
    """
    try:
        virhe = json.loads(body).get("error", {})
    except ValueError:
        return False
    if virhe.get("is_transient"):
        return True
    return virhe.get("code") == 9007 or virhe.get("error_subcode") == 2207027


def jo_julkaistu(ig_id, token, caption):
    """Onko sama caption jo tilillä? Palauttaa media_id:n tai None.

    Ajetaan vain ennen UUSINTAyritystä: jos edellinen ajo ehti julkaista mutta
    kaatui ennen tilan tallennusta, uusinta tekisi tuplapostauksen. Jos kysely
    epäonnistuu, palautetaan None — tarkistuksen puute ei saa estää julkaisua.
    """
    try:
        res = api_get(f"{ig_id}/media", {
            "fields": "id,caption",
            "limit": "25",
            "access_token": token,
        })
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return None
    for media in res.get("data", []):
        if (media.get("caption") or "").strip() == caption.strip():
            return media.get("id")
    return None


def julkaise_kuva(ig_id, token, image_url, caption):
    """Kaksivaiheinen julkaisu: luo container → odota valmista → media_publish.
    Palauttaa julkaistun median ID:n."""
    # 1) Luo media-container
    res = api_post(f"{ig_id}/media", {
        "image_url": image_url,
        "caption": caption,
        "access_token": token,
    })
    creation_id = res["id"]

    # 2) Odota että container on valmis (kuva = yleensä heti, mutta varmistetaan)
    for _ in range(10):
        status = api_get(f"{creation_id}", {
            "fields": "status_code",
            "access_token": token,
        })
        code = status.get("status_code")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise RuntimeError(f"Container ERROR (creation_id={creation_id})")
        time.sleep(3)
    else:
        raise RuntimeError(f"Container ei valmistunut ajoissa (creation_id={creation_id})")

    # 3) Julkaise. Ohimenevä "ei vielä valmis" → odota ja yritä uudelleen.
    for yritys in range(1, JULKAISU_YRITYKSET + 1):
        try:
            pub = api_post(f"{ig_id}/media_publish", {
                "creation_id": creation_id,
                "access_token": token,
            })
            return pub["id"]
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if not on_ohimeneva(body) or yritys == JULKAISU_YRITYKSET:
                raise RuntimeError(body)
            print(f"  … ei vielä julkaisukelpoinen (yritys {yritys}/{JULKAISU_YRITYKSET}), odotetaan {JULKAISU_ODOTUS} s")
            time.sleep(JULKAISU_ODOTUS)


# --------------------------------------------------------------------------- #
# Päälogiikka
# --------------------------------------------------------------------------- #
def main():
    token, ig_id, raw_base = load_config()

    with open(JONO_PATH, encoding="utf-8") as f:
        jono = json.load(f)

    nyt = datetime.now(timezone.utc)
    julkaistu = 0
    virheita = 0

    for item in jono:
        tila = item.get("tila")
        uusinta = tila == "virhe" and item.get("ajoyrityksia", 1) < MAX_AJOYRITYKSET
        if tila != "odottaa" and not uusinta:
            continue
        aika_str = item.get("aika")
        if not aika_str:
            continue
        try:
            aika = datetime.fromisoformat(aika_str)
            if aika.tzinfo is None:
                aika = aika.replace(tzinfo=timezone.utc)
        except ValueError:
            print(f"  ⚠ {item.get('id')}: virheellinen aika '{aika_str}' — ohitetaan")
            continue
        if aika > nyt:
            continue  # ei vielä erääntynyt

        if not raw_base:
            sys.exit("✗ RAW_BASE / GITHUB_REPOSITORY puuttuu — kuvan URL:ä ei voi rakentaa.")
        image_url = f"{raw_base}/{urllib.parse.quote(item['kuva'])}"

        # Uusinnassa: meniköhän se sittenkin ulos? Tuplapostaus on pahempi
        # kuin julkaisematta jäänyt postaus.
        if uusinta:
            vanha = jo_julkaistu(ig_id, token, item["caption"])
            if vanha:
                print(f"→ {item['id']} oli jo tilillä (media_id={vanha}) — merkitään julkaistuksi, ei julkaista uudelleen.")
                item["tila"] = "julkaistu"
                item["media_id"] = vanha
                item["julkaistu_aika"] = nyt.isoformat()
                item.pop("virhe", None)
                item.pop("ajoyrityksia", None)
                continue
            print(f"→ {item['id']}: uusintayritys {item.get('ajoyrityksia', 1) + 1}/{MAX_AJOYRITYKSET}")

        print(f"→ Julkaistaan {item['id']} ({item['kuva']}) …")
        try:
            media_id = julkaise_kuva(ig_id, token, image_url, item["caption"])
            item["tila"] = "julkaistu"
            item["media_id"] = media_id
            item["julkaistu_aika"] = nyt.isoformat()
            item.pop("virhe", None)
            item.pop("ajoyrityksia", None)
            julkaistu += 1
            print(f"  ✓ julkaistu, media_id={media_id}")
        except (urllib.error.HTTPError, RuntimeError, KeyError) as e:
            msg = e.read().decode() if isinstance(e, urllib.error.HTTPError) else str(e)
            item["tila"] = "virhe"
            item["virhe"] = msg
            item["ajoyrityksia"] = item.get("ajoyrityksia", 0) + 1
            virheita += 1
            jaljella = MAX_AJOYRITYKSET - item["ajoyrityksia"]
            print(f"  ✗ VIRHE: {msg}")
            print(f"    ({'yritetään seuraavassa ajossa uudelleen, ' + str(jaljella) + ' yritystä jäljellä' if jaljella > 0 else 'yritykset käytetty — jää virheeseen, vaatii käsin korjauksen'})")

    # Tallenna jonon tila takaisin (workflow committaa tämän)
    with open(JONO_PATH, "w", encoding="utf-8") as f:
        json.dump(jono, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"\nValmis. Julkaistu: {julkaistu}, virheitä: {virheita}.")
    if virheita:
        sys.exit(1)  # → GitHub lähettää sähköpostin epäonnistuneesta ajosta


if __name__ == "__main__":
    main()
