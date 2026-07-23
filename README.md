# CDB-julkaisuautomaatio (ilmainen DIY-ajastin)

Ajastaa Instagram-postaukset @coaches.databaseen **ilman että kone on auki ja ilman kuukausimaksua.** GitHub Actions pyörii pilvessä 15 min välein, tarkistaa jonon ja julkaisee erääntyneet postaukset Metan rajapinnan kautta.

```
jono.json  ──>  GitHub Actions (cron 15 min)  ──>  julkaise.py  ──>  Instagram
   ▲                                                   │
   └────────── merkitsee "julkaistu" takaisin ─────────┘
kuvat/  ──>  raw.githubusercontent.com  ──>  Instagram hakee kuvan tästä
```

## Miten lisään postauksen jonoon

Jonon tila: `Projektit/Coaches Database/Julkaisuautomaatio/jono.json` (omistaja). ⚠️ **Aktiivinen lähde on `origin/main`, ei paikallinen työkopio** — lue `git show origin/main:jono.json`. (Mitattu 07-20: paikallinen kopio oli 2 committia jäljessä ja siitä johdettu väite oli väärä.)

Lisää `jono.json`:iin objekti ja vaihda `tila` → `"odottaa"`:

```json
{
  "id": "vt-04",
  "otsikko": "PALAUTE (ON)",
  "kuva": "kuvat/04-palaute.png",
  "caption": "Mikä valmennuksessa...\n\n#valmennus #fitness ...",
  "aika": "2026-07-08T18:00:00+03:00",
  "tila": "odottaa"
}
```

- `kuva` — polku repossa. Lisää kuvatiedosto `kuvat/`-kansioon (ascii-nimi, ei välilyöntejä/ääkkösiä).
- `caption` — koko teksti hashtageineen. Rivinvaihto = `\n`.
- `aika` — ISO-aika **+03:00** (Suomen kesäaika EEST) / **+02:00** (talvi EET). Julkaistaan kun tämä hetki on mennyt.
- `tila` — `"luonnos"` = ei julkaista vielä. `"odottaa"` = julkaistaan kun aika koittaa. Skripti vaihtaa sen → `"julkaistu"` tai `"virhe"`.

Committaa muutos → Actions hoitaa loput. Tila päivittyy takaisin `jono.json`:iin automaattisesti.

## Kertaluontoinen käyttöönotto (GitHub)
1. **Luo julkinen repo** GitHubissa (esim. `cdb-julkaisin`). Julkinen, koska Instagram hakee kuvat raw-URL:sta + Actions-minuutit ovat julkisilla repoilla ilmaisia.
2. **Pushaa tämän kansion sisältö** repon juureen (ks. alempi git-komennot).
3. **Lisää 2 Secretiä** (repo → Settings → Secrets and variables → Actions → New repository secret):
   - `IG_TOKEN` = pitkäkestoinen access token (`Instagram API/.env` → `LONG_TOKEN`)
   - `IG_ID` = @coaches.database IG Business Account ID (`Instagram API/.env` → `IG_COACHES_DB`)
4. **Testaa:** Actions-välilehti → "Julkaise Instagramiin" → Run workflow. Tai aseta yhden postauksen `aika` muutaman minuutin päähän ja `tila: "odottaa"`.

## Token — ei deadlinea (korjattu 2026-07-21)
❌ **Tässä luki aiemmin "vanhenee — hoidettava ennen ~2026-07-31" ja "voimassa vain 60 pv". Molemmat olivat vääriä.** Metalta kysyttiin ensimmäistä kertaa 07-21 (`debug_token`): token **ei vanhene**. Ainoa kello on data-access-ikkuna, ja se asuu omistajallaan.
**Tila, mitattu fakta ja tekeminen: `Projektit/Instagram API/CLAUDE.md` §AVOIMET 1. rivi (omistaja).** Muistutus on Apple Calendarissa. ⛔ **Älä kirjoita päivämäärää tähän tiedostoon** — juuri se kopioituminen tuotti kahden eri päivän tilanteen (root `CLAUDE.md` §Osoitinsääntö).
⛔ **Älä ehdota system-user-tokenia.** Se luki tässä "kestävänä korjauksena", mutta **Meta esti sen 07-21** (appi ja IG-tilit ovat eri yritysportfolioissa). Mittaus ja purkuehto: sama omistajarivi.

## Rajat ja varautuminen
- **Cron-tarkkuus:** GitHub voi viivästyttää ajoa 5–15 min ruuhkassa. Siksi julkaisuikkuna (18–20) eikä tarkka minuutti.
- **Virhe → sähköposti:** jos julkaisu epäonnistuu, ajo merkitään punaiseksi ja GitHub lähettää repo-omistajalle sähköpostin. Postaus saa `tila: "virhe"` + virheviesti jonossa.
- **Inaktiivisuus:** GitHub poistaa cronin käytöstä jos repoon ei kosketa 60 pv. Postausten lisääminen pitää sen elossa.

## Paikallinen testi (valinnainen)
Ennen GitHubia voi ajaa koneelta. Tarvitsee julkisen kuva-URL:n (`RAW_BASE`) — toimii vasta kun repo on GitHubissa, tai anna jokin muu julkinen kuvaosoite:
```bash
RAW_BASE="https://raw.githubusercontent.com/<owner>/<repo>/main" python3 julkaise.py
```
Token + IG-ID luetaan automaattisesti `../../Instagram API/.env`:stä paikallisessa ajossa.
