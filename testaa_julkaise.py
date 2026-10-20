"""Testit julkaise.py:lle — verkkokutsut korvattu, mitään ei mene ulos Instagramiin.

    python3 testaa_julkaise.py        # tarkistusten maara tulostuu loppuun, exit 1 jos yksikin hylätty

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

    tilat = {"julkaistut": 0, "lapsia": 0}
    def api_post(path, params):
        kutsut.append(("POST", path, params))
        if path.endswith("/media"):
            if kaada_rivilla == "kansi" and "cover_url" in params:
                raise urllib.error.HTTPError("u", 400, "b", {}, io.BytesIO(b'{"error":{"code":100}}'))
            if kaada_rivilla == "collab" and "collaborators" in params:
                raise urllib.error.HTTPError("u", 400, "b", {}, io.BytesIO(b'{"error":{"code":100}}'))
            if params.get("media_type") == "STORIES":
                if kaada_rivilla == "story":
                    raise urllib.error.HTTPError("u", 400, "b", {}, io.BytesIO(b'{"error":{"code":100,"error_subcode":2207082}}'))
                return {"id": "STORY_CID"}
            if params.get("is_carousel_item") == "true":     # karusellin lapsikontti
                tilat["lapsia"] += 1
                return {"id": f"LAPSI_{tilat['lapsia']}"}
            return {"id": "CID_UUSI"}
        tilat["julkaistut"] += 1
        if kaada_rivilla == "publish":
            raise urllib.error.HTTPError("u", 400, "b", {}, io.BytesIO(b'{"error":{"code":100}}'))
        return {"id": f"MEDIA_{tilat['julkaistut']}"}
    def api_get(path, params):
        kutsut.append(("GET", path, params))
        if path.endswith("/media"):
            return {"data": [{"id": "VANHA_MEDIA", "caption": "jo tililla"}]}
        if path.endswith("/stories"):
            if kaada_rivilla == "story_jo":       # julkaistu rivin ajan (MENNYT 12.00) jalkeen
                return {"data": [{"id": "VANHA_STORY", "timestamp": "2020-01-01T12:05:00+0000"}]}
            if kaada_rivilla == "story_vanha":    # edellisen slotin story, ennen rivin aikaa
                return {"data": [{"id": "EDELLINEN_STORY", "timestamp": "2020-01-01T11:00:00+0000"}]}
            return {"data": []}
        if path == "CID_KUOLLUT" or path == "LAPSI_KUOLLUT" or (kaada_rivilla == "lapsi_error" and path.startswith("LAPSI_")):
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

t, k, _ = aja([rivi(collab="joku")])
tarkista("onnistunut collab -> ei collab_pudotettu-merkintaa", "collab_pudotettu" not in t[0])
t, k, _ = aja([rivi(collab="joku")], kaada_rivilla="collab")
konttipostit = [p for me, pa, p in k if me == "POST" and pa.endswith("/media")]
tarkista("hylatty collab -> uusi kontti ilman collabia, kuva julkaistaan",
         t[0]["tila"] == "julkaistu" and len(konttipostit) == 2 and "collaborators" in konttipostit[0] and "collaborators" not in konttipostit[1])
tarkista("… ja riville jaa collab_pudotettu", t[0].get("collab_pudotettu") is True)
t, k, _ = aja([rivi(kuva=None, kuvat=["kuvat/k1.jpg", "kuvat/k2.jpg"], collab="kim")], kaada_rivilla="collab")
emot = [p for me, pa, p in k if me == "POST" and pa.endswith("/media") and p.get("media_type") == "CAROUSEL"]
tarkista("karuselli: hylatty collab -> emo ilman collabia, lapsia ei luoda uudelleen",
         t[0]["tila"] == "julkaistu" and len(emot) == 2 and "collaborators" not in emot[1] and emot[1]["children"] == "LAPSI_1,LAPSI_2" and t[0].get("collab_pudotettu") is True)
t, k, _ = aja([rivi(kuva=None, video="media/v.mp4", kansi_url="https://raw/x/kuvat/k.png", collab="joku")], kaada_rivilla="collab")
viimeinen = [p for me, pa, p in k if me == "POST" and pa.endswith("/media")][-1]
tarkista("reel: hylatty collab -> kansi sailyy, collab pois", t[0]["tila"] == "julkaistu" and viimeinen.get("cover_url") and "collaborators" not in viimeinen)

print("\n— kansikuva —")
t, k, _ = aja([rivi(kuva=None, video="media/v.mp4", kansi_url="https://raw/x/kuvat/k.png")])
tarkista("kansi_url menee cover_urlina reelin konttiin", any(p.get("cover_url") == "https://raw/x/kuvat/k.png" for _, _, p in k))
t, k, _ = aja([rivi(kansi_url="https://raw/x/kuvat/k.png")])
tarkista("kuvarivi ei laheta cover_urlia", not any("cover_url" in p for _, _, p in k))
t, k, _ = aja([rivi(kuva=None, video="media/v.mp4", kansi_url="https://raw/x/kuvat/k.png")], kaada_rivilla="kansi")
tarkista("hylatty kansi -> uusi kontti ilman kantta, reel julkaistaan", t[0]["tila"] == "julkaistu" and sum(1 for me, pa, _ in k if me == "POST" and pa.endswith("/media")) == 2)

def lapsi_kutsut(k):
    return [p for me, pa, p in k if me == "POST" and pa.endswith("/media") and p.get("is_carousel_item") == "true"]
def emo_kutsut(k):
    return [p for me, pa, p in k if me == "POST" and pa.endswith("/media") and p.get("media_type") == "CAROUSEL"]
def julkaisut(k):
    return [p for me, pa, p in k if me == "POST" and pa.endswith("media_publish")]

KUVAT3 = ["kuvat/k1.jpg", "kuvat/k2.jpg", "kuvat/k3.jpg"]

print("\n— karuselli: Graph API -kulku —")
t, k, koodi = aja([rivi(kuva=None, kuvat=KUVAT3)])
tarkista("karuselli julkaistaan, tila+media_id talteen", t[0]["tila"] == "julkaistu" and t[0]["media_id"] == "MEDIA_1" and koodi == 0)
tarkista("3 lapsikonttia, image_url raw_basesta oikeassa jarjestyksessa",
         [p.get("image_url") for p in lapsi_kutsut(k)] == ["https://raw/x/kuvat/k1.jpg", "https://raw/x/kuvat/k2.jpg", "https://raw/x/kuvat/k3.jpg"])
tarkista("lapsella ei kuvatekstia eika media_typea", all("caption" not in p and "media_type" not in p for p in lapsi_kutsut(k)))
tarkista("emokontti: CAROUSEL + children + caption", len(emo_kutsut(k)) == 1 and emo_kutsut(k)[0]["children"] == "LAPSI_1,LAPSI_2,LAPSI_3" and emo_kutsut(k)[0]["caption"] == "teksti")
tarkista("julkaistaan emokontti (ei lasta)", len(julkaisut(k)) == 1 and julkaisut(k)[0]["creation_id"] == "CID_UUSI")
jarj = [("emo" if p.get("media_type") == "CAROUSEL" else "lapsi") for me, pa, p in k if me == "POST" and pa.endswith("/media")]
tarkista("lapset luodaan ennen emoa", jarj == ["lapsi", "lapsi", "lapsi", "emo"])
ensimmainen_emo = next(i for i, (me, pa, p) in enumerate(k) if p.get("media_type") == "CAROUSEL")
tarkista("jokaisen lapsen tila (GET) kysytaan ennen emoa", {pa for me, pa, _ in k[:ensimmainen_emo] if me == "GET"} >= {"LAPSI_1", "LAPSI_2", "LAPSI_3"})
tarkista("emon tila (GET) kysytaan ennen julkaisua", any(me == "GET" and pa == "CID_UUSI" for me, pa, _ in k))
tarkista("creation_id + lapsi_idt siivottu onnistuneelta rivilta", "creation_id" not in t[0] and "lapsi_idt" not in t[0])

t, k, _ = aja([rivi(kuva=None, kuvat=["kuvat/k1.jpg", "media/v.mp4", "kuvat/k3.jpg"], tili="miikameier")])
tarkista("videokohde: media_type=VIDEO + video_url Release-osoitteesta + is_carousel_item",
         any(p.get("media_type") == "VIDEO" and p.get("video_url") == "https://rel/x/media/v.mp4" and p.get("is_carousel_item") == "true" for p in lapsi_kutsut(k)))
tarkista("videolapsi ei ole REELS", not any(p.get("media_type") == "REELS" for _, _, p in k if "media_type" in p))
tarkista("sekakaruselli julkaistaan, miikameierin tili-id", t[0]["tila"] == "julkaistu" and any("17841400232383202" in pa for _, pa, _ in k))

t, k, _ = aja([rivi(kuva=None, kuvat=KUVAT3, collab="kim")])
tarkista("collab vain emokonttiin", emo_kutsut(k)[0].get("collaborators") == '["kim"]' and not any("collaborators" in p for p in lapsi_kutsut(k)))
t, k, _ = aja([rivi(kuva=None, kuvat=KUVAT3)])
tarkista("ilman collabia ei collaborators-kenttaa", not any("collaborators" in p for _, _, p in k if isinstance(p, dict)))

print("\n— karuselli: validointi ennen verkkoa —")
for nimi, r in [("1 kohde", rivi(kuva=None, kuvat=["kuvat/a.jpg"])),
                ("tyhja lista", rivi(kuva=None, kuvat=[])),
                ("11 kohdetta", rivi(kuva=None, kuvat=[f"kuvat/{n}.jpg" for n in range(11)])),
                ("kuvat + kuva", rivi(kuvat=KUVAT3)),
                ("kuvat + video", rivi(kuva=None, video="media/v.mp4", kuvat=KUVAT3)),
                ("kuvat + video_url", rivi(kuva=None, video_url="https://x/v.mp4", kuvat=KUVAT3)),
                ("kuvat ei lista", rivi(kuva=None, kuvat="kuvat/a.jpg")),
                ("tyhja alkio", rivi(kuva=None, kuvat=["kuvat/a.jpg", "  "])),
                ("alkio ei merkkijono", rivi(kuva=None, kuvat=["kuvat/a.jpg", 5])),
                ("videokohde ilman tagia", rivi(kuva=None, kuvat=["kuvat/a.jpg", "v.mp4"]))]:
    t, k, koodi = aja([r])
    tarkista(f"{nimi} -> virhe, 0 verkkokutsua", t[0]["tila"] == "virhe" and len(k) == 0 and t[0].get("virhe"), f"kutsuja {len(k)} virhe={t[0].get('virhe')}")
t, k, _ = aja([rivi(kuva=None, kuvat=["kuvat/a.jpg", "kuvat/b.jpg"])])
tarkista("alaraja 2 kohdetta kelpaa", t[0]["tila"] == "julkaistu")
t, k, _ = aja([rivi(kuva=None, kuvat=[f"kuvat/{n}.jpg" for n in range(10)])])
tarkista("ylaraja 10 kohdetta kelpaa", t[0]["tila"] == "julkaistu" and len(lapsi_kutsut(k)) == 10)
t, k, _ = aja([rivi(id="a", kuva=None, kuvat=["kuvat/a.jpg"]), rivi(id="b", caption="toinen", kuva=None, kuvat=KUVAT3), rivi(id="c", caption="kolmas")])
tarkista("virheellinen karuselli ei kaada muita rivejä", [r["tila"] for r in t] == ["virhe", "julkaistu", "julkaistu"])
tarkista("virheviesti kertoo kohteen numeron", "kohde" in aja([rivi(kuva=None, kuvat=["kuvat/a.jpg", ""])])[0][0]["virhe"])

print("\n— karuselli: turvat (tuplasuoja, uusinta, virheet) —")
t, k, _ = aja([rivi(kuva=None, kuvat=KUVAT3, caption="jo tililla")])
tarkista("jo tilillä -> julkaistuksi, EI lapsia/emoa/julkaisua", t[0]["tila"] == "julkaistu" and t[0]["media_id"] == "VANHA_MEDIA" and not lapsi_kutsut(k) and not emo_kutsut(k) and not julkaisut(k))
t, k, _ = aja([rivi(kuva=None, kuvat=KUVAT3, caption="jo tililla", lapsi_idt=["LAPSI_A"], creation_id="CID_X")])
tarkista("jo tilillä -> kesken jaaneet idt siivotaan", "lapsi_idt" not in t[0] and "creation_id" not in t[0])

t, k, _ = aja([rivi(kuva=None, kuvat=KUVAT3)], kaada_rivilla="publish")
tarkista("julkaisuvirhe -> emo + lapset JAAVAT riville uusintaa varten", t[0]["tila"] == "virhe" and t[0].get("creation_id") == "CID_UUSI" and t[0].get("lapsi_idt") == ["LAPSI_1", "LAPSI_2", "LAPSI_3"])
tarkista("… ja ajoyrityksia kasvaa", t[0].get("ajoyrityksia") == 1)

t, k, koodi = aja([rivi(kuva=None, kuvat=KUVAT3)], kaada_rivilla="lapsi_error")
tarkista("lapsikontti ERROR -> virhe, emoa EI luoda eika julkaista", t[0]["tila"] == "virhe" and not emo_kutsut(k) and not julkaisut(k) and koodi == 1)
tarkista("… ja luotu lapsi jää riville", t[0].get("lapsi_idt") == ["LAPSI_1"])

t, k, _ = aja([rivi(kuva=None, kuvat=KUVAT3, tila="virhe", ajoyrityksia=1, creation_id="CID_VANHA", lapsi_idt=["LAPSI_A", "LAPSI_B", "LAPSI_C"], caption="ei tilillä")])
tarkista("uusinta valmiilla emolla -> ei uusia kontteja", t[0]["tila"] == "julkaistu" and not lapsi_kutsut(k) and not emo_kutsut(k) and julkaisut(k)[0]["creation_id"] == "CID_VANHA")
t, k, _ = aja([rivi(kuva=None, kuvat=KUVAT3, creation_id="CID_KUOLLUT", lapsi_idt=["LAPSI_A", "LAPSI_B", "LAPSI_C"], caption="ei tilillä")])
tarkista("kuollut emo -> kaikki luodaan alusta (3 lasta + emo)", t[0]["tila"] == "julkaistu" and len(lapsi_kutsut(k)) == 3 and len(emo_kutsut(k)) == 1)
t, k, _ = aja([rivi(kuva=None, kuvat=KUVAT3, lapsi_idt=["LAPSI_A"], caption="ei tilillä")])
tarkista("1/3 lasta valmiina -> luodaan vain 2 puuttuvaa", len(lapsi_kutsut(k)) == 2 and emo_kutsut(k)[0]["children"] == "LAPSI_A,LAPSI_1,LAPSI_2")
t, k, _ = aja([rivi(kuva=None, kuvat=KUVAT3, lapsi_idt=["LAPSI_A", "LAPSI_B", "LAPSI_C"], caption="ei tilillä")])
tarkista("kaikki lapset valmiina, ei emoa -> vain emo luodaan", not lapsi_kutsut(k) and len(emo_kutsut(k)) == 1 and t[0]["tila"] == "julkaistu")
t, k, _ = aja([rivi(kuva=None, kuvat=KUVAT3, lapsi_idt=["LAPSI_KUOLLUT", "LAPSI_B", "LAPSI_C"], caption="ei tilillä")])
tarkista("kuollut lapsi -> vain se luodaan uudelleen", len(lapsi_kutsut(k)) == 1 and emo_kutsut(k)[0]["children"] == "LAPSI_1,LAPSI_B,LAPSI_C")

def story_kutsut(k):
    return [p for me, pa, p in k if me == "POST" and pa.endswith("/media") and p.get("media_type") == "STORIES"]
def reel_kutsut(k):
    return [p for me, pa, p in k if me == "POST" and pa.endswith("/media") and p.get("media_type") == "REELS"]
def stories_haut(k):
    return [pa for me, pa, _ in k if me == "GET" and pa.endswith("/stories")]
VIDEO = dict(kuva=None, video="media/v.mp4", tili="monologi")

print("\n— story reelin perään —")
t, k, koodi = aja([rivi(**VIDEO, story=True)])
tarkista("story: true -> reel + story samassa ajossa, sama video",
         t[0]["tila"] == "julkaistu" and len(story_kutsut(k)) == 1 and story_kutsut(k)[0]["video_url"] == "https://rel/x/media/v.mp4" and koodi == 0)
tarkista("storyn kontissa ei kuvatekstia", "caption" not in story_kutsut(k)[0])
jarj = [p.get("media_type") for me, pa, p in k if me == "POST" and pa.endswith("/media")]
tarkista("reel luodaan ennen storya", jarj == ["REELS", "STORIES"])
tarkista("kaksi julkaisua: reel ja story", len(julkaisut(k)) == 2 and julkaisut(k)[1]["creation_id"] == "STORY_CID")
tarkista("story_media_id talteen, reelin media_id ennallaan, apukentat siivottu",
         t[0].get("story_media_id") == "MEDIA_2" and t[0]["media_id"] == "MEDIA_1" and "story_creation_id" not in t[0] and "story_virhe" not in t[0])
tarkista("tuore julkaisu ei kysy tilin storyja (ei vaaraa saman ajon aiemmasta storysta)", not stories_haut(k))

t, k, _ = aja([rivi(**VIDEO, story="media/v_story.mp4")])
tarkista("story-versio omasta tiedostosta Release-osoitteella",
         story_kutsut(k)[0]["video_url"] == "https://rel/x/media/v_story.mp4" and reel_kutsut(k)[0]["video_url"] == "https://rel/x/media/v.mp4")
t, k, _ = aja([rivi(kuva=None, video_url="https://x/v.mp4", story="https://x/s.mp4")])
tarkista("story valmiilla osoitteella", story_kutsut(k)[0]["video_url"] == "https://x/s.mp4")

t, k, _ = aja([rivi(**VIDEO)])
tarkista("ilman story-kenttaa ei storya (regressio)", not story_kutsut(k) and "story_media_id" not in t[0])

print("\n— story: validointi ennen verkkoa —")
for nimi, r in [("story kuvarivilla", rivi(story=True)),
                ("story karusellilla", rivi(kuva=None, kuvat=KUVAT3, story=True)),
                ("story ilman tagia", rivi(**VIDEO, story="v.mp4")),
                ("story vaara tyyppi", rivi(**VIDEO, story=5))]:
    t, k, koodi = aja([r])
    tarkista(f"{nimi} -> virhe, 0 verkkokutsua (reelia ei julkaista)", t[0]["tila"] == "virhe" and len(k) == 0 and "story" in t[0].get("virhe", ""), f"kutsuja {len(k)} virhe={t[0].get('virhe')}")

print("\n— story: virhe ei koske reeliin —")
t, k, koodi = aja([rivi(**VIDEO, story=True)], kaada_rivilla="story")
tarkista("story kaatuu -> reel silti julkaistu", t[0]["tila"] == "julkaistu" and t[0]["media_id"] == "MEDIA_1" and "virhe" not in t[0])
tarkista("… storyn virhe omiin kenttiin", "2207082" in t[0].get("story_virhe", "") and t[0].get("story_yrityksia") == 1 and "story_media_id" not in t[0])
tarkista("… ja exit 1 (meili)", koodi == 1)

print("\n— story: uusinta seuraavassa ajossa —")
t, k, koodi = aja([rivi(**VIDEO, story=True, tila="julkaistu", media_id="MEDIA_R", story_yrityksia=1, story_virhe="x")])
tarkista("julkaistu rivi jolta puuttuu story -> vain story, reelia ei kosketa",
         not reel_kutsut(k) and len(story_kutsut(k)) == 1 and t[0]["tila"] == "julkaistu" and t[0]["media_id"] == "MEDIA_R" and koodi == 0)
tarkista("… tarkistaa tilin storyt ensin", k and k[0][0] == "GET" and k[0][1].endswith("/stories"))
tarkista("… onnistunut uusinta siivoaa virhekentat", t[0].get("story_media_id") == "MEDIA_1" and "story_virhe" not in t[0] and "story_yrityksia" not in t[0])

t, k, _ = aja([rivi(**VIDEO, story=True, tila="julkaistu", story_yrityksia=1)], kaada_rivilla="story_jo")
tarkista("story jo tililla rivin ajan jalkeen -> merkitaan, EI julkaista", not story_kutsut(k) and not julkaisut(k) and t[0].get("story_media_id") == "VANHA_STORY")
t, k, _ = aja([rivi(**VIDEO, story=True, tila="julkaistu", story_yrityksia=1)], kaada_rivilla="story_vanha")
tarkista("edellisen slotin story ei kelpaa tamän rivin storyksi", len(story_kutsut(k)) == 1)
t, k, _ = aja([rivi(**VIDEO, story=True, tila="julkaistu", story_yrityksia=3)])
tarkista("storyn yritykset kaytetty -> 0 kutsua", len(k) == 0)
t, k, _ = aja([rivi(**VIDEO, story=True, tila="julkaistu", story_media_id="S1")])
tarkista("story jo tehty -> 0 kutsua", len(k) == 0)
t, k, _ = aja([rivi(**VIDEO, story=True, tila="julkaistu", story_creation_id="STORY_VANHA")])
tarkista("kesken jaanyt story-kontti -> jatketaan, ei uutta konttia", not story_kutsut(k) and julkaisut(k)[0]["creation_id"] == "STORY_VANHA")
t, k, _ = aja([rivi(**VIDEO, story=True, tila="julkaistu", story_creation_id="CID_KUOLLUT")])
tarkista("kuollut story-kontti -> uusi", len(story_kutsut(k)) == 1 and t[0].get("story_media_id"))

print("\n— story: reel oli jo tililla —")
t, k, _ = aja([rivi(**VIDEO, story=True, caption="jo tililla")])
tarkista("reel jo tililla -> reelia ei julkaista, story tehdään tilin tarkistuksen jälkeen",
         not reel_kutsut(k) and len(story_kutsut(k)) == 1 and stories_haut(k) and t[0].get("story_media_id"))
t, k, _ = aja([rivi(**VIDEO, story=True, caption="jo tililla")], kaada_rivilla="story_jo")
tarkista("reel ja story molemmat jo tililla -> ei yhtaan julkaisua", not julkaisut(k) and t[0].get("story_media_id") == "VANHA_STORY")

print(f"\n{ok} lapi, {fail} hylatty")
sys.exit(1 if fail else 0)
