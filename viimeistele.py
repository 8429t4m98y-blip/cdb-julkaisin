#!/usr/bin/env python3
"""
Vaihe 5 yhtenä komentona: odota että jonorivi on julkaistu → tarkista ääni →
poista Release-liite ja jonorivi → todenna siivous elävistä lähteistä → kirjaa
tulos raporttitiedostoon.

    python3 viimeistele.py --id j20-k4 --id j20-k5 --id j20-k6

`--id` voi antaa monta kertaa; id:t käsitellään järjestyksessä, kukin omana
kokonaisuutenaan (oma tarkistus, oma commit, oma push).

`--alkuperainen` JOHDETAAN jonorivin `video`-kentästä: tiedostonimi haetaan
HAKUJUURET-kansioista. ⛔ Jos sitä ei löydy — tai sama nimi löytyy kahdesta
paikasta — se id PYSÄYTETÄÄN eikä mitään poisteta. Lähde ratkaisee äänituomion,
ja väärä tiedosto läpäisee tarkistuksen hiljaa [mitattu 08-27]. Käsin annettuna
polku käy vain yhdelle id:lle kerrallaan:

    python3 viimeistele.py --id j20-k4 --alkuperainen "/…/jakso20_klippi4_TO.mp4"

Miksi tämä on skripti eikä ajastettu Claude-prompti, joka tekisi samat viisi
askelta käsin: ajastettu tehtävä pysähtyy ensimmäiseen kirjoittavaan komentoon
ja jää odottamaan hyväksyntää jota kukaan ei ole antamassa [mitattu 08-18 ja
08-19, kaksi ajoa, molemmat tuloksetta — `automaatiot.md`]. Yksi komento =
yksi hyväksyntä, joka voidaan antaa etukäteen.

⛔ EI POISTA MITÄÄN JOS ÄÄNI ON RIKKI TAI JOS SITÄ EI VOITU MITATA. Silloin liite
   ja rivi jäävät paikalleen, koska uusinta tarvitsee molemmat.

⛔ EI POISTA JONORIVIÄ JOS LIITE EI POISTUNUT. Molemmat jäävät paikalleen ja sama
   komento voidaan ajaa uudestaan; rivin poisto yksin tekisi tilasta
   peruuttamattoman, koska uusinta ei enää löytäisi riviä eikä siis liitettä.

Poistumiskoodit: 0 = valmis JA todennettu · 2 = ei edennyt (ei julkaistu
määräajassa, ei `media_id`:tä, lähdetiedostoa ei voitu johtaa, tai verkko ei
vastannut `FETCH_YRITYKSET` kertaa peräkkäin) · 3 = ääni
rikki TAI ei tarkistettavissa · 4 = ääni puhdas mutta siivous jäi kesken (pull,
liite tai push epäonnistui) — **koodi 4 on aina korjattavissa samalla
komennolla** · 5 = siivous raportoitiin tehdyksi mutta `todenna_siivous.py` ei
vahvistanut sitä. ⛔ **Koodi 5 EI lupaa korjattavuutta samalla komennolla:** jos
jonorivi on jo poissa, uusinta osuu `etarivi() → None` -haaraan eikä koske
liitteeseen enää. Lue todennuksen tuloste ja korjaa se pää joka jäi.
**Monella id:llä palautetaan suurin yksittäinen koodi**, ja ajon lopussa
tulostetaan yhteenveto id kerrallaan.

⛔ RAPORTTI VIEDÄÄN REMOTEEN OMANA COMMITTINAAN jokaisen id:n jälkeen
   (`viimeistely-loki.md`). Se EI muuta poistumiskoodia: koodi 4 lupaa
   *"korjattavissa samalla komennolla"*, eikä se päde raporttiin, koska
   jonorivi on siinä vaiheessa jo poissa. Epäonnistuminen tulostuu punaisena
   ja antaa tarkan korjauskomennon. [08-31: ennen tätä ajon ainoa todiste jäi
   pelkästään levylle — `j20-k7`:n rivi löytyi commitoimattomana ajon jälkeen.]

⛔ EI KIRJAA ONNISTUMISTA JOTA EI TAPAHTUNUT. Jokaisen alikomennon paluuarvo
   tarkistetaan; 08-23 j19-k7:n liitteen poisto epäonnistui ja loki sanoi silti
   ✅ PUHDAS · liite poistettu. Liite löytyi Releasesta 4 vrk myöhemmin.

⛔ SIIVOUS TODENNETAAN ELÄVISTÄ LÄHTEISTÄ ENNEN KUIN AJO SANOO 0. Puhtaan
   tuomion jälkeen ajetaan `todenna_siivous.py --id <id>` automaattisesti: se
   lukee jonorivin `origin/main`:sta ja liitteen GitHubin assets-listasta, ei
   tämän skriptin omasta tulosteesta. Jos se ei vahvista MOLEMPIA päitä, koodi
   on **5**, ei 0. [Yhdistetty 09-13. Siihen asti todennus oli erillinen
   komento, jonka sai unohtaa juuri silloin kun tämä skripti valehteli — eli
   täsmälleen siinä tapauksessa jota varten se rakennettiin.]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PROJEKTIT = os.path.abspath(os.path.join(HERE, "..", ".."))
TARKISTA = os.path.join(PROJEKTIT, "Instagram API", "tarkista_julkaisu.py")
# Tilit joilla `tarkista_julkaisu.py` ajetaan `--vain-todiste`-tilassa: se
# tarkistaa että julkaisu on olemassa mutta EI mittaa ääntä.
# 📏 Miikan päätös 2026-09-16: Monologin klipeistä 0/17 tuomittiin RIKKI
# (`viimeistely-loki.md` 23.8.–16.9.). Ne neljä aitoa äänivikaa ovat ERA:n
# vieraista mastereista ja ne korjattiin lähteessä (08-14), joten vertailu jää
# niille riveille joissa vika on joskus ollut.
# 🔓 Purkuehto: yksikin RIKKI-tuomio Monologin klipistä ⇒ poista tili tästä.
VAIN_TODISTE_TILIT = {"monologi"}
# ERA:n julkaistut reelit vs. `viimeistely-loki.md` — ks. era_ilman_tuomiota().
ERA_TILI = "teamera.coaching"
ERA_REELEJA = 10              # montako uusinta reeliä katsotaan (--reeleja yliajaa)
# ⛔ Tätä vanhempia ei lippuiteta: `viimeistely-loki.md` alkaa 23.8. ja sen
# ensimmäinen ERA-tuomio on 27.8. (`era-k7`), joten vanhemmat julkaisut
# puuttuisivat lokista ikuisesti [mitattu 16.9.: 12 uusimmasta reelistä 6].
ERA_ALKAA = "2026-08-27"
TODENNA = os.path.join(HERE, "todenna_siivous.py")
RAPORTTI = os.path.join(HERE, "viimeistely-loki.md")

# Mistä lähdetiedosto etsitään jonorivin `video`-kentän tiedostonimellä.
HAKUJUURET = [
    os.path.join(PROJEKTIT, "Henkilöbrändi", "Monologi", "Jaksot"),
    os.path.join(PROJEKTIT, "ERA", "klipit"),
]

SELITE = {
    0: "valmis ja todennettu",
    2: "ei edennyt — mitään ei poistettu",
    3: "ääni rikki tai ei tarkistettavissa — mitään ei poistettu",
    4: "ääni puhdas, siivous jäi kesken",
    5: "siivous tehty mutta todennus ei vahvistanut sitä",
}

# Uudelleenyritys verkkokutsulle saman ajon sisällä. Sama muoto kuin
# `julkaise.py`:n JULKAISU_YRITYKSET/JULKAISU_ODOTUS — kaksi eri
# takaisinvetokäyrää samassa putkessa pakottaisi lukemaan molemmat.
FETCH_YRITYKSET = 4
FETCH_ODOTUS = 15             # sekuntia yritysten välissä


class VerkkoVirhe(Exception):
    """Jonoriviä ei saatu luettua originista. ⛔ Ei koskaan poiston jälkeen:
    `etarivi()` kutsutaan vain ennen siivousta, joten tämä pysäyttää id:n
    tilaan jossa liite ja rivi ovat molemmat tallessa."""


def aja(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def viimeinen_rivi(r):
    rivit = (r.stdout + r.stderr).strip().splitlines()
    return rivit[-1] if rivit else "—"


def etarivi(rivi_id):
    """Lue jonorivi GitHubin mainista — paikallinen kopio on aina jäljessä.

    ⛔ Verkkovirhe ei enää tapa ajoa hiljaa. Ennen 13.9. fetchin kaatuminen
    kutsui `sys.exit()`: poistumiskoodiksi tuli dokumentoimaton 1 eikä
    `viimeistely-loki.md`:hen jäänyt riviä. 13.9. klo 08:41 j22-k7:n ajo kuoli
    virheeseen "Could not resolve host: github.com" ja loki hyppäsi
    `07:37 · j22-k5` → `10:30 · j22-k6` ilman jälkeä koko ajosta.
    Altistus ei ole yksi kutsu vaan ~80: odotussilmukka hakee 180 s välein,
    joten `--odota 240` fetchaa nelisenkymmentä kertaa tunnissa.
    """
    viimeisin = "—"
    for yritys in range(1, FETCH_YRITYKSET + 1):
        f = aja(["git", "-C", HERE, "fetch", "origin", "--quiet"])
        if f.returncode == 0:
            break
        viimeisin = f.stderr.strip()[:200] or "(ei virheilmoitusta)"
        if yritys < FETCH_YRITYKSET:
            print(f"  … git fetch ei onnistunut (yritys {yritys}/{FETCH_YRITYKSET}), "
                  f"odotetaan {FETCH_ODOTUS} s: {viimeisin}")
            time.sleep(FETCH_ODOTUS)
    else:
        raise VerkkoVirhe(f"`git fetch` epäonnistui {FETCH_YRITYKSET} kertaa peräkkäin "
                          f"({FETCH_ODOTUS} s välein): {viimeisin}")
    r = aja(["git", "-C", HERE, "show", "origin/main:jono.json"])
    if r.returncode != 0:
        raise VerkkoVirhe(f"`jono.json` ei luettavissa originista: "
                          f"{r.stderr.strip()[:200]}")
    for item in json.loads(r.stdout):
        if item.get("id") == rivi_id:
            return item
    return None


def johda_alkuperainen(video_kentta):
    """`video` = '<release-tagi>/<tiedosto.mp4>' → sama tiedostonimi levyltä.

    Palauttaa (polku, None) tai (None, syy). ⛔ Ei arvaa: 0 osumaa tai useampi
    kuin 1 pysäyttää id:n. Lähde ratkaisee äänituomion, joten väärä tiedosto ei
    saa mennä läpi hiljaa.
    """
    nimi = os.path.basename((video_kentta or "").strip())
    if not nimi.lower().endswith(".mp4"):
        return None, f"jonorivin `video`-kenttä ei ole mp4-tiedosto: {video_kentta!r}"
    osumat = []
    for juuri in HAKUJUURET:
        for polku, _, tiedostot in os.walk(juuri):
            if nimi in tiedostot:
                osumat.append(os.path.join(polku, nimi))
    if not osumat:
        return None, (f"tiedostoa `{nimi}` ei löytynyt hakujuurista — anna polku käsin: "
                      f"--id <id> --alkuperainen <mp4>")
    if len(osumat) > 1:
        return None, ("sama tiedostonimi `%s` löytyi %d paikasta, en arvaa:\n  %s"
                      % (nimi, len(osumat), "\n  ".join(osumat)))
    return osumat[0], None


def kirjaa(teksti):
    with open(RAPORTTI, "a", encoding="utf-8") as f:
        f.write(teksti + "\n")
    print(teksti)


def pusha_raportti(rivi_id):
    """Vie `viimeistely-loki.md` remoteen omana committinaan.

    ⛔ EI muuta poistumiskoodia. Koodi 4 lupaa *"korjattavissa samalla
    komennolla"*, eikä se pidä paikkaansa raportista: kun jonorivi on jo
    poistettu, uusinta osuu `etarivi() → None` -haaraan eikä kirjoita
    raporttiin mitään. Epäonnistuminen huudetaan siis näkyviin ja annetaan
    tarkka korjauskomento — sitä ei piiloteta koodiin jota ei voi korjata.

    Miksi oma commit eikä sama kuin `jono.json`:n: raportti kirjoitetaan
    vasta kun tuomio on tiedossa, eli `kirjaa()` ajaa jonorivin poiston
    JÄLKEEN. Yhteinen commit vaatisi tuomion siirtämistä ennen siivousta,
    ja siivouksen järjestys on osa sääntöä (ks. kohta 3).

    [rakennettu 08-31: ajon ainoa todiste jäi tähän asti vain levylle —
    `j20-k7`:n rivi löytyi commitoimattomana ajon jälkeen.]
    """
    tila = aja(["git", "-C", HERE, "status", "--porcelain", "--", RAPORTTI])
    if tila.returncode != 0 or not tila.stdout.strip():
        return  # ei muutosta vietäväksi — tai git ei vastaa, ja se näkyy jo muualla
    aja(["git", "-C", HERE, "add", "--", RAPORTTI])
    c = aja(["git", "-C", HERE, "commit", "-q", "-m",
             f"viimeistely-loki: {rivi_id} vaihe 5 ajettu"])
    pu = aja(["sh", os.path.join(HERE, "push.sh")]) if c.returncode == 0 else c
    if c.returncode == 0 and pu.returncode == 0:
        print(f"- ✓ raportti: `viimeistely-loki.md` commitoitu ja työnnetty")
        return
    # Korjauskomento riippuu siitä KUMPI kaatui: jo commitoitua ei voi commitoida
    # uudelleen, ja `&&`-ketju pysähtyisi siihen ("nothing to commit").
    if c.returncode == 0:
        korjaus = f'sh "{os.path.join(HERE, "push.sh")}"'
    else:
        korjaus = (f'git -C "{HERE}" add -- viimeistely-loki.md && '
                   f'git -C "{HERE}" commit -m "viimeistely-loki: {rivi_id}" && '
                   f'sh "{os.path.join(HERE, "push.sh")}"')
    print(f"- 🔴 RAPORTTI JÄI PAIKALLISEKSI ({viimeinen_rivi(pu)}) — siivous on tehty, "
          f"mutta ajon todiste ei ole remotessa. ⛔ Sama komento EI korjaa tätä "
          f"(jonorivi on jo poissa). Korjaa käsin:\n  {korjaus}")


def todenna(rivi_id):
    """Aja `todenna_siivous.py` ja palauta (koodi, tuloste).

    ⛔ Tämän skriptin oma tuloste ei kelpaa todisteeksi: 08-23 j19-k7 raportoi
    "✅ liite poistettu" liitteelle joka löytyi Releasesta 4 vrk myöhemmin.
    Todennus lukee molemmat päät elävistä lähteistä (`origin/main:jono.json` +
    GitHubin assets-lista), joten se on ajon ainoa puhdas tuomio.
    """
    if not os.path.isfile(TODENNA):
        return 1, f"todenna_siivous.py puuttuu: {TODENNA}"
    r = aja([sys.executable, TODENNA, "--id", rivi_id])
    return r.returncode, (r.stdout + r.stderr).strip()


def kasittele(rivi_id, alkuperainen_kasin, odota):
    def otsikko():
        return f"\n## {datetime.now():%Y-%m-%d %H:%M} · {rivi_id}\n"

    def hae_rivi(vaihe):
        """(rivi, koodi) — verkkovirhe kirjataan lokiin ja pysäyttää id:n koodiin 2."""
        try:
            return etarivi(rivi_id), None
        except VerkkoVirhe as e:
            kirjaa(otsikko() + f"🌐 **VERKKO EI VASTANNUT {vaihe}** — {e}\n"
                               f"Jonoriviä ei voitu lukea, joten mitään ei tarkistettu "
                               f"eikä poistettu: liite ja rivi ovat molemmat tallessa. "
                               f"Aja sama komento uudestaan:\n"
                               f"  `python3 viimeistele.py --id {rivi_id}`")
            return None, 2

    rivi, verkkokoodi = hae_rivi("heti alussa")
    if verkkokoodi:
        return verkkokoodi
    if rivi is None:
        kirjaa(otsikko() + "⚠️ Riviä ei ole jonossa. Joku on jo ajanut vaihe 5:n, "
                           "tai id on väärä. Ei tehty mitään.")
        return 0

    # 0) lähdetiedosto ensin — ilman sitä ei kannata odottaa tuntia.
    #    ⛔ VAIN_TODISTE-riveillä sitä ei haeta lainkaan: lähdettä tarvitaan
    #    pelkkään spektrivertailuun, eikä sitä enää tehdä näille tileille
    #    (ks. VAIN_TODISTE_TILIT). Turha haku pysäyttäisi id:n syystä jolla ei
    #    ole tekemistä julkaisun kanssa — juuri niin kävi or-07:lle 15.9.
    vain_todiste = (rivi.get("tili") or "cdb").strip().lower() in VAIN_TODISTE_TILIT
    alkuperainen = alkuperainen_kasin
    if not alkuperainen and not vain_todiste:
        alkuperainen, syy = johda_alkuperainen(rivi.get("video", ""))
        if not alkuperainen:
            kirjaa(otsikko() + f"🛑 Lähdetiedostoa ei voitu johtaa: {syy}\n"
                               f"Mitään ei tarkistettu eikä poistettu.")
            return 2
    if alkuperainen and not os.path.isfile(alkuperainen):
        kirjaa(otsikko() + f"🛑 Alkuperäistä ei ole: {alkuperainen}\n"
                           f"Mitään ei tarkistettu eikä poistettu.")
        return 2
    print(f"\n▶ {rivi_id} — lähde: {alkuperainen or 'ei tarvita (vain julkaisutodiste)'}")

    # 1) odota että cron on julkaissut
    loppu = time.time() + odota * 60
    while True:
        if rivi is None:
            kirjaa(otsikko() + "⚠️ Rivi katosi jonosta kesken odotuksen. Ei tehty mitään.")
            return 0
        if rivi.get("tila") == "julkaistu":
            break
        if rivi.get("tila") == "virhe":
            kirjaa(otsikko() + f"🔴 Rivi on tilassa `virhe`: {str(rivi.get('virhe'))[:300]}\n"
                               f"Liite ja rivi jätettiin paikalleen — `julkaise.py` uusii "
                               f"seuraavalla ajolla.")
            return 2
        if time.time() > loppu:
            kirjaa(otsikko() + f"⏳ Ei julkaistu {odota} minuutissa "
                               f"(tila `{rivi.get('tila')}`). Mitään ei poistettu. "
                               f"Aja tämä uudestaan myöhemmin.")
            return 2
        time.sleep(180)
        rivi, verkkokoodi = hae_rivi("kesken odotuksen")
        if verkkokoodi:
            return verkkokoodi

    media_id = str(rivi.get("media_id") or "").strip()
    liite = rivi.get("video", "")
    if not media_id:
        kirjaa(otsikko() + "⚠️ Rivi on `julkaistu` mutta ilman `media_id`:tä — "
                           "en tarkista enkä poista sokkona.")
        return 2

    # 2) tarkista julkaisu Metan omasta transkoodauksesta.
    #    Kaksi tilaa, ja ero on tilikohtainen (ks. VAIN_TODISTE_TILIT):
    #      täysi        = lataa julkaisun ja mittaa ääniraidan lähdettä vasten
    #      vain todiste = tarkistaa että `media_url` vastaa (julkaisu on olemassa)
    #    ⚠️ MOLEMMISSA koodi != 0 tarkoittaa ettei mitään poisteta.
    cmd = [sys.executable, TARKISTA, "--media-id", media_id]
    cmd += ["--vain-todiste"] if vain_todiste else ["--alkuperainen", alkuperainen]
    t = aja(cmd)
    tuloste = (t.stdout + t.stderr).strip()
    if t.returncode == 2:
        kirjaa(otsikko() + f"🛑 **EI TARKISTETTAVISSA** (`media_id {media_id}`) — Meta ei "
               f"palauttanut `media_url`ia, joten "
               + ("julkaisua ei todennettu kertaakaan" if vain_todiste
                  else "ääntä ei mitattu kertaakaan") +
               f". Tätä kohdellaan kuin RIKKI: liite ja rivi JÄTETTIIN paikalleen.\n"
               f"```\n{tuloste[-1200:]}\n```")
        return 3
    if t.returncode != 0:
        kirjaa(otsikko() + ("🔴 **JULKAISUA EI TODENNETTU tai tarkistus kaatui**"
                            if vain_todiste else
                            "🔴 **ÄÄNI RIKKI tai tarkistus kaatui**")
               + f" (`media_id {media_id}`) — "
               f"liite ja rivi JÄTETTIIN paikalleen.\n```\n{tuloste[-1200:]}\n```")
        return 3

    # 3) siivous — vasta kun tuomio on puhdas. JÄRJESTYS ON OSA SÄÄNTÖÄ:
    #    ① pull ensin, jotta jonorivi poistetaan tuoreesta kopiosta eikä stale
    #    lokaali pushaudu originin päälle · ② liite sitten · ③ jonoriviin
    #    kosketaan VASTA kun liite on poissa.
    #    ⛔ Jos ① tai ② epäonnistuu, kumpaakaan ei viedä eteenpäin: rivin poisto
    #    tekisi tilasta peruuttamattoman (rivi poissa ⇒ uusinta osuu
    #    `etarivi() → None` -haaraan eikä koske liitteeseen enää koskaan) ja
    #    liite jäisi orvoksi. [mitattu 08-30: vahti esti poiston 2 kertaa 10
    #    ajossa ja MOLEMMILLA kerroilla syntyi orpo liite.]
    poistot, epaonnistui = [], []

    pull = aja(["git", "-C", HERE, "pull", "--ff-only", "origin", "main"])
    if pull.returncode != 0:
        kirjaa(otsikko() + f"⚠️ **ÄÄNI PUHDAS, MUTTA SIIVOUS EI ALKANUT** · "
               f"`media_id` **{media_id}**\n"
               f"- 🔴 `git pull --ff-only` epäonnistui: {viimeinen_rivi(pull)}\n"
               f"- Liite `{liite}` ja jonorivi JÄTETTIIN paikalleen. Korjaa klooni ja "
               f"aja sama komento uudestaan:\n"
               f"  `python3 viimeistele.py --id {rivi_id}`")
        return 4

    if liite:
        p = aja([sys.executable, os.path.join(HERE, "laheta_video.py"), "--poista", liite])
        poistot.append(f"{'✓' if p.returncode == 0 else '✗'} liite: {viimeinen_rivi(p)}")
        if p.returncode != 0:
            kirjaa(otsikko() + f"⚠️ **ÄÄNI PUHDAS, MUTTA LIITE EI POISTUNUT** · "
                   f"`media_id` **{media_id}**\n"
                   f"- 🔴 Release-liite `{liite}` EI poistunut — **jonoriviin ei koskettu**, "
                   f"joten sama komento ajaa siivouksen loppuun:\n"
                   f"  `python3 viimeistele.py --id {rivi_id}`\n"
                   + "\n".join(f"- {x}" for x in poistot))
            return 4

    jono_path = os.path.join(HERE, "jono.json")
    jono = json.load(open(jono_path, encoding="utf-8"))
    jaljelle = [r for r in jono if r.get("id") != rivi_id]
    if len(jaljelle) != len(jono):
        json.dump(jaljelle, open(jono_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        open(jono_path, "a", encoding="utf-8").write("\n")
        aja(["git", "-C", HERE, "add", "jono.json"])
        aja(["git", "-C", HERE, "commit", "-q", "-m",
             f"jono: {rivi_id} julkaistu (media_id {media_id}), rivi pois vaihe 5:n mukaan"])
        pu = aja(["sh", os.path.join(HERE, "push.sh")])
        poistot.append(f"{'✓' if pu.returncode == 0 else '✗'} push: {viimeinen_rivi(pu)}")
        if pu.returncode != 0:
            epaonnistui.append("jonorivin poisto jäi PAIKALLISEKSI — remotessa rivi on yhä")

    if epaonnistui:
        kirjaa(otsikko() + f"⚠️ **ÄÄNI PUHDAS, MUTTA SIIVOUS JÄI KESKEN** · "
               f"`media_id` **{media_id}**\n"
               + "\n".join(f"- 🔴 {x}" for x in epaonnistui) + "\n"
               + "\n".join(f"- {x}" for x in poistot))
        return 4

    kirjaa(otsikko() +
           f"✅ **PUHDAS** · `media_id` **{media_id}** · liite `{liite}` poistettu · "
           f"jonorivi poistettu\n"
           f"```\n{tuloste[-700:]}\n```\n"
           f"➡️ Jäljellä: kirjaa `media_id` jakson `…_julkaisumateriaalit.md`:hen.\n"
           + "\n".join(f"- {x}" for x in poistot))
    return 0


def era_ilman_tuomiota(jono_media_idt, reeleja):
    """Listaa @teamera.coachingin julkaistut reelit joilta puuttuu äänituomio.

    📏 **Miksi (Miikan päätös 2026-09-16):** `--tila`:n muut osiot lukevat jonoa,
    ja jonorivi voi kadota ilman että vaihe 5 on ajettu. `era-sf-kisojen-vali`
    julkaistiin 6.9. klo 10:00:11, ja sen jonorivi lakaistiin 10.9. commitissa
    `65b3dd5` CDB:n `or-05`/`or-06`-siivouksen mukana — ääni mitattiin vasta
    16.9. (PUHDAS −2,8 dB). Tuomio olisi voinut olla RIKKI kymmenen vuorokautta
    ilman että mikään huomauttaa: orvon liitteen `--tila` löysi, poistetun rivin
    ei. **Tämä osio ei lue jonoa lainkaan** vaan Metan julkaisulistaa ja
    `viimeistely-loki.md`:tä, joten lakaistu rivi ei piilota mitään.

    ⛔ **Vain ERA.** Monologi ajaa 16.9. alkaen `--vain-todiste` (0/17 RIKKI),
    joten sillä ei ole äänituomiota jota kaivata; CDB julkaisee kuvia.
    ⛔ Äänituomio ei tarvitse Release-liitettä eikä jonoriviä — `tarkista_julkaisu.py`
    lataa Metan oman kopion `media_url`ista [todennettu 16.9.].
    ⚠️ Lippu ei ole todiste viasta: se sanoo että **tuomiota ei ole**, ei että
    ääni olisi rikki. Käsin puhelimesta julkaistu reeli lippuittuu samalla tavalla.
    """
    print("\n— ERA: JULKAISTU MUTTA ILMAN ÄÄNITUOMIOTA —")
    t = aja([sys.executable, TARKISTA, "--tili", ERA_TILI,
             "--n", str(reeleja), "--vain-todiste"])
    tuloste = (t.stdout + t.stderr).strip()
    # Koodi 2 = osalta puuttui `media_url`; rivit on silti tulostettu, joten
    # lista kelpaa. Muu nollasta poikkeava = lista jäi saamatta.
    rivit = re.findall(r"^(\d{4}-\d{2}-\d{2})\s+(\d{5,})\s*(\S*)",
                       tuloste, re.MULTILINE)
    if t.returncode not in (0, 2) or not rivit:
        print(f"  🛑 Julkaisulistaa ei saatu tilille `{ERA_TILI}` "
              f"(koodi {t.returncode}) — tarkistus EI ajanut.")
        print("  " + (viimeinen_rivi(t) or "(ei tulostetta)"))
        # ⛔ Ei hiljaista läpimenoa: lukematon lähde on tekemätöntä työtä, ei 0.
        return [f"{ERA_TILI}: äänituomioiden tarkistus ei ajanut (koodi {t.returncode})"]

    try:
        loki = open(RAPORTTI, encoding="utf-8").read()
    except OSError as e:
        print(f"  🛑 `viimeistely-loki.md` ei luettavissa: {e}")
        return ["viimeistely-loki.md: ei luettavissa, äänituomioita ei voi verrata"]

    tekematta = []
    for pvm, media_id, linkki in rivit:
        if pvm < ERA_ALKAA:
            print(f"  {pvm}  {media_id}  — lokia vanhempi (ennen {ERA_ALKAA}), ohitetaan")
            continue
        if media_id in loki:
            print(f"  {pvm}  {media_id}  ✓ tuomio lokissa")
            continue
        if media_id in jono_media_idt:
            print(f"  {pvm}  {media_id}  → rivi on yhä jonossa, ks. vaihe 5 yllä")
            continue
        print(f"  {pvm}  {media_id}  🔴 EI TUOMIOTA LOKISSA  {linkki}")
        print(f"      → AJA: python3 \"../../Instagram API/tarkista_julkaisu.py\" "
              f"--media-id {media_id} --alkuperainen ../../ERA/klipit/<lähde>.mp4")
        print(f"      → sitten kirjaa tuomio `viimeistely-loki.md`:hen käsin "
              f"(jonoriviä ei ole, joten `--id` ei auta)")
        tekematta.append(f"{media_id} ({pvm}): julkaistu, äänituomio puuttuu")
    return tekematta


def tila(reeleja=ERA_REELEJA):
    """`--tila` — lue tilan lähteet ja kerro mitä on tekemättä.

    📏 **Miksi (Miikan päätös 2026-09-16):** vaihe 5:n 27 ajossa 23.8.–16.9. oli
    6 poikkeamaa, eikä yksikään ollut se vika jota tarkistukset etsivät. Neljä
    kuudesta oli tilan epäsynkkaa — sama klippi elää neljässä paikassa eikä
    mikään komento kertonut mikä niistä on jäljessä:
      ① `origin/main:jono.json`  ② paikallinen `jono.json`  ③ Release-liitteet
      ④ Metan `media_id`.
    ⑤ **ERA:n julkaisulista vs. `viimeistely-loki.md`** (lisätty 16.9.) — neljä
    ensimmäistä lähtevät jonorivistä, eikä yksikään näe riviä joka on jo
    lakaistu jonosta. Ks. `era_ilman_tuomiota()`.
    Kaksi ajoa oli turhaa uusintaa (*«riviä ei ole jonossa»*), yksi osui
    kuvapostaukseen jolla ei ole lähdettä (or-07), ja yhdessä jonorivissä oli
    vanha `media_id` joka näytti äänivialta mutta oli kirjanpitovika (j23-k2).
    ⛔ Tämä komento ei muuta mitään — se lukee ja tulostaa.

    Poistumiskoodit: 0 = ei tekemistä · 1 = jotain tekemättä · 4 = ei luettavissa.
    """
    import todenna_siivous as ts

    try:
        for yritys in range(1, FETCH_YRITYKSET + 1):
            f = aja(["git", "-C", HERE, "fetch", "origin", "--quiet"])
            if f.returncode == 0:
                break
            if yritys < FETCH_YRITYKSET:
                time.sleep(FETCH_ODOTUS)
        else:
            print(f"🛑 `git fetch` epäonnistui {FETCH_YRITYKSET} kertaa — tilaa ei voi lukea.")
            return 4
    except OSError as e:
        print(f"🛑 git ei vastannut: {e}")
        return 4

    etaa, virhe = ts.jono_originista()
    if etaa is None:
        print(f"🛑 origin/main:jono.json ei luettavissa: {virhe}")
        return 4
    try:
        paikallinen = json.load(open(os.path.join(HERE, "jono.json"), encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"🛑 paikallinen jono.json ei luettavissa: {e}")
        return 4

    eta_idt = {r.get("id") for r in etaa}
    tekematta = []

    # Release-liitteet tageittain — yksi API-kutsu per tagi, ei per rivi.
    tagit = {}
    for r in etaa + paikallinen:
        video = (r.get("video") or "").strip()
        if "/" in video:
            tagit.setdefault(video.split("/", 1)[0], set()).add(video.split("/", 1)[1])
    saatavilla = {}
    for tagi in sorted(tagit):
        nimet, virhe = ts.liitteet(tagi)
        saatavilla[tagi] = None if nimet is None else set(nimet)
        if nimet is None:
            print(f"⚠️ Release-liitteitä ei saatu tagille `{tagi}`: {virhe}")

    print("\n— JONO (origin/main) —")
    if not etaa:
        print("  (tyhjä)")
    for r in etaa:
        rid, tila_ = r.get("id", "?"), r.get("tila", "?")
        aika = (r.get("aika") or "")[:16].replace("T", " ")
        video = (r.get("video") or "").strip()
        liite_tila = "—"
        if "/" in video:
            tagi, nimi = video.split("/", 1)
            joukko = saatavilla.get(tagi)
            if joukko is None:
                liite_tila = "liite ?"
            elif nimi in joukko:
                liite_tila = "liite ✓"
            else:
                liite_tila = "🔴 LIITE PUUTTUU"
        teko = "—"
        if tila_ == "julkaistu":
            teko = f"→ AJA: python3 viimeistele.py --id {rid}"
            tekematta.append(f"{rid}: julkaistu, vaihe 5 tekemättä")
        elif tila_ == "virhe":
            teko = "🔴 tila `virhe` — julkaise.py uusii, tarkista syy"
            tekematta.append(f"{rid}: tilassa virhe")
        elif tila_ == "odottaa" and liite_tila.startswith("🔴"):
            teko = "🔴 julkaisu antaa 404 — vie liite uudelleen ennen slottia"
            tekematta.append(f"{rid}: odottaa, mutta liite puuttuu")
        print(f"  {rid:<16} {tila_:<10} {aika:<16} {liite_tila:<17} {teko}")

    print("\n— VAIN PAIKALLISESTI (ei pushattu) —")
    vain_levylla = [r for r in paikallinen if r.get("id") not in eta_idt]
    if not vain_levylla:
        print("  (ei mitään — levy ja origin täsmäävät)")
    for r in vain_levylla:
        rid = r.get("id", "?")
        print(f"  🔴 {rid} — rivi on levyllä mutta EI originissa: commit + ./push.sh tekemättä")
        tekematta.append(f"{rid}: rivi ei ole originissa")
    if vain_levylla:
        print("     📏 Juuri tämä jätti j23-k2:n julkaisematta 15.9. — rivi oli "
              "kirjattu, klippiblokkiin merkitty «työnnetty», eikä committia ollut.")

    print("\n— ORVOT RELEASE-LIITTEET —")
    viitatut = {f"{t}/{n}" for t, nimet in tagit.items() for n in nimet}
    orpoja = False
    for tagi, joukko in saatavilla.items():
        for nimi in sorted(joukko or []):
            if f"{tagi}/{nimi}" not in viitatut:
                # Tagissa voi olla myös käytössä oleva liite — silloin orpo on
                # lähes aina vanha versio jonka `_v2` korvasi.
                vihje = ("  (tagissa on myös käytössä oleva liite ⇒ luultavasti "
                         "vanha versio)" if tagit.get(tagi) else "")
                print(f"  🔴 {tagi}/{nimi} — ei yhtään jonoriviä joka viittaisi "
                      f"siihen{vihje}")
                tekematta.append(f"{tagi}/{nimi}: orpo liite")
                orpoja = True
    if not orpoja:
        print("  (ei orpoja)")

    tekematta += era_ilman_tuomiota(
        {str(r.get("media_id") or "").strip() for r in etaa}, reeleja)

    print(f"\n— YHTEENSÄ: {len(tekematta)} tekemättä —")
    for rivi in tekematta:
        print(f"  • {rivi}")
    return 1 if tekematta else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", action="append", metavar="ID",
                    help="jonorivin id, esim. j20-k4. Voi antaa monta kertaa.")
    ap.add_argument("--tila", action="store_true",
                    help="älä siivoa mitään — lue tilan lähteet (jono, liitteet, "
                         "ERA:n julkaisut vs. äänituomiot) ja kerro mitä on "
                         "tekemättä. Aja tämä ENNEN vaihe 5:tä.")
    ap.add_argument("--reeleja", type=int, default=ERA_REELEJA, metavar="N",
                    help=f"vain --tila: montako ERA:n uusinta reeliä verrataan "
                         f"`viimeistely-loki.md`:hen (oletus {ERA_REELEJA})")
    ap.add_argument("--alkuperainen",
                    help="paikallinen mp4 johon julkaisua verrataan. Ilman tätä lähde "
                         "johdetaan jonorivin `video`-kentästä. Käy vain yhden --id:n kanssa.")
    ap.add_argument("--odota", type=int, default=60,
                    help="minuuttia jonka verran KUTAKIN id:tä odotetaan julkaistuksi (oletus 60)")
    a = ap.parse_args()

    if a.tila:
        if a.id:
            ap.error("--tila lukee koko jonon eikä ota --id:tä.")
        return tila(a.reeleja)
    if not a.id:
        ap.error("anna --id tai --tila")
    if a.alkuperainen and len(a.id) > 1:
        ap.error("--alkuperainen käy vain yhden --id:n kanssa — monella id:llä lähde "
                 "johdetaan jonorivin `video`-kentästä.")
    if a.alkuperainen and not os.path.isfile(a.alkuperainen):
        ap.error(f"alkuperäistä ei ole: {a.alkuperainen}")

    tulokset = []
    for rivi_id in a.id:
        koodi = kasittele(rivi_id, a.alkuperainen, a.odota)
        if koodi == 0:
            t_koodi, t_tuloste = todenna(rivi_id)
            print(f"\n— todennus: {rivi_id} —\n{t_tuloste}")
            if t_koodi != 0:
                kirjaa(f"\n🔴 **TODENNUS EI VAHVISTANUT SIIVOUSTA** · `{rivi_id}` · "
                       f"`todenna_siivous.py` koodi {t_koodi}\n"
                       f"```\n{t_tuloste[-1200:]}\n```\n"
                       f"⛔ Sama komento ei välttämättä korjaa tätä — lue tuloste ja "
                       f"korjaa se pää joka jäi.")
                koodi = 5
        pusha_raportti(rivi_id)   # ⛔ ei vaikuta koodiin — ks. funktion docstring
        tulokset.append((rivi_id, koodi))

    if len(tulokset) > 1:
        print("\n— yhteenveto —")
        for rivi_id, koodi in tulokset:
            print(f"  {rivi_id}: {koodi} — {SELITE.get(koodi, '?')}")
    return max(koodi for _, koodi in tulokset)


if __name__ == "__main__":
    sys.exit(main())
