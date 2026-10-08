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

Kenttä "kuvat" (lista, 2–10 kohdetta) tekee karusellin: jokainen kohde on joko
kuva (repon polku) tai video (".mp4", muoto "<release-tagi>/<tiedosto.mp4>").
Kohteista luodaan lapsikontit, ja ne kootaan emokontiksi media_type=CAROUSEL.
Kenttä "kuvat" ei saa olla samalla rivillä kuin "kuva", "video" tai "video_url".

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

# Karusellin kohteiden määrä (Metan raja: 2–10).
KARUSELLI_MIN, KARUSELLI_MAX = 2, 10

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


def karuselli_kohteet(item, raw_base, release_base):
    """Rivin "kuvat"-lista -> [(laji, julkinen URL), ...]. Validoi ennen verkkoa.

    Kohde jonka pääte on .mp4 on video ("<tagi>/<tiedosto.mp4>", sama muoto ja
    sama Release-osoite kuin "video"-kentässä), kaikki muu on kuva (repon polku).
    """
    for kentta in ("kuva", "video", "video_url"):
        if item.get(kentta):
            raise RuntimeError(
                f"rivillä on sekä 'kuvat' että '{kentta}' — karuselli käyttää vain 'kuvat'-kenttää"
            )
    kuvat = item["kuvat"]
    if not isinstance(kuvat, list):
        raise RuntimeError("'kuvat' on oltava lista repopolkuja")
    if not KARUSELLI_MIN <= len(kuvat) <= KARUSELLI_MAX:
        raise RuntimeError(
            f"karusellissa on oltava {KARUSELLI_MIN}–{KARUSELLI_MAX} kohdetta, rivillä on {len(kuvat)}"
        )
    kohteet = []
    for nro, polku in enumerate(kuvat, start=1):
        if not isinstance(polku, str) or not polku.strip():
            raise RuntimeError(f"'kuvat'-kohde {nro} ei ole polku (tyhjä tai ei merkkijono)")
        polku = polku.strip()
        try:
            if polku.lower().endswith(".mp4"):
                kohteet.append(media_osoite({"video": polku}, raw_base, release_base))
            else:
                kohteet.append(media_osoite({"kuva": polku}, raw_base, release_base))
        except RuntimeError as e:
            raise RuntimeError(f"'kuvat'-kohde {nro} ({polku}): {e}")
    return kohteet


def media_osoite(item, raw_base, release_base):
    """Jonorivi -> (laji, julkinen URL). laji on "kuva" tai "video".

    Karusellirivillä ("kuvat") palautuu ("karuselli", [(laji, URL), ...]).
    """
    if item.get("kuvat") is not None:
        return "karuselli", karuselli_kohteet(item, raw_base, release_base)
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

    Ajetaan JOKAISELLE erääntyneelle riville ennen julkaisua. Syy: rivin tila voi
    hävitä ilman että riville jää jälkeä siitä (ks. main). Kustannus on yksi GET
    per erääntynyt rivi. Jos kysely epäonnistuu, palautetaan None — tarkistuksen
    puute ei saa estää julkaisua, koska julkaisematta jäänyt postaus on tässä
    suunnassa halvempi virhe kuin julkaisun estäminen.
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


def collab_param(item):
    """Valinnainen collab-kutsu parametreiksi. ⚠️ EI MITATTU — ks. luo_kontti."""
    if not item.get("collab"):
        return {}
    collab = item["collab"]
    return {"collaborators": json.dumps(collab if isinstance(collab, list) else [collab])}


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
    params.update(collab_param(item))
    # Reelin kansikuva, valinnainen: täysi URL kenttään "kansi_url".
    # Jos Meta hylkää kannen, kontti luodaan uudelleen ilman sitä ⇒ reel lähtee
    # silti ajallaan, kansi on silloin Metan oletusruutu.
    if laji == "video" and item.get("kansi_url"):
        try:
            return api_post(f"{ig_id}/media", {**params, "cover_url": item["kansi_url"]})["id"]
        except urllib.error.HTTPError as e:
            print(f"  … kansikuva hylättiin ({e.code}), luodaan kontti ilman kantta")
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

    return julkaise_kontti(ig_id, token, creation_id)


def julkaise_kontti(ig_id, token, creation_id):
    """media_publish valmiille kontille. Ohimenevä "ei vielä valmis" → odota ja
    yritä uudelleen. Palauttaa julkaistun median ID:n."""
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


def luo_lapsi(ig_id, token, laji, url):
    """Karusellin lapsikontti: ei omaa kuvatekstiä, vain is_carousel_item."""
    params = {"is_carousel_item": "true", "access_token": token}
    if laji == "video":
        params["media_type"] = "VIDEO"
        params["video_url"] = url
    else:
        params["image_url"] = url
    return api_post(f"{ig_id}/media", params)["id"]


