#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pärnu Ilmakeskuse jõeseire. Värske XML-voog + eraldi ajaloolised tunnikeskmised.

Kumbki allikas ei ole iseseisev üleujutushoiatus. Jaamapõhine XML mõõtmisaeg kinnitamata.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import argparse
import json
import math
import os
import xml.etree.ElementTree as ET

UTC = timezone.utc
XML_URL = "https://ilmateenistus.ee/ilma_andmed/xml/observations.php"
HIST_URL = "https://keskkonnaandmed.envir.ee/f_hydroseire"
STATIONS = {
    "41137": ("Aesoo", "Navesti"),
    "41183": ("Audru", "Audru jõgi"),
    "41174": ("Kaansoo", "Saarjõgi"),
    "41197": ("Laadi", "Reiu"),
    "41198": ("Nurme", "Sauga"),
    "41127": ("Oore", "Pärnu jõgi"),
    "41140": ("Riisa", "Halliste"),
    "41126": ("Tahkuse", "Pärnu jõgi"),
}
HEADERS = {"User-Agent": "ParnuIlmakeskus-Hydrology/1.0", "Accept": "application/json, application/xml;q=0.9"}
def now_utc():
    return datetime.now(UTC)
def stamp(t):
    return t.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
def parse_time(t):
    if not isinstance(t, str) or len(t) > 64:
        return None
    try:
        x = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return x.replace(tzinfo=UTC) if x.tzinfo is None else x.astimezone(UTC)
    except ValueError:
        return None
def request(url, max_bytes=500000):
    with urlopen(Request(url, headers=HEADERS), timeout=25) as r:
        raw = r.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("allikas ületas mahupiiri")
    return raw
def river_number(raw):
    if raw is None or not str(raw).strip():
        return None
    try:
        v = float(str(raw).strip().replace(",", "."))
    except ValueError:
        return None
    return round(v, 2) if math.isfinite(v) and -5000 <= v <= 30000 else None
def parse_xml(raw, now):
    root = ET.fromstring(raw)
    if root.tag != "observations":
        raise ValueError("XML juur ei sobi")
    root_raw = root.attrib.get("timestamp", "")
    if not root_raw.isdecimal():
        raise ValueError("XML aja kuju on vigane")
    feed_t = datetime.fromtimestamp(int(root_raw), UTC)
    age = (now - feed_t).total_seconds()
    fresh = -300 <= age <= 7200
    found, duplicates = {}, set()
    for entry in root.findall("station"):
        code = (entry.findtext("wmocode") or "").strip()
        if code not in STATIONS:
            continue
        if code in found:
            duplicates.add(code)
            continue
        name = (entry.findtext("name") or "").strip()
        if name.casefold() != STATIONS[code][0].casefold():
            continue
        found[code] = river_number(entry.findtext("waterlevel"))
    return {
        "source": XML_URL, "source_status": "ok" if fresh else "stale",
        "feed_timestamp_utc": stamp(feed_t),
        "station_measurement_time_verified": False,
        "datum_note": "Sisevete waterlevel: cm Amsterdami nulli suhtes, üksikjaama mõõtmishetk kinnitamata",
        "stations": [
            {"code":code, "name":name, "cm":found.get(code) if fresh and code not in duplicates else None,
             "station_time_verified":False}
            for code,(name,_) in STATIONS.items()
        ],
    }
def empty_observation(status):
    return {"source": XML_URL, "source_status": status,
            "feed_timestamp_utc": None, "station_measurement_time_verified":False,
            "datum_note": "Jaama mõõtmisaeg kinnitamata",
            "stations":[{"code":c,"name":n,"cm":None,"station_time_verified":False} for c,(n,_) in STATIONS.items()]}
def history_url(code, now):
    opts=[("jaam_kood","eq."+code),("aegrida_nimi","eq.WL avg"),
          ("timeline_ts_utc","gte."+stamp(now-timedelta(days=8))),
          ("order","timeline_ts_utc.desc"),("limit","72"),
          ("select","jaam_kood,jaam_nimi,veekogu_nimi,aegrida_nimi,timeline_ts_utc,vaartus")]
    return HIST_URL+"?"+urlencode(opts, safe=",:.")
def parse_history(code, raw, now):
    data=json.loads(raw)
    if not isinstance(data,list) or len(data)>72:
        raise ValueError("ajaloo vastus ei sobi")
    points={}
    for row in data:
        if not isinstance(row,dict) or str(row.get("jaam_kood"))!=code or row.get("aegrida_nimi")!="WL avg":
            continue
        if (row.get("jaam_nimi") or "").casefold()!=STATIONS[code][0].casefold():
            continue
        t=parse_time(row.get("timeline_ts_utc"))
        v=river_number(row.get("vaartus"))
        if t is None or v is None or not now-timedelta(days=8)<=t<=now+timedelta(minutes=5):
            continue
        points[stamp(t)]=v
    hours=[{"t":k,"cm":v} for k,v in sorted(points.items())[-72:]]
    latest=parse_time(hours[-1]["t"]) if hours else None
    return {"code":code,"name":STATIONS[code][0],"waterbody":STATIONS[code][1],
            "hours":hours,"status":"ok" if len(hours)>=24 and latest and now-latest<=timedelta(hours=96) else "incomplete"}
