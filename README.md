# Julkaisuautomaatio (ilmainen DIY-ajastin, monta tiliä)

Ajastaa Instagram-postaukset **ilman että kone on auki ja ilman kuukausimaksua.** GitHub Actions pyörii pilvessä, tarkistaa jonon ja julkaisee erääntyneet postaukset Metan rajapinnan kautta. Tilit: @coaches.database (kuvat) ja @monologi.podcast (reelit) — sama jono, kenttä `tili` valitsee.

```
jono.json  ──>  GitHub Actions (cron)  ──>  julkaise.py  ──>  Instagram
   ▲                                                   │
   └────────── merkitsee "julkaistu" takaisin ─────────┘
kuvat/         ──>  raw.githubusercontent.com  ─┐
Release-liite  ──>  github.com/…/releases/…  ───┴─>  Meta hakee median tästä itse
```

> 📖 **Tämä tiedosto vastaa vain siihen miten repoa käytetään.** Mitatut luvut, päätökset, tokenien tila ja lukitut linjaukset asuvat työtilassa: **`Projektit/Coaches Database/julkaisuautomaatio.md` (omistaja)** — ⛔ älä kopioi niitä tänne.

## Miten lisään postauksen jonoon

⚠️ **Aktiivinen lähde on `origin/main`, ei paikallinen työkopio** — lue `git show origin/main:jono.json` ja lisää uudet sen päälle. (Mitattu 07-20: paikallinen kopio oli 2 committia jäljessä ja siitä johdettu väite oli väärä.)

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
- `aika` — ISO-aika **+03:00** (kesäaika EEST) / **+02:00** (talvi EET). Julkaistaan kun tämä hetki on mennyt.
- `tila` — `"luonnos"` = ei julkaista vielä · `"odottaa"` = julkaistaan kun aika koittaa. Skripti vaihtaa sen → `"julkaistu"` tai `"virhe"`.
- `tili` — **valinnainen, oletus `cdb`.** Sallitut: `cdb` · `monologi` · `miikameier` · `teamera`. Tuntematon arvo pysäyttää sen rivin ennen yhtäkään verkkokutsua; muut rivit julkaistaan normaalisti.

## Miten lisään VIDEON (reel) jonoon

Video ei mene repoon — se viedään Release-liitteeksi, koska 40–60 MB tiedosto jäisi julkiseen git-historiaan pysyvästi.

```bash
python3 laheta_video.py "polku/jakso19_klippi4_TO.mp4"
```

Skripti luo tarvittaessa releasen, vie liitteen, **tarkistaa että julkinen osoite vastaa** ja tulostaa jonokentän. Lisää se riville:

```json
{
  "id": "j19-k4",
  "tili": "monologi",
  "video": "media/jakso19_klippi4_TO.mp4",
  "caption": "…",
  "aika": "2026-08-20T18:00:00+03:00",
  "tila": "odottaa"
}
```

- `video` — `"<release-tagi>/<tiedosto.mp4>"`. Vaihtoehtoisesti `video_url` = valmis julkinen osoite sellaisenaan (mikä tahansa isäntä).
- Video julkaistaan **reelinä** (`media_type=REELS`); Meta hakee tiedoston itse. Tämä on eri latauspolku kuin `Instagram API/ig_publish_reel.py`:n `rupload`, joka kaatuu yli ~60 s klipeillä.
- `collab` — valinnainen, `"miikameier"` tai lista. ⚠️ **Ei vielä mitattu:** Metan oma opas ei dokumentoi parametria. Jos se ei kelpaa, virhe tulee konttia luodessa eikä mitään mene ulos.
- **Liite saa poistua heti julkaisun jälkeen** (`python3 laheta_video.py --poista media/tiedosto.mp4`) — Instagram tallentaa oman kopionsa. Sama läpivirtaussääntö kuin `kuvat/`.

Committaa → aja `./push.sh` → Actions hoitaa loput. Tila päivittyy takaisin `jono.json`:iin automaattisesti. **Clauden koko työnkulku jonoon viemisestä siivoukseen: omistajatiedosto §Ajastus.**

## Kertaluontoinen käyttöönotto (GitHub)
1. **Luo julkinen repo** (esim. `cdb-julkaisin`). Julkinen, koska Instagram hakee kuvat raw-URL:sta + Actions-minuutit ovat julkisilla repoilla ilmaisia. Salaisuuksia ei ole repossa (`.env` on gitignoressa).
2. **Pushaa tämän kansion sisältö** repon juureen.
3. **Lisää 2 Secretiä** (repo → Settings → Secrets and variables → Actions):
   - `IG_TOKEN` = pitkäkestoinen access token (`Instagram API/.env` → `LONG_TOKEN`)
   - `IG_ID` = @coaches.database IG Business Account ID (`Instagram API/.env` → `IG_COACHES_DB`). Muiden tilien ID:t ovat `julkaise.py`:n allowlistissa — ne eivät ole salaisuuksia, joten uusi tili ei vaadi uutta secretiä. Tarvittaessa ohitus: `IG_ID_MONOLOGI` jne.
4. **Testaa:** Actions → "Julkaise Instagramiin" → Run workflow.

`push.sh` lukee `GH_TOKEN`:n **tämän kansion omasta `.env`:stä** (ei Instagram API:n).

## Paikallinen ajo — kun postaus on saatava ulos heti
Älä odota cronia. Tarvitsee vain julkisen kuva-URL:n perusosoitteen; token + IG-ID luetaan automaattisesti `../../Instagram API/.env`:stä.
```bash
RAW_BASE="https://raw.githubusercontent.com/<owner>/<repo>/main" python3 julkaise.py
```
Committaa ja pushaa `jono.json` heti perään.

## Rajat
- ⏱ **Cron ei aja luvattua 15 min tahtia** — postaus julkaistuu tyypillisesti tunteja myöhässä ajastetusta ajasta. **Mitatut luvut, syy ja purkuehto: omistajatiedosto §⏱ TODELLINEN AJOTAHTI.** ⛔ Älä lupaa "≤15 min".
- 📧 **Virhe → sähköposti + `tila: "virhe"` jonossa.** Uudelleenyritys on automaattinen: ohimenevä Metan virhe 4× saman ajon sisällä, `virhe`-rivi vielä 3 seuraavassa ajossa (`ajoyrityksia`), ja ennen uusintaa tarkistetaan ettei sama caption ole jo tilillä. ⚠️ **Kaatumismeili ei useimmiten ole meidän vika** — diagnoosin järjestys: omistajatiedosto §📧 Kaatumismeili.
- 🔑 **Kaksi tokenia voi rikkoa tämän.** Tila, päivät ja tekeminen: omistajatiedosto §⚠️ Kaksi vanhenevaa tokenia. ⛔ Älä kirjoita vanhenemispäiviä tähän tiedostoon.
- 💤 **Inaktiivisuus:** GitHub poistaa cronin käytöstä jos repoon ei kosketa 60 pv. Postausten lisääminen pitää sen elossa.