def julkaise_karuselli(ig_id, token, kohteet, item, merkitse, merkitse_lapset):
    """Karuselli: lapsikontit → odota FINISHED → emokontti CAROUSEL → odota →
    media_publish. Palauttaa julkaistun median ID:n.

    `merkitse(creation_id)` tallentaa emokontin ja `merkitse_lapset(idt)`
    lapsikontit riville heti kun ne ovat olemassa (ks. tallenna()). Uusinta
    jatkaa niistä: valmiita lapsia ei luoda uudestaan, ja videolapset
    transkoodataan vain kerran. Vain kuollut (ERROR / kadonnut) lapsi luodaan
    uudelleen. Emokontin ERROR hylkää myös lapset.
    """
    # Karusellin odotus mitoitetaan hitaimman kohteen mukaan.
    emon_laji = "video" if any(laji == "video" for laji, _ in kohteet) else "kuva"

    creation_id = item.get("creation_id")
    lapset = [c for c in (item.get("lapsi_idt") or []) if c][:len(kohteet)]
    if creation_id:
        print(f"  … jatketaan aiemmin luotua karusellikonttia {creation_id}")
        if not odota_valmista(creation_id, token, emon_laji):
            print("  … vanha karusellikontti ei kelpaa, luodaan uusi")
            creation_id = None
            lapset = []
            merkitse(None)
            merkitse_lapset(lapset)

    if not creation_id:
        # Lapsikontit: luo puuttuvat, tarkista olemassa olevat.
        for nro, (laji, url) in enumerate(kohteet):
            if nro < len(lapset) and odota_valmista(lapset[nro], token, laji):
                continue
            if nro < len(lapset):
                print(f"  … lapsikontti {nro + 1}/{len(kohteet)} ei kelpaa, luodaan uusi")
                lapset[nro] = luo_lapsi(ig_id, token, laji, url)
            else:
                lapset.append(luo_lapsi(ig_id, token, laji, url))
            merkitse_lapset(lapset)
            if not odota_valmista(lapset[nro], token, laji):
                raise RuntimeError(f"Lapsikontti {nro + 1} ERROR (creation_id={lapset[nro]})")

        params = {
            "media_type": "CAROUSEL",
            "children": ",".join(lapset),
            "caption": item["caption"],
            "access_token": token,
        }
        params.update(collab_param(item))
        creation_id = api_post(f"{ig_id}/media", params)["id"]
        merkitse(creation_id)
        if not odota_valmista(creation_id, token, emon_laji):
            raise RuntimeError(f"Karusellikontti ERROR (creation_id={creation_id})")

    return julkaise_kontti(ig_id, token, creation_id)


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

        # Meniköhän se sittenkin ulos? Tuplapostaus on pahempi kuin julkaisematta
        # jäänyt postaus, ja rivin tila voi hävitä ilman että riville jää siitä
        # mitään jälkeä: Actionsissa levy on väliaikainen, ja ainoa pysyvä
        # kirjoitus on ajon lopun commit. Jos runner kuolee kesken (3/500 ajoa,
        # kaikki 08-06) tai commitin push hylätään (main liikkui ajon aikana),
        # levylle kirjoitettu "julkaistu" ei päädy mihinkään ja rivi palaa
        # seuraavaan ajoon tilassa "odottaa" ILMAN creation_id:tä — eli ilman
        # yhtäkään merkkiä siitä että se on jo Instagramissa.
        # ⇒ Tarkistus ajetaan JOKAISELLE erääntyneelle riville, ei vain
        # uusinnoille ja kesken jääneille. Hinta: yksi GET per erääntynyt rivi.
        vanha = jo_julkaistu(ig_id, token, item["caption"])
        if vanha:
            print(f"→ {item['id']} oli jo tilillä (media_id={vanha}) — merkitään julkaistuksi, ei julkaista uudelleen.")
            item["tila"] = "julkaistu"
            item["media_id"] = vanha
            item["julkaistu_aika"] = nyt.isoformat()
            item.pop("virhe", None)
            item.pop("ajoyrityksia", None)
            item.pop("creation_id", None)
            item.pop("lapsi_idt", None)
            tallenna(jono)
            continue
        if uusinta:
            print(f"→ {item['id']}: uusintayritys {item.get('ajoyrityksia', 1) + 1}/{MAX_AJOYRITYKSET}")

        def merkitse(cid, _item=item):
            """Kontti riville ja levylle heti — ks. tallenna()."""
            if cid:
                _item["creation_id"] = cid
            else:
                _item.pop("creation_id", None)
            tallenna(jono)

        def merkitse_lapset(idt, _item=item):
            """Karusellin lapsikontit riville ja levylle heti."""
            if idt:
                _item["lapsi_idt"] = list(idt)
            else:
                _item.pop("lapsi_idt", None)
            tallenna(jono)

        print(f"→ Julkaistaan {item['id']} → @{tili} ({laji}) …")
        try:
            if laji == "karuselli":
                media_id = julkaise_karuselli(ig_id, token, url, item, merkitse, merkitse_lapset)
            else:
                media_id = julkaise_media(ig_id, token, laji, url, item, merkitse)
            item["tila"] = "julkaistu"
            item["media_id"] = media_id
            item["julkaistu_aika"] = nyt.isoformat()
            item.pop("virhe", None)
            item.pop("ajoyrityksia", None)
            item.pop("creation_id", None)
            item.pop("lapsi_idt", None)
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
