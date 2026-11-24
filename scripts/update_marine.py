#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ametliku rannikujaamade XML-andmevoo konservatiivne eksport Pärnu Ilmakeskusele.

XML voo ajatempel EI ole iga üksikjaama kinnitatud mõõtmisaeg.
Ei loo merevee ega tormi teavitusi. Ei puuduta olemasolevaid meretaseme hoiatusi.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
import argparse
import json
import math
import os
import xml.etree.ElementTree as ET

UTC = timezone.utc
SOURCE = "https://ilmateenistus.ee/ilma_andmed/xml/observations.php"
STATIONS = {
    "41803": ("Pärnu", "coast"),
    "86031": ("Häädemeeste", "coast"),
    "26128": ("Virtsu", "coast"),
    "26226": ("Kihnu", "weather"),
}
FIELDS = {
    "waterlevel_eh2000": ("sea_level_eh2000_cm", -500, 1000),
    "watertemperature": ("water_temperature_c", -5, 40),
    "airtemperature": ("air_temperature_c", -70, 60),
    "windspeed": ("wind_ms", 0, 70),
    "windspeedmax": ("gust_ms", 0, 90),
    "winddirection": ("wind_direction_deg", 0, 360),
}
def stamp(dt):
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
def now_utc():
    return datetime.now(UTC)
def value(raw, low, high):
    try:
        v = float((raw or "").strip().replace(",", "."))
    except (ValueError, TypeError):
        return None
    return round(v,2) if math.isfinite(v) and low <= v <= high else None
def request():
    req = Request(SOURCE, headers={"User-Agent":"ParnuIlmakeskus-Marine/1.0",
                                     "Accept":"application/xml,text/xml;q=0.9,*/*;q=0.5"})
    with urlopen(req,timeout=25) as resp:
        data = resp.read(2800000)
        if resp.read(1):
            raise ValueError("XML suurem kui 2.8 MB")
    return data
def empty(status):
    return {
        "source_status":status,
        "feed_timestamp_utc":None,
        "station_measurement_time_verified":False,
        "stations":[{"code":c, "name":n, "kind":kind, "station_measurement_time_verified":False,
                     **{k[0]:None for k in FIELDS.values()}}
                    for c,(n,kind) in STATIONS.items()],
    }
def parse_xml(raw, now):
    root = ET.fromstring(raw)
    if root.tag != "observations":
        raise ValueError("Tundmatu XML juurelement")
    feed_raw = root.get("timestamp","")
    if not feed_raw.isdecimal() or len(feed_raw)>12:
        raise ValueError("Vigane XML voo ajatempel")
    feed = datetime.fromtimestamp(int(feed_raw),UTC)
    age=(now-feed).total_seconds()
    fresh= -300 <= age <= 6600
    result = empty("ok" if fresh else "stale")
    result["feed_timestamp_utc"]=stamp(feed)
    matched,duplicates = {},set()
    for station in root.findall("station"):
        code = (station.findtext("wmocode") or "").strip()
        if code not in STATIONS: continue
        if code in matched:
            duplicates.add(code)
            continue
        name = (station.findtext("name") or "").strip()
        if name.casefold() != STATIONS[code][0].casefold():
            continue
        vals={target:value(station.findtext(field),low,high)
              for field,(target,low,high) in FIELDS.items()}
        if STATIONS[code][1]=="weather":
            vals["sea_level_eh2000_cm"]=None
        matched[code]=vals
    for row in result["stations"]:
        code=row["code"]
        if fresh and code in matched and code not in duplicates:
            row.update(matched[code])
    result["source_url"]=SOURCE
    result["note"]="XML avaldamisaeg ei kinnita üksikjaama mõõtmisaega. Meretase on EH2000 sentimeetrites."
    return result