def fetch_history_station(code, now):
    return parse_history(code,request(history_url(code,now)),now)
def history_result(now, old_history):
    recent=old_history if isinstance(old_history,dict) and isinstance(old_history.get("stations"),list) else None
    last=parse_time(recent.get("generated_at_utc")) if recent else None
    if last and timedelta(0)<=now-last<timedelta(hours=12):
        return recent
    result={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(fetch_history_station,code,now):code for code in STATIONS}
        for fut in as_completed(jobs):
            code=jobs[fut]
            try:
                result[code]=fut.result()
            except Exception:
                result[code]={"code":code,"name":STATIONS[code][0],
                              "waterbody":STATIONS[code][1],"hours":[],"status":"error"}
    good=sum(s["status"]=="ok" for s in result.values())
    if good<6:
        if recent:
            return recent
        raise ValueError("vähem kui 6/8 ajaloojaama; ei avaldata eksitavat uut ajalugu")
    return {"source":HIST_URL,"generated_at_utc":stamp(now),
            "unit":"cm","datum":"jaama graafiku null","is_live":False,
            "stations":[result[c] for c in STATIONS]}
def collect(now, previous=None, xml_fetch=None, history_fetch=None):
    previous=previous if isinstance(previous,dict) and previous.get("schema")=="river-monitor-v1" else {}
    try:
        observations=parse_xml((xml_fetch or (lambda:request(XML_URL,2500000)))(),now)
    except Exception:
        observations=empty_observation("error")
    history=history_fetch(now,previous.get("history")) if history_fetch else history_result(now,previous.get("history"))
    return {"schema":"river-monitor-v1", "generated_at_utc":stamp(now),
            "observations":observations,"history":history}
def save(path, data):
    path=Path(path)
    if path.is_symlink():
        raise ValueError("sümbollink ei ole lubatud")
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(data,ensure_ascii=False,indent=1,allow_nan=False)+"\n"
    if len(raw.encode("utf-8"))>400000:
        raise ValueError("andmefail liiga suur")
    temp=path.with_name(path.name+".tmp")
    try:
        temp.write_text(raw,encoding="utf-8")
        os.replace(temp,path)
    finally:
        if temp.exists():
            temp.unlink()
def selftest():
    now=datetime(2026,11,24,17,0,tzinfo=UTC)
    sample=('<observations timestamp="'+str(int(now.timestamp()))+'">'
            '<station><wmocode>41140</wmocode><name>Riisa</name><waterlevel>152</waterlevel></station>'
            '<station><wmocode>41137</wmocode><name>Aesoo</name><waterlevel></waterlevel></station>'
            '</observations>').encode()
    a=parse_xml(sample,now)
    assert a["source_status"]=="ok"
    assert next(x["cm"] for x in a["stations"] if x["code"]=="41140")==152
    assert next(x["cm"] for x in a["stations"] if x["code"]=="41137") is None
    assert parse_xml(sample,now+timedelta(hours=3))["source_status"]=="stale"
    dupe=sample.replace(b"</observations>",b'<station><wmocode>41140</wmocode><name>Riisa</name><waterlevel>999</waterlevel></station></observations>')
    assert next(x["cm"] for x in parse_xml(dupe,now)["stations"] if x["code"]=="41140") is None
    rows=[{"jaam_kood":41140,"jaam_nimi":"Riisa","aegrida_nimi":"WL avg",
           "timeline_ts_utc":stamp(now-timedelta(hours=i)),"vaartus":150+i} for i in range(72)]
    assert len(parse_history("41140",json.dumps(rows).encode(),now)["hours"])==72
    assert collect(now,xml_fetch=lambda:sample,history_fetch=lambda a,b:{"stations":[]})["schema"]=="river-monitor-v1"
    print("OK: ajakontroll, jaamakoodid, duplikaadid, nullväärtused, 72h ajalugu, ühine väljastus")
def main():
    p=argparse.ArgumentParser();p.add_argument("--output",default="docs/data/rivers.json")
    p.add_argument("--selftest",action="store_true");args=p.parse_args()
    if args.selftest:
        selftest();return
    path=Path(args.output)
    try:
        previous=json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError,ValueError):
        previous=None
    data=collect(now_utc(),previous)
    save(path,data)
    print("Jõeseire uuendatud: XML "+data["observations"]["source_status"]+
          "; ajaloojaamu "+str(len(data["history"]["stations"])))
if __name__=="__main__":
    main()
