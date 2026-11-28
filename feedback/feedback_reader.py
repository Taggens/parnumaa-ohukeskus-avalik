import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

def read_feedback():
    config=json.loads(Path(__file__).with_name('feedback_private.json').read_text(encoding='utf-8'))
    data=urlencode({'mode':'read','key':config['key']}).encode()
    with urlopen(config['endpoint'],data=data,timeout=20) as response:
        rows=json.load(response)
    if not isinstance(rows,list) or any(not isinstance(r,list) or len(r)!=4 for r in rows):
        raise ValueError('Vigane tagasiside vastus')
    return rows