def build(now,reader=request):
    try:
        source=parse_xml(reader(),now)
    except (OSError,ValueError,ET.ParseError,OverflowError):
        source=empty("error")
    return {
        "schema":"marine-monitor-v1",
        "generated_at_utc":stamp(now),
        "official_observations":source,
        "forecast_status":{"nemo":"unverified","swan":"unverified"},
        "automatic_alerts":False,
    }
def save(path,data):
    path=Path(path)
    if path.is_symlink():raise ValueError("Keeldutud sümbollingist")
    raw=json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2)+"\n"
    if len(raw.encode("utf-8"))>50000:raise ValueError("Ebatavaliselt suur JSON")
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+".tmp")
    if tmp.is_symlink():raise ValueError("Ajutine fail on sümbollink")
    try:
        tmp.write_text(raw,encoding="utf-8")
        os.replace(tmp,path)
    finally:
        if tmp.exists():tmp.unlink()
def selftest():
    n=datetime(2026,11,24,19,tzinfo=UTC)
    row=lambda code,name,sea,wind:"<station><wmocode>"+code+"</wmocode><name>"+name+"</name><waterlevel_eh2000>"+sea+"</waterlevel_eh2000><windspeed>"+wind+"</windspeed><windspeedmax>8</windspeedmax><airtemperature>2</airtemperature></station>"
    wrap=lambda cells,t=n:'<observations timestamp="'+str(int(t.timestamp()))+'">'+cells+'</observations>'
    a=parse_xml(wrap(row("86031","Häädemeeste","52","3")+row("26128","Virtsu","46","4")).encode(),n)
    assert a["source_status"]=="ok"
    assert a["station_measurement_time_verified"] is False
    assert next(s for s in a["stations"] if s["code"]=="86031")["sea_level_eh2000_cm"]==52
    assert next(s for s in a["stations"] if s["code"]=="26128")["wind_ms"]==4
    assert next(s for s in a["stations"] if s["code"]=="41803")["sea_level_eh2000_cm"] is None
    assert parse_xml(wrap(row("86031","Häädemeeste","10","3"),n-timedelta(hours=3)).encode(),n)["source_status"]=="stale"
    assert all(s["sea_level_eh2000_cm"] is None for s in parse_xml(wrap(row("86031","Häädemeeste","10","3"),n-timedelta(hours=3)).encode(),n)["stations"])
    assert parse_xml(wrap(row("86031","Häädemeeste","10","3"),n+timedelta(hours=1)).encode(),n)["source_status"]=="stale"
    assert next(s for s in parse_xml(wrap(row("86031","Virtsu","42","3")).encode(),n)["stations"] if s["code"]=="86031")["sea_level_eh2000_cm"] is None
    duplicate=wrap(row("86031","Häädemeeste","20","3")+row("86031","Häädemeeste","25","3")).encode()
    assert next(s for s in parse_xml(duplicate,n)["stations"] if s["code"]=="86031")["sea_level_eh2000_cm"] is None
    assert value("",-500,1000) is None and value("NaN",-500,1000) is None
    assert value("20000",-500,1000) is None
    assert value("-12.5",-500,1000)==-12.5
    assert next(s for s in parse_xml(wrap(row("26226","Kihnu","25","3")).encode(),n)["stations"] if s["code"]=="26226")["sea_level_eh2000_cm"] is None
    assert build(n,reader=lambda: b"<invalid/>")["official_observations"]["source_status"]=="error"
    assert build(n,reader=lambda: wrap(row("26128","Virtsu","46","4")).encode())["automatic_alerts"] is False
    assert all(s["station_measurement_time_verified"] is False for s in a["stations"])
    print("OK: 15 rannikujaama XML-kontrolli (aeg, jaama identiteet, duplikaat, ühik, null, väärnäit, Kihnu, veaolek, teavitused)")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",default="docs/data/marine.json")
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest: selftest();return
    d=build(now_utc())
    save(args.output,d)
    print("Mereseire XML:",d["official_observations"]["source_status"],
          "jaamu",len(d["official_observations"]["stations"]),
          "andmefail",d["generated_at_utc"])
if __name__=="__main__":
    main()
