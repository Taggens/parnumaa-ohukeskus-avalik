# Pärnumaa Ohukeskus · avalik prooviversioon

Avalik ainult lugemiseks mõeldud veebileht. Kolm jaotist: **Ilmaülevaade**, **Ilmaprognoos** ja **Teeolud**.

## Veebilehe avaldamine

GitHubis vali **Settings → Pages → Build and deployment → Deploy from a branch → main → /docs → Save**.

Veebiaadress: https://taggens.github.io/parnumaa-ohukeskus-avalik/

## Andmete värskus

Failis `docs/data/state.json` on esialgu ainult tühi näidisolek. **Päris mõõtmisi ei ole seni avaldatud.** Veebileht peab kuvama puuduvate või aegunud näitude asemel kriipse.

Avalike andmete eksportimiseks on eraldi Windowsi paigalduspakk `PARNUMAA_OHUKESKUS_AVALIK_PROOVIVERSIOON_V1_20261122.zip`. Selle andmesild vajab kohalikku kontrolli enne automaatse üleslaadimise kasutuselevõttu.

Avalikku hoidlasse **ei tohi** laadida privaatset `server.py`, SQLite'i, sisselogimisi, API-võtmeid, salajasi tokeneid, konfiguratsiooni ega kogu Windowsi Ohukeskuse kausta. Lubatud on ainult avaliku veebilehe failid ja puhastatud JSON-eksport.

## Piirangud

- Teeilmajaamade andmed on üksikute jaamade mõõtmised, mitte tee sõiduohutuse hinnang.
- Ametlikke hoiatusi vaata Ilmateenistusest, teeinfot Tark Teest.
- Kui Windowsi server ei tööta või eksport ei uuene, muutuvad avalikud näidud aegunuks.
- Avalik leht ei anna ligipääsu administraatori osale ega sisalda teavitusi.

Kohalikud veebi- ja andmeekspordi testid ei asenda päris Windowsi andmevoo ning GitHub Pagesi HTTPS-testimist.
