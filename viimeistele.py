#!/usr/bin/env python3
"""
Vaihe 5 yhtenä komentona: odota että jonorivi on julkaistu → tarkista ääni →
poista Release-liite ja jonorivi → kirjaa tulos raporttitiedostoon.

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

Poistumiskoodit: 0 = valmis · 2 = ei edennyt (ei julkaistu määräajassa, ei
`media_id`:tä, tai lähdetiedostoa ei voitu johtaa) · 3 = ääni rikki TAI ei
tarkistettavissa · 4 = ääni puhdas mutta siivous jäi kesken (pull, liite tai
push epäonnistui) — **koodi 4 on aina korjattavissa samalla komennolla**. **Monella id:llä palautetaan suurin yksittäinen koodi**, ja
ajon lopussa tulostetaan yhteenveto id kerrallaan.

⛔ RAPORTTI VIEDÄÄN REMOTEEN OMANA COMMITTINAAN jokaisen id:n jälkeen
   (`viimeistely-loki.md`). Se EI muuta poistumiskoodia: koodi 4 lupaa
   *"korjattavissa samalla komennolla"*, eikä se päde raporttiin, koska
   jonorivi on siinä vaiheessa jo poissa. Epäonnistuminen tulostuu punaisena
   ja antaa tarkan korjauskomennon. [08-31: ennen tätä ajon ainoa todiste jäi
   pelkästään levylle — `j20-k7`:n rivi löytyi commitoimattomana ajon jälkeen.]

⛔ EI KIRJAA ONNISTUMISTA JOTA EI TAPAHTUNUT. Jokaisen alikomennon paluuarvo
   tarkistetaan; 08-23 j19-k7:n liitteen poisto epäonnistui ja loki sanoi silti
   ✅ PUHDAS · liite poistettu. Liite löytyi Releasesta 4 vrk myöhemmin.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PROJEKTIT = os.path.abspath(os.path.join(HERE, "..", ".."))
TARKISTA = os.path.join(PROJEKTIT, "Instagram API", "tarkista_julkaisu.py")
RAPORTTI = os.path.join(HERE, "viimeistely-loki.md")

# Mistä lähdetiedosto etsitään jonorivin `video`-kentän tiedostonimellä.
HAKUJUURET = [
    os.path.join(PROJEKTIT, "Henkilöbrändi", "Monologi", "Jaksot"),
    os.path.join(PROJEKTIT, "ERA", "klipit"),
]

SELITE = {
    0: "valmis",
    2: "ei edennyt — mitään ei poistettu",
    3: "ääni rikki tai ei tarkistettavissa — mitään ei poistettu",
    4: "ääni puhdas, siivous jäi kesken",
}


def aja(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def viimeinen_rivi(r):
    rivit = (r.stdout + r.stderr).strip().splitlines()
    return rivit[-1] if rivit else "—"


def etarivi(rivi_id):
    """Lue jonorivi GitHubin mainista — paikallinen kopio on aina jäljessä."""
    f = aja(["git", "-C", HERE, "fetch", "origin", "--quiet"])
    if f.returncode != 0:
        sys.exit(f"✗ git fetch epäonnistui — en lue vanhaa origin/mainia sokkona: "
                 f"{f.stderr.strip()[:200]}")
    r = aja(["git", "-C", HERE, "show", "origin/main:jono.json"])
    if r.returncode != 0:
        sys.exit(f"✗ jono.json ei luettavissa originista: {r.stderr.strip()[:200]}")
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


def kasittele(rivi_id, alkuperainen_kasin, odota):
    def otsikko():
        return f"\n## {datetime.now():%Y-%m-%d %H:%M} · {rivi_id}\n"

    rivi = etarivi(rivi_id)
    if rivi is None:
        kirjaa(otsikko() + "⚠️ Riviä ei ole jonossa. Joku on jo ajanut vaihe 5:n, "
                           "tai id on väärä. Ei tehty mitään.")
        return 0

    # 0) lähdetiedosto ensin — ilman sitä ei kannata odottaa tuntia
    alkuperainen = alkuperainen_kasin
    if not alkuperainen:
        alkuperainen, syy = johda_alkuperainen(rivi.get("video", ""))
        if not alkuperainen:
            kirjaa(otsikko() + f"🛑 Lähdetiedostoa ei voitu johtaa: {syy}\n"
                               f"Mitään ei tarkistettu eikä poistettu.")
            return 2
    if not os.path.isfile(alkuperainen):
        kirjaa(otsikko() + f"🛑 Alkuperäistä ei ole: {alkuperainen}\n"
                           f"Mitään ei tarkistettu eikä poistettu.")
        return 2
    print(f"\n▶ {rivi_id} — lähde: {alkuperainen}")

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
        rivi = etarivi(rivi_id)

    media_id = str(rivi.get("media_id") or "").strip()
    liite = rivi.get("video", "")
    if not media_id:
        kirjaa(otsikko() + "⚠️ Rivi on `julkaistu` mutta ilman `media_id`:tä — "
                           "en tarkista enkä poista sokkona.")
        return 2

    # 2) tarkista ääni Metan omasta transkoodauksesta
    t = aja([sys.executable, TARKISTA, "--media-id", media_id,
             "--alkuperainen", alkuperainen])
    tuloste = (t.stdout + t.stderr).strip()
    if t.returncode == 2:
        kirjaa(otsikko() + f"🛑 **EI TARKISTETTAVISSA** (`media_id {media_id}`) — Meta ei "
               f"palauttanut `media_url`ia, joten ääntä ei mitattu kertaakaan. Tätä "
               f"kohdellaan kuin RIKKI: liite ja rivi JÄTETTIIN paikalleen.\n"
               f"```\n{tuloste[-1200:]}\n```")
        return 3
    if t.returncode != 0:
        kirjaa(otsikko() + f"🔴 **ÄÄNI RIKKI tai tarkistus kaatui** (`media_id {media_id}`) — "
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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True, action="append", metavar="ID",
                    help="jonorivin id, esim. j20-k4. Voi antaa monta kertaa.")
    ap.add_argument("--alkuperainen",
                    help="paikallinen mp4 johon julkaisua verrataan. Ilman tätä lähde "
                         "johdetaan jonorivin `video`-kentästä. Käy vain yhden --id:n kanssa.")
    ap.add_argument("--odota", type=int, default=60,
                    help="minuuttia jonka verran KUTAKIN id:tä odotetaan julkaistuksi (oletus 60)")
    a = ap.parse_args()

    if a.alkuperainen and len(a.id) > 1:
        ap.error("--alkuperainen käy vain yhden --id:n kanssa — monella id:llä lähde "
                 "johdetaan jonorivin `video`-kentästä.")
    if a.alkuperainen and not os.path.isfile(a.alkuperainen):
        ap.error(f"alkuperäistä ei ole: {a.alkuperainen}")

    tulokset = []
    for rivi_id in a.id:
        koodi = kasittele(rivi_id, a.alkuperainen, a.odota)
        pusha_raportti(rivi_id)   # ⛔ ei vaikuta koodiin — ks. funktion docstring
        tulokset.append((rivi_id, koodi))

    if len(tulokset) > 1:
        print("\n— yhteenveto —")
        for rivi_id, koodi in tulokset:
            print(f"  {rivi_id}: {koodi} — {SELITE.get(koodi, '?')}")
    return max(koodi for _, koodi in tulokset)


if __name__ == "__main__":
    sys.exit(main())
