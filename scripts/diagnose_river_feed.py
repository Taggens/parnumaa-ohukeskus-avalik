#!/usr/bin/env python3
"""Read-only diagnostic of the KAUR XML feed for 3 river stations.
Output is public source metadata, not a verified per-station measurement time.
"""
import json
import datetime as dt
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
URL="https://ilmateenistus.ee/ilma_andmed/xml/observations.php"
TARGET={"Kaansoo":"41174","Audru":"41183","Tahkuse":"41126"}
def main():
    now=dt.datetime.now(dt.timezone.utc)
    out={"checked_at_utc":now.isoformat(),"source":URL,"mode":"read_only","stations":{}}
    try:
        q=urllib.request.Request(URL,headers={"User-Agent":"ParnuIlmakeskus-RiverDiagnostics/1.0","Accept":"application/xml,text/xml,*/*"})
        with urllib.request.urlopen(q,timeout=25) as r:
            raw=r.read(2600000)
            if r.read(1): raise ValueError("XML too long")
        root=ET.fromstring(raw)
        out["xml_root"]=root.tag
        out["feed_timestamp_unix"]=root.get("timestamp")
        try:
            out["feed_timestamp_utc"]=dt.datetime.fromtimestamp(int(root.get("timestamp")),dt.timezone.utc).isoformat()
        except (TypeError,ValueError,OverflowError):out["feed_timestamp_utc"]=None
        all_stations=root.findall("station")
        out["total_xml_stations"]=len(all_stations)
        for name,code in TARGET.items():
            matches=[]
            for st in all_stations:
                current_name=(st.findtext("name") or "").strip()
                current_code=(st.findtext("wmocode") or "").strip()
                if current_name.casefold()==name.casefold() or current_code==code:
                    fields={}
                    for field in ["waterlevel","waterlevel_eh2000","watertemperature","airtemperature","precipitations"]:
                        fields[field]=st.findtext(field)
                    matches.append({"name":current_name,"wmocode":current_code,"fields":fields,
                                    "xml_child_count":len(list(st))})
            out["stations"][name]={"expected_wmocode":code,"matching_xml_records":len(matches),
                "records":matches,"matches_exporter_exact_name_and_code":any(
                    x["wmocode"]==code and x["name"].casefold()==name.casefold() for x in matches)}
    except Exception as e:
        out["error_class"]=type(e).__name__
        out["error_text"]=str(e)[:160]
    dest=Path("research/river_operational_diagnostic_20261124.json")
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()
