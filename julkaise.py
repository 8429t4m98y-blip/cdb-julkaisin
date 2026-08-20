#!/usr/bin/env python3
"""
Julkaisin — DIY-ajastin Instagramiin. Monitili: kuvat ja reelit.

Lukee jono.json:n, julkaisee jokaisen postauksen jonka aika on jo mennyt ja
joka on tilassa "odottaa", ja merkitsee sen julkaistuksi. Pyörii GitHub
Actionsissa cron-ajastimella (ks. .github/workflows/julkaise.yml).

Jonorivi valitsee tilin kentällä "tili" (oletus "cdb") ja median joko
kentällä "kuva" (repon polku -> raw.githubusercontent) tai "video"
("<release-tagi>/<tiedosto.mp4>" -> Release-liite). Video menee ulos
reelinä: media_type=REELS + video_url.

Token luetaan ympäristömuuttujasta IG_TOKEN (GitHub Secret); paikallisessa
ajossa fallback ../../Instagram API/.env (LONG_TOKEN). Tili-ID:t ovat
allowlistissa alla — ne eivät ole salaisuuksia, vain token on.

Meta hakee median itse annetusta osoitteesta, joten repon on oltava julkinen
ja osoitteen toimittava ilman kirjautumista. Tämä on eri latauspolku kuin
Instagram API/ig_publish_reel.py:n rupload — ja se on syy tämän olemassaoloon:
rupload kaatuu yli ~60 s klipeillä, video_url ei [mitattu 2026-08-19].
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
# Yksittäisen HTTP-kutsun aikakatkaisu. Ilman tätä jumittunut yhteys roikkuu
# GitHubin ajorajaan asti (6 h) eikä jonon tila päädy koskaan levylle.
HTTP_TIMEOUT = 60

# Kontin valmistumisen pollaus: kuva on heti valmis, video transkoodataan.
POLLAUS = {"kuva": (10, 3), "video": (40, 15)}   # (kierrosta, sekuntia välissä)

# Tili-allowlist. IG Business Account -ID:t EIVÄT ole salaisuuksia (sama lista
# on Instagram API/ig_publish_reel.py:n turvaportissa) — vain token on. Lista
# on tässä siksi, ettei uusi tili vaadi käyntiä GitHubin secret-näkymässä.
# Ympäristömuuttuja IG_ID_<AVAIN> ohittaa rivin; vanha IG_ID = @coaches.database.
TILIT = {
    "cdb":        "17841437462011709",   # @coaches.database
    "monologi":   "17841435019135389",   # @monologi.podcast
    "miikameier": "17841400232383202",   # @miikameier
    "teamera":    "17841441289626947",   # @teamera.coaching
}
OLETUSTILI = "cdb"


# --------------------------------------------------------------------------- #
# Konfiguraatio
# --------------------------------------------------------------------------- #
def load_config():
    """Token + tili-ID:t + median julkiset perusosoitteet."""
    token = os.environ.get("IG_TOKEN")

    # Paikallinen fallback: keskitetty Instagram API -kansion .env
    if not token:
        env_path = os.path.join(HERE, "..", "..", "Instagram API", ".env")
        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("LONG_TOKEN="):
                        token = line.partition("=")[2].strip()
    if not token:
        sys.exit("✗ IG_TOKEN puuttuu (env / Instagram API/.env LONG_TOKEN).")

    # Tili-ID:t: allowlist + ympäristön ohitukset. IG_ID = vanha yhden tilin secret.
    tilit = dict(TILIT)
    if os.environ.get("IG_ID"):
        tilit[OLETUSTILI] = os.environ["IG_ID"]
    for avain in list(tilit):
        oma = os.environ.get(f"IG_ID_{avain.upper()}")
        if oma:
            tilit[avain] = oma

    # Median julkiset perusosoitteet. Actionsissa rakennetaan automaattisesti.
    repo = os.environ.get("GITHUB_REPOSITORY")       # "owner/repo"
    ref = os.environ.get("GITHUB_REF_NAME", "main")  # branch
    raw_base = os.environ.get("RAW_BASE")
    if not raw_base and repo:
        raw_base = f"https://raw.githubusercontent.com/{repo}/{ref}"
    release_base = os.environ.get("RELEASE_BASE")
    if not release_base and repo:
        release_base = f"https://github.com/{repo}/releases/download"

    return token, tilit, raw_base, release_base


def valitse_tili(item, tilit):
    """Jonorivin tili -> IG-ID. Tuntematon tili pysäyttää tämän rivin."""
    avain = (item.get("tili") or OLETUSTILI).strip().lower()
    if avain not in tilit:
        raise RuntimeError(
            f"tuntematon tili {avain!r} — sallitut: {', '.join(sorted(tilit))}"
        )
    return avain, tilit[avain]


def media_osoite(item, raw_base, release_base):
    """Jonorivi -> (laji, julkinen URL). laji on "kuva" tai "video"."""
    if item.get("video_url"):                       # valmis osoite sellaisenaan
        return "video", item["video_url"]
    if item.get("video"):                           # "<tagi>/<tiedosto.mp4>"
        if not release_base:
            raise RuntimeError("RELEASE_BASE / GITHUB_REPOSITORY puuttuu")
        tagi, _, nimi = item["video"].partition("/")
        if not nimi:
            raise RuntimeError(
                f"video-kentän muoto on '<release-tagi>/<tiedosto.mp4>', sai {item['video']!r}"
            )
        return "video", f"{release_base}/{urllib.parse.quote(tagi)}/{urllib.parse.quote(nimi)}"
    if item.get("kuva"):
        if not raw_base:
            raise RuntimeError("RAW_BASE / GITHUB_REPOSITORY puuttuu")
        return "kuva", f"{raw_base}/{urllib.parse.quote(item['kuva'])}"
    raise RuntimeError("rivillä ei ole kenttää kuva, video eikä video_url")


# --------------------------------------------------------------------------- #
# Graph API -apurit
# --------------------------------------------------------------------------- #
def tallenna(jono):
    """Kirjoita jonon tila levylle HETI, joka rivin muutoksen jälkeen.

    Ennen 2026-08-20 tila kirjoitettiin vasta koko silmukan jälkeen. Jos ajo
    kuoli kesken (GitHubin infra tappoi kolme ajoa 08-06), levyllä luki yhä
    "odottaa" rivistä joka oli jo Instagramissa → seuraava ajo julkaisi sen
    uudelleen, eikä jo_julkaistu-tuplasuoja lauennut (se ajettiin vain
    virhe-riveille). Videolla yksi rivi kestää jopa ~11 min, joten ikkuna oli
    aito, ei teoreettinen.
    """
    with open(JONO_PATH, "w", encoding="utf-8") as f:
        json.dump(jono, f, ensure_ascii=False, indent=2)
        f.write("\n")


def api_post(path, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"{BASE}/{path}", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        return json.loads(r.read())


def api_get(path, params):
    q = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{BASE}/{path}?{q}", timeout=HTTP_TIMEOUT) as r:
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


def luo_kontti(ig_id, token, laji, url, item):
    """Luo media-container. Video menee reelinä; Meta hakee tiedoston itse."""
    params = {"caption": item["caption"], "access_token": token}
    if laji == "video":
        params["media_type"] = "REELS"
        params["video_url"] = url
    else:
        params["image_url"] = url
    # Collab-kutsu, valinnainen: vastaanottaja hyväksyy tai hylkää IG:ssä.
    # ⚠️ EI MITATTU — Metan oma opas ei dokumentoi tätä parametria, kolmannen
    # osapuolen lähteet kyllä. Jos se ei kelpaa, virhe tulee TÄSSÄ konttia
    # luodessa eikä julkaisussa ⇒ mitään ei mene ulos vahingossa.
    if item.get("collab"):
        collab = item["collab"]
        params["collaborators"] = json.dumps(collab if isinstance(collab, list) else [collab])
    return api_post(f"{ig_id}/media", params)["id"]


def odota_valmista(creation_id, token, laji):
    """Odota että container on valmis. Kuva on käytännössä heti, video
    transkoodataan (mitattu 08-19: 73 s reel ~45 s).

    True  = valmis julkaistavaksi.
    False = kontti on kuollut (ERROR tai kadonnut, esim. Metan 24 h vanhenemisen
            jälkeen) → soittaja luo uuden. Aikakatkaisu sen sijaan nostaa
            poikkeuksen: kontti voi yhä valmistua, joten se pollataan uusinnassa
            loppuun eikä transkoodata alusta.
    """
    kierrokset, odotus = POLLAUS[laji]
    for _ in range(kierrokset):
        try:
            status = api_get(f"{creation_id}", {
                "fields": "status_code,status",
                "access_token": token,
            })
        except urllib.error.HTTPError:
            return False
        code = status.get("status_code")
        if code == "FINISHED":
            return True
        if code == "ERROR":
            print(f"  … kontti {creation_id} on ERROR: {status.get('status', '')}")
            return False
        time.sleep(odotus)
    raise RuntimeError(f"Container ei valmistunut ajoissa (creation_id={creation_id})")


def julkaise_media(ig_id, token, laji, url, item, merkitse):
    """Kaksivaiheinen julkaisu: luo container → odota valmista → media_publish.
    Palauttaa julkaistun median ID:n.

    `merkitse(creation_id)` tallentaa kontin riville levylle heti kun se on
    olemassa. Sen ansiosta kesken kuollut ajo tunnistetaan seuraavalla kerralla,
    ja uusinta jatkaa vanhaa konttia sen sijaan että transkoodaisi videon alusta.
    """
    creation_id = item.get("creation_id")
    if creation_id:
        print(f"  … jatketaan aiemmin luotua konttia {creation_id}")
        if not odota_valmista(creation_id, token, laji):
            print("  … vanha kontti ei kelpaa, luodaan uusi")
            creation_id = None
            merkitse(None)
    if not creation_id:
        creation_id = luo_kontti(ig_id, token, laji, url, item)
        merkitse(creation_id)
        if not odota_valmista(creation_id, token, laji):
            raise RuntimeError(f"Container ERROR (creation_id={creation_id})")

    # Julkaise. Ohimenevä "ei vielä valmis" → odota ja yritä uudelleen.
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
    token, tilit, raw_base, release_base = load_config()

    with open(JONO_PATH, encoding="utf-8") as f:
        jono = json.load(f)

    nyt = datetime.now(timezone.utc)
    julkaistu = 0
    virheita = 0

    for item in jono:
        tila = item.get("tila")
        # creation_id rivillä = edellinen ajo ehti luoda kontin muttei tallentaa
        # lopputulosta. Rivi voi siis olla jo Instagramissa.
        kesken = bool(item.get("creation_id"))
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

        # Tili, kuvateksti ja median osoite ratkaistaan ennen kuin mitään
        # lähetetään. Rikkinäinen rivi ei saa kaataa koko ajoa muiden alta —
        # ja kuvateksti tarkistetaan tässä, koska jo_julkaistu vertaa sitä.
        try:
            tili, ig_id = valitse_tili(item, tilit)
            laji, url = media_osoite(item, raw_base, release_base)
            if not (item.get("caption") or "").strip():
                raise RuntimeError("rivillä ei ole kuvatekstiä (caption)")
        except RuntimeError as e:
            item["tila"] = "virhe"
            item["virhe"] = str(e)
            item["ajoyrityksia"] = item.get("ajoyrityksia", 0) + 1
            virheita += 1
            tallenna(jono)
            print(f"  ✗ {item.get('id')}: {e}")
            continue

        # Meniköhän se sittenkin ulos? Tuplapostaus on pahempi kuin
        # julkaisematta jäänyt postaus. Tarkistetaan aina kun rivi on jo kerran
        # ollut käsittelyssä: uusinta (tila=virhe) TAI kesken jäänyt kontti
        # (edellinen ajo kuoli ennen kuin ehti tallentaa tilan).
        if uusinta or kesken:
            vanha = jo_julkaistu(ig_id, token, item["caption"])
            if vanha:
                print(f"→ {item['id']} oli jo tilillä (media_id={vanha}) — merkitään julkaistuksi, ei julkaista uudelleen.")
                item["tila"] = "julkaistu"
                item["media_id"] = vanha
                item["julkaistu_aika"] = nyt.isoformat()
                item.pop("virhe", None)
                item.pop("ajoyrityksia", None)
                item.pop("creation_id", None)
                tallenna(jono)
                continue
            print(f"→ {item['id']}: uusintayritys {item.get('ajoyrityksia', 1) + 1}/{MAX_AJOYRITYKSET}")

        def merkitse(cid, _item=item):
            """Kontti riville ja levylle heti — ks. tallenna()."""
            if cid:
                _item["creation_id"] = cid
            else:
                _item.pop("creation_id", None)
            tallenna(jono)

        print(f"→ Julkaistaan {item['id']} → @{tili} ({laji}) …")
        try:
            media_id = julkaise_media(ig_id, token, laji, url, item, merkitse)
            item["tila"] = "julkaistu"
            item["media_id"] = media_id
            item["julkaistu_aika"] = nyt.isoformat()
            item.pop("virhe", None)
            item.pop("ajoyrityksia", None)
            item.pop("creation_id", None)
            tallenna(jono)
            julkaistu += 1
            print(f"  ✓ julkaistu, media_id={media_id}")
        except (urllib.error.HTTPError, RuntimeError, KeyError) as e:
            msg = e.read().decode() if isinstance(e, urllib.error.HTTPError) else str(e)
            item["tila"] = "virhe"
            item["virhe"] = msg
            item["ajoyrityksia"] = item.get("ajoyrityksia", 0) + 1
            virheita += 1
            tallenna(jono)   # creation_id jää riville: uusinta jatkaa samaa konttia
            jaljella = MAX_AJOYRITYKSET - item["ajoyrityksia"]
            print(f"  ✗ VIRHE: {msg}")
            print(f"    ({'yritetään seuraavassa ajossa uudelleen, ' + str(jaljella) + ' yritystä jäljellä' if jaljella > 0 else 'yritykset käytetty — jää virheeseen, vaatii käsin korjauksen'})")

    tallenna(jono)   # varmistus; tila on kirjoitettu jo joka rivin jälkeen

    print(f"\nValmis. Julkaistu: {julkaistu}, virheitä: {virheita}.")
    if virheita:
        sys.exit(1)  # → GitHub lähettää sähköpostin epäonnistuneesta ajosta


if __name__ == "__main__":
    main()
