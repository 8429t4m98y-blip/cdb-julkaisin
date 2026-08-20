"""Testit julkaise.py:lle — verkkokutsut korvattu, mitään ei mene ulos Instagramiin.

    python3 testaa_julkaise.py        # 26 tarkistusta, exit 1 jos yksikin hylätty

⛔ AJA TÄMÄ ENNEN KUIN MUUTAT julkaise.py:tä. Neljästä tähänastisesta muutoksesta
kaksi oli korjaus juuri siihen uusinta- ja tuplasuojalogiikkaan jota nämä testit
vartioivat, eikä workflow aja testejä puolestasi.

Todistettu mutaatiotestillä 2026-08-20: kun tuplajulkaisun korjaus palautetaan
takaisin vialliseksi, kolme testiä hajoaa (mm. "mediaa ei julkaistu uudelleen").
"""
import importlib.util, json, os, shutil, sys, tempfile, urllib.error, io

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "julkaise.py")
ok = fail = 0

def tarkista(nimi, ehto, lisa=""):
    global ok, fail
    if ehto: ok += 1; print(f"  ok   {nimi}")
    else:    fail += 1; print(f"  FAIL {nimi} {lisa}")

def lataa(jono, kutsut, kaada_rivilla=None):
    """Lataa tuore moduuli tilapäishakemistoon, korvaa API-kutsut."""
    d = tempfile.mkdtemp()
    shutil.copy(SRC, os.path.join(d, "julkaise.py"))
    with open(os.path.join(d, "jono.json"), "w", encoding="utf-8") as f:
        json.dump(jono, f, ensure_ascii=False)
    spec = importlib.util.spec_from_file_location(f"j{len(kutsut)}{id(d)}", os.path.join(d, "julkaise.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

    tilat = {"julkaistut": 0}
    def api_post(path, params):
        kutsut.append(("POST", path, params))
        if path.endswith("/media"):
            return {"id": "CID_UUSI"}
        tilat["julkaistut"] += 1
        if kaada_rivilla == "publish":
            raise urllib.error.HTTPError("u", 400, "b", {}, io.BytesIO(b'{"error":{"code":100}}'))
        return {"id": f"MEDIA_{tilat['julkaistut']}"}
    def api_get(path, params):
        kutsut.append(("GET", path, params))
        if path.endswith("/media"):
            return {"data": [{"id": "VANHA_MEDIA", "caption": "jo tililla"}]}
        if path == "CID_KUOLLUT":
            return {"status_code": "ERROR", "status": "testi"}
        return {"status_code": "FINISHED"}
    m.api_post, m.api_get = api_post, api_get
    m.time.sleep = lambda s: None
    os.environ.update({"IG_TOKEN": "T", "RAW_BASE": "https://raw/x", "RELEASE_BASE": "https://rel/x"})
    return m, d

def aja(jono, kaada_rivilla=None):
    kutsut = []
    m, d = lataa(jono, kutsut, kaada_rivilla)
    buf, sys.stdout = sys.stdout, io.StringIO()
    koodi = 0
    try: m.main()
    except SystemExit as e: koodi = e.code or 0
    finally: sys.stdout = buf
    tulos = json.load(open(os.path.join(d, "jono.json"), encoding="utf-8"))
    return tulos, kutsut, koodi

MENNYT, TULEVA = "2020-01-01T12:00:00+00:00", "2099-01-01T12:00:00+00:00"
def rivi(**kw):
    p = {"id": "r1", "caption": "teksti", "aika": MENNYT, "tila": "odottaa", "kuva": "kuvat/a.jpg"}
    p.update(kw); return p

print("\n— perustoiminta (regressio: kuvarivit) —")
t, k, _ = aja([rivi()])
tarkista("kuva julkaistaan, tila+media_id talteen", t[0]["tila"] == "julkaistu" and t[0]["media_id"] == "MEDIA_1")
tarkista("kuvan osoite raw_basesta", any(p.get("image_url") == "https://raw/x/kuvat/a.jpg" for _, _, p in k if "image_url" in p))
tarkista("creation_id siivottu onnistuneelta rivilta", "creation_id" not in t[0])

t, k, _ = aja([rivi(kuva=None, video="media/v.mp4", tili="monologi")])
tarkista("video menee REELSina", any(p.get("media_type") == "REELS" for _, _, p in k if "media_type" in p))
tarkista("videon osoite release_basesta", any(p.get("video_url") == "https://rel/x/media/v.mp4" for _, _, p in k if "video_url" in p))
tarkista("monologin tili-id valittu", any("17841435019135389" in pa for _, pa, _ in k))

print("\n— portit: rikkinaiset rivit eivat koske verkkoon —")
for nimi, r in [("tuntematon tili", rivi(tili="ei-ole")),
                ("ei mediakenttaa", rivi(kuva=None)),
                ("tyhja kuvateksti", rivi(caption="   ")),
                ("video ilman tiedostonimea", rivi(kuva=None, video="pelkkatagi"))]:
    t, k, koodi = aja([r])
    tarkista(f"{nimi} -> virhe, 0 verkkokutsua", t[0]["tila"] == "virhe" and len(k) == 0, f"kutsuja {len(k)}")
tarkista("virheellinen rivi -> exit 1 (GitHub lahettaa meilin)", koodi == 1)

t, k, _ = aja([rivi(aika="rikki")])
tarkista("kelvoton aika -> ohitetaan, tila ennallaan", t[0]["tila"] == "odottaa" and len(k) == 0)

print("\n— tuleva rivi ja jo kasitellyt —")
t, k, _ = aja([rivi(aika=TULEVA)])
tarkista("tuleva rivi koskematon", t[0]["tila"] == "odottaa" and len(k) == 0)
t, k, _ = aja([rivi(tila="julkaistu")])
tarkista("julkaistua ei julkaista uudelleen", len(k) == 0)
t, k, _ = aja([rivi(tila="virhe", ajoyrityksia=3)])
tarkista("yritykset kaytetty -> ei uutta yritysta", len(k) == 0)

print("\n— UUSI: tuplajulkaisun aukko —")
t, k, _ = aja([rivi(creation_id="CID_VANHA", caption="jo tililla")])
tarkista("kesken jaanyt rivi tarkistaa tilin ENSIN", k and k[0][0] == "GET" and k[0][1].endswith("/media"))
tarkista("jo tilillä oleva -> merkitaan julkaistuksi, EI julkaista", t[0]["tila"] == "julkaistu" and t[0]["media_id"] == "VANHA_MEDIA")
tarkista("mediaa ei julkaistu uudelleen", not any(pa.endswith("media_publish") for _, pa, _ in k))

t, k, _ = aja([rivi(creation_id="CID_VANHA", caption="ei tilillä")])
tarkista("kesken jaanyt jota EI ole tilillä -> jatkaa vanhaa konttia", not any(pa.endswith("/media") and me == "POST" for me, pa, _ in k))
tarkista("… ja julkaisee sen", t[0]["tila"] == "julkaistu")

t, k, _ = aja([rivi(creation_id="CID_KUOLLUT", caption="ei tilillä")])
tarkista("kuollut kontti -> luodaan uusi", any(me == "POST" and pa.endswith("/media") for me, pa, _ in k))

print("\n— UUSI: tila levylle joka rivin jalkeen —")
t, k, koodi = aja([rivi(id="a"), rivi(id="b", caption="toinen")])
tarkista("kaksi rivia, molemmat julkaistu", all(r["tila"] == "julkaistu" for r in t))
t, k, koodi = aja([rivi(id="a"), rivi(id="b", tili="ei-ole")], )
tarkista("rikkinainen rivi ei kaada tervetta rivia", t[0]["tila"] == "julkaistu" and t[1]["tila"] == "virhe")

t, k, _ = aja([rivi()], kaada_rivilla="publish")
tarkista("julkaisuvirhe -> creation_id JAA riville uusintaa varten", t[0].get("creation_id") == "CID_UUSI")
tarkista("… ja ajoyrityksia kasvaa", t[0].get("ajoyrityksia") == 1)

print("\n— collab —")
t, k, _ = aja([rivi(collab="joku")])
tarkista("collab menee listana konttikutsuun", any(p.get("collaborators") == '["joku"]' for _, _, p in k if "collaborators" in p))

print(f"\n{ok} lapi, {fail} hylatty")
sys.exit(1 if fail else 0)
