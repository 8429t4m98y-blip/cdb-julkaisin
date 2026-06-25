# CDB-julkaisuautomaatio (ilmainen DIY-ajastin)

Ajastaa Instagram-postaukset @coaches.databaseen **ilman että kone on auki ja ilman kuukausimaksua.** GitHub Actions pyörii pilvessä 15 min välein, tarkistaa jonon ja julkaisee erääntyneet postaukset Metan rajapinnan kautta.

```
jono.json  ──>  GitHub Actions (cron 15 min)  ──>  julkaise.py  ──>  Instagram
   ▲                                                   │
   └────────── merkitsee "julkaistu" takaisin ─────────┘
kuvat/  ──>  raw.githubusercontent.com  ──>  Instagram hakee kuvan tästä
```

## Miten lisään postauksen jonoon
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

## ⚠️ Token vanhenee — hoidettava ennen ~2026-07-31
`LONG_TOKEN` on voimassa vain 60 pv. Ajastin lakkaa toimimasta kun se vanhenee.
**Kestävä korjaus:** luo **system-user-token** Metan Business Managerissa (Business Settings → System Users → lisää token, oikeudet `instagram_basic` + `instagram_content_publish` + `pages_read_engagement`). Se **ei vanhene** → päivitä `IG_TOKEN`-Secret kerran, ei enää huolta.

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
