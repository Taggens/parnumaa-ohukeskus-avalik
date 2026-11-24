#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only marine source reachability research for Pärnu Ilmakeskus.

Does not download large NetCDF files or modify operational weather data.
Do not interpret HTML page timestamps as verified observations.
"""
import datetime as dt
import json
import re
import html
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UTC=dt.timezone.utc
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"research"/"marine_sources_access_20261124.json"
UA="ParnuIlmakeskusReadOnlyMarineAudit/1.0"
TARGETS={
 "taltech_kihnu":"https://on-line.msi.ttu.ee/kihnu/",
 "taltech_munalaid":"https://on-line.msi.ttu.ee/munalaid/",
 "kaia_nemo_catalog":"https://avaandmed.keskkonnaportaal.ee/dhs/Active/documentList.aspx?ViewId=40a63be9-52d3-4833-b9f6-1d6617a8fff5",
 "kaia_swan_catalog":"https://avaandmed.keskkonnaportaal.ee/dhs/Active/documentList.aspx?ViewId=319c5400-af7c-43cc-ba6e-94428d1dbc2a",
}
API="https://avaandmed.keskkonnaportaal.ee/api/lists/active/items/query"
MAX_BYTES=300000

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None
OPENER=urllib.request.build_opener(NoRedirect)

def fetch(url,post=None):
    headers={"User-Agent":UA,"Accept":"text/html,application/json;q=0.9,*/*;q=0.8"}
    raw=None
    if post is not None:
        raw=json.dumps(post,separators=(",",":")).encode("utf-8")
        headers["Content-Type"]="application/json"
    current=url
    chain=[]
    for _ in range(8):
        try:
            req=urllib.request.Request(current,headers=headers,data=raw,method="POST" if raw is not None else "GET")
            with OPENER.open(req,timeout=22) as r:
                body=r.read(MAX_BYTES+1)
                return {"status":"http_ok" if r.status==200 else "http_other","http_code":r.status,
                        "final_url":r.geturl(),"redirect_chain":chain,
                        "content_type":r.headers.get("Content-Type","")[:80],
                        "body":body[:MAX_BYTES], "truncated":len(body)>MAX_BYTES}
        except urllib.error.HTTPError as e:
            if e.code in (301,302,303,307,308):
                loc=e.headers.get("Location","")
                nxt=urllib.parse.urljoin(current,loc)
                old=urllib.parse.urlsplit(current)
                dest=urllib.parse.urlsplit(nxt)
                chain.append({"code":e.code,"from":old.path or "/","to":dest.path or "/",
                              "cross_origin":old.hostname!=dest.hostname or old.scheme!=dest.scheme})
                if old.hostname!=dest.hostname or dest.scheme not in ("https","http") or nxt in [url]+[current]:
                    return {"status":"redirect_external_or_loop","http_code":e.code,"redirect_chain":chain}
                if any(x["to"]==dest.path for x in chain[:-1]):
                    return {"status":"redirect_loop","http_code":e.code,"redirect_chain":chain}
                current=nxt
                continue
            err=e.read(1500)
            return {"status":"http_error","http_code":e.code,"redirect_chain":chain,
                    "error_prefix":err.decode("utf-8","replace")[:160] if b"<html" not in err[:200].lower() else "HTML response (body omitted)"}
        except (OSError,TimeoutError,urllib.error.URLError) as e:
            return {"status":"connection_error","error_type":type(e).__name__,"redirect_chain":chain}
    return {"status":"too_many_redirects","redirect_chain":chain}

def summarize(name,url):
    r=fetch(url)
    body=r.pop("body",b"")
    r["requested_url"]=url
    if body:
        s=body.decode("utf-8","replace")
        # Distinguish page availability from observation availability.
        r["page_title"]=(re.search(r"<title[^>]*>([^<]{1,120})</title>",s,re.I|re.S).group(1).strip()
                         if re.search(r"<title[^>]*>([^<]{1,120})</title>",s,re.I|re.S) else None)
        r["has_station_or_model_name"]=name.split("_")[-1].lower() in s.lower()
        r["candidate_date_strings"]=list(dict.fromkeys(re.findall(
            r"\b(?:20\d{2}-\d{2}-\d{2}[T ][0-2]\d:[0-5]\d(?::[0-5]\d)?|[0-3]?\d\.[01]?\d\.20\d{2}\s+[0-2]?\d:[0-5]\d)\b",s)))[:12]
        # Public-page text only, never trust this as a verified station observation.
        clean=re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>"," ",s)
        clean=html.unescape(re.sub(r"(?is)<[^>]*>"," ",clean))
        clean=re.sub(r"\s+"," ",clean).strip()
        r["page_text_head"]=clean[:1600]
        r["page_text_length"]=len(clean)
        r["date_context"]=[]
        for t in r["candidate_date_strings"][:4]:
            pos=clean.find(t)
            if pos>=0:
                r["date_context"].append(clean[max(0,pos-180):min(len(clean),pos+330)])
        r["keyword_context"]={}
        for keyword in ["Meretase","Veetase","lainekõrgus","laineperiood","tuul","õhutemperatuur"]:
            m=re.search(keyword,clean,re.I)
            if m:
                r["keyword_context"][keyword]=clean[max(0,m.start()-60):min(len(clean),m.end()+190)]
        r["https_to_http_downgrade"]=url.startswith("https:") and r.get("final_url","").startswith("http:")
        r["timestamp_verified"]=False
    return r

def main():
    report={"schema":"marine-source-access-probe-v1","checked_at_utc":dt.datetime.now(UTC).isoformat(),
            "mode":"read_only","results":{},"netcdf_content_verified":False,"swan_ready":False,"nemo_ready":False,
            "taltech_station_measurement_verified":False}
    for name,url in TARGETS.items():
        report["results"][name]=summarize(name,url)
    # This deliberately does not guess a model-specific KAIA filter.
    probe=fetch(API,post={"filter":{},"includeFileMetadata":False,"pageSize":1})
    body=probe.pop("body",b"")
    if body:
        try:
            parsed=json.loads(body)
            probe["response_shape"]=list(parsed)[:12] if isinstance(parsed,dict) else type(parsed).__name__
        except (ValueError,UnicodeDecodeError):
            probe["response_shape"]="not_json"
    probe["requested_url"]=API
    probe["model_filter_verified"]=False
    report["results"]["kaia_api_unfiltered_metadata_probe"]=probe
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for name,r in report["results"].items():
        print(name, r.get("status"), "HTTP",r.get("http_code","?"),"dates",r.get("candidate_date_strings",[])[:3])
    print("Research report saved; no NetCDF values or fresh station measurements validated.")
if __name__=="__main__":
    main()
