#!/usr/bin/env python3
"""
Vaihe 5 yhtenä komentona: odota että jonorivi on julkaistu → tarkista ääni →
poista Release-liite ja jonorivi → kirjaa tulos raporttitiedostoon.

    python3 viimeistele.py --id j19-k7 \
        --alkuperainen "/…/jakso19_klippi7_SU_v2.mp4" \
        --tili monologi.podcast

Miksi tämä on skripti eikä ajastettu Claude-prompti, joka tekisi samat viisi
askelta käsin: ajastettu tehtävä pysähtyy ensimmäiseen kirjoittavaan komentoon
ja jää odottamaan hyväksyntää jota kukaan ei ole antamassa [mitattu 08-18 ja
08-19, kaksi ajoa, molemmat tuloksetta — `automaatiot.md`]. Yksi komento =
yksi hyväksyntä, joka voidaan antaa etukäteen.

⛔ EI POISTA MITÄÄN JOS ÄÄNI ON RIKKI. Silloin liite ja rivi jäävät paikalleen,
   koska uusinta tarvitsee molemmat.

Poistumiskoodit: 0 = valmis · 2 = ei julkaistu määräajassa · 3 = ääni rikki ·
4 = ääni puhdas mutta siivous jäi kesken (liite, pull tai push epäonnistui).

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
TARKISTA = os.path.abspath(os.path.join(HERE, "..", "..", "Instagram API", "tarkista_julkaisu.py"))
RAPORTTI = os.path.join(HERE, "viimeistely-loki.md")


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


def kirjaa(teksti):
    with open(RAPORTTI, "a", encoding="utf-8") as f:
        f.write(teksti + "\n")
    print(teksti)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="jonorivin id, esim. j19-k7")
    ap.add_argument("--alkuperainen", required=True, help="paikallinen mp4 johon julkaisua verrataan")
    ap.add_argument("--tili", required=True, help="esim. monologi.podcast")
    ap.add_argument("--odota", type=int, default=60, help="minuuttia jonka verran odotetaan julkaisua")
    a = ap.parse_args()

    if not os.path.isfile(a.alkuperainen):
        sys.exit(f"✗ alkuperäistä ei ole: {a.alkuperainen}")

    # 1) odota että cron on julkaissut
    loppu = time.time() + a.odota * 60
    rivi = None
    while True:
        rivi = etarivi(a.id)
        if rivi is None:
            kirjaa(f"\n## {datetime.now():%Y-%m-%d %H:%M} · {a.id}\n"
                   f"⚠️ Riviä ei ole jonossa. Joku on jo ajanut vaihe 5:n, tai id on väärä. Ei tehty mitään.")
            return 0
        if rivi.get("tila") == "julkaistu":
            break
        if rivi.get("tila") == "virhe":
            kirjaa(f"\n## {datetime.now():%Y-%m-%d %H:%M} · {a.id}\n"
                   f"🔴 Rivi on tilassa `virhe`: {str(rivi.get('virhe'))[:300]}\n"
                   f"Liite ja rivi jätettiin paikalleen — `julkaise.py` uusii seuraavalla ajolla.")
            return 2
        if time.time() > loppu:
            kirjaa(f"\n## {datetime.now():%Y-%m-%d %H:%M} · {a.id}\n"
                   f"⏳ Ei julkaistu {a.odota} minuutissa (tila `{rivi.get('tila')}`). "
                   f"Mitään ei poistettu. Aja tämä uudestaan myöhemmin.")
            return 2
        time.sleep(180)

    media_id = str(rivi.get("media_id") or "").strip()
    liite = rivi.get("video", "")
    if not media_id:
        kirjaa(f"\n## {datetime.now():%Y-%m-%d %H:%M} · {a.id}\n"
               f"⚠️ Rivi on `julkaistu` mutta ilman `media_id`:tä — en tarkista enkä poista sokkona.")
        return 2

    # 2) tarkista ääni Metan omasta transkoodauksesta
    t = aja([sys.executable, TARKISTA, "--media-id", media_id,
             "--alkuperainen", a.alkuperainen, "--tili", a.tili])
    tuloste = (t.stdout + t.stderr).strip()
    if t.returncode != 0:
        kirjaa(f"\n## {datetime.now():%Y-%m-%d %H:%M} · {a.id}\n"
               f"🔴 **ÄÄNI RIKKI tai tarkistus kaatui** (`media_id {media_id}`) — "
               f"liite ja rivi JÄTETTIIN paikalleen.\n```\n{tuloste[-1200:]}\n```")
        return 3

    # 3) poista liite ja rivi — vasta kun tuomio on puhdas
    poistot, epaonnistui = [], []
    if liite:
        p = aja([sys.executable, os.path.join(HERE, "laheta_video.py"), "--poista", liite])
        poistot.append(f"{'✓' if p.returncode == 0 else '✗'} liite: {viimeinen_rivi(p)}")
        if p.returncode != 0:
            epaonnistui.append(f"Release-liite `{liite}` EI poistunut")

    pull = aja(["git", "-C", HERE, "pull", "--ff-only", "origin", "main"])
    if pull.returncode != 0:
        epaonnistui.append(f"git pull epäonnistui: {viimeinen_rivi(pull)}")
    jono_path = os.path.join(HERE, "jono.json")
    jono = json.load(open(jono_path, encoding="utf-8"))
    jaljelle = [r for r in jono if r.get("id") != a.id]
    if len(jaljelle) != len(jono):
        json.dump(jaljelle, open(jono_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        open(jono_path, "a", encoding="utf-8").write("\n")
        aja(["git", "-C", HERE, "add", "jono.json"])
        aja(["git", "-C", HERE, "commit", "-q", "-m",
             f"jono: {a.id} julkaistu (media_id {media_id}), rivi pois vaihe 5:n mukaan"])
        pu = aja(["sh", os.path.join(HERE, "push.sh")])
        poistot.append(f"{'✓' if pu.returncode == 0 else '✗'} push: {viimeinen_rivi(pu)}")
        if pu.returncode != 0:
            epaonnistui.append("jonorivin poisto jäi PAIKALLISEKSI — remotessa rivi on yhä")

    if epaonnistui:
        kirjaa(f"\n## {datetime.now():%Y-%m-%d %H:%M} · {a.id}\n"
               f"⚠️ **ÄÄNI PUHDAS, MUTTA SIIVOUS JÄI KESKEN** · `media_id` **{media_id}**\n"
               + "\n".join(f"- 🔴 {x}" for x in epaonnistui) + "\n"
               + "\n".join(f"- {x}" for x in poistot))
        return 4

    kirjaa(f"\n## {datetime.now():%Y-%m-%d %H:%M} · {a.id}\n"
           f"✅ **PUHDAS** · `media_id` **{media_id}** · liite `{liite}` poistettu · jonorivi poistettu\n"
           f"```\n{tuloste[-700:]}\n```\n"
           f"➡️ Jäljellä: kirjaa `media_id` jakson `…_julkaisumateriaalit.md`:hen.\n"
           + "\n".join(f"- {x}" for x in poistot))
    return 0


if __name__ == "__main__":
    sys.exit(main())
