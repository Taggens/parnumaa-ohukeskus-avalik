#!/usr/bin/env python3
"""Statistical public frontend checks for the Pärnu Ilmakeskus marine monitoring view."""
from html.parser import HTMLParser
from pathlib import Path
from subprocess import run
from tempfile import TemporaryDirectory
from collections import Counter
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "docs" / "index.html"
class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=[]
        self.buttons=[]
        self.screens=[]
    def handle_starttag(self,tag,attrs):
        data=dict(attrs)
        if "id" in data:self.ids.append(data["id"])
        if data.get("data-section"):self.buttons.append(data["data-section"])
        if tag=="section" and "screen" in data.get("class","").split():
            self.screens.append(data.get("id"))
def main():
    html=HTML.read_text(encoding="utf-8")
    p=Markup()
    p.feed(html)
    duplicates=[key for key,n in Counter(p.ids).items() if n!=1]
    assert not duplicates, "duplicate IDs: "+str(duplicates)
    expected={"live","forecast","roads","rivers","marine","sources","radar","feedback"}
    assert set(p.buttons)==expected and set(p.screens)==expected
    assert len(p.buttons)==len(expected) and len(p.screens)==len(expected)
    for id in ["marine-heading","marine-status","marine-feed-time","marine-levels","marine-weather"]:
        assert id in p.ids, "marine DOM ID missing: "+id
    for text in ["function renderMarine()","function marineEligible()",
                 "function loadMarine()","renderMarine();",
                 "loadMarine();","fresh(m.generated_at_utc,90)",
                 "sourceVerified&&cm>=100",
                 "Jaama mõõtmise täpne aeg: kinnitamata",
                 "marine:'Mereseire'",
                 "on-line.msi.ttu.ee/munalaid",
                 "on-line.msi.ttu.ee/kihnu"]:
        assert text in html, "marine safety/UI logic missing: "+text
    scripts=re.findall(r"<script(?:\s[^>]*)?>([\s\S]*?)</script>",html)
    scripts=[body for body in scripts if body.strip()]
    assert len(scripts)==1, "Expected one inline script"
    with TemporaryDirectory() as tmp:
        js=Path(tmp)/"site.js"
        js.write_text(scripts[0],encoding="utf-8")
        result=run(["node","--check",str(js)],text=True,capture_output=True)
        assert result.returncode==0, result.stdout+result.stderr
    print("OK: 14 marine UI assertions + JS syntax + unique DOM IDs + eight menus")
if __name__=="__main__":
    main()
