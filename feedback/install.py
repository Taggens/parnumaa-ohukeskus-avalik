"""Add the feedback inbox to an existing Windows admin installation."""
from pathlib import Path
import getpass
import json
import re
import shutil
import sys

ROUTE = """        if url == '/api/feedback':
            if not self.authenticated() or self.session_identity()[0] != 'admin':
                return self._send({'error':'Ligipääs puudub'},403)
            from feedback_reader import read_feedback
            try:
                return self._send(read_feedback())
            except Exception:
                return self._send({'error':'Tagasiside vastuvõtja pole kättesaadav'},503)
"""
def install(root, endpoint, key):
    if not re.fullmatch(r'https://script\.google\.com/macros/s/[\w-]+/exec', endpoint) or len(key)<32:
        raise ValueError('Kontrolli veebirakenduse aadressi ja lugemisvõtit.')
    here = Path(__file__).resolve().parent
    server, app = root/'server.py', root/'app.js'
    changes = {}
    for file, anchor, insert in [(server,"        if url == '/api/history':",ROUTE),
            (app,"  userAccount = session.account || 'admin';","\n  if(userRole==='admin' && !document.getElementById('feedback'))installFeedbackMenu();")]:
        src=file.read_text(encoding='utf-8-sig')
        if insert in src: continue
        if src.count(anchor)!=1: raise ValueError(f'{file.name} versioon vajab kontrolli.')
        dst=src.replace(anchor,insert+anchor) if file==server else src.replace(anchor,anchor+insert)+'\n'+(here/'admin.js').read_text(encoding='utf-8')
        if file==server: compile(dst,str(server),'exec')
        changes[file]=dst
    shutil.copyfile(here/'feedback_reader.py',root/'feedback_reader.py')
    (root/'feedback_private.json').write_text(json.dumps(dict(endpoint=endpoint,key=key)),encoding='utf-8')
    for path,src in changes.items():
        backup=path.with_suffix(path.suffix+'.before-feedback')
        if not backup.exists(): shutil.copy2(path,backup)
        tmp=path.with_suffix(path.suffix+'.feedback.tmp')
        tmp.write_text(src,encoding='utf-8')
        tmp.replace(path)

if __name__=='__main__':
    root=Path(input('Adminiserveri kaust (server.py asukoht): ').strip().strip('"'))
    install(root,input('Avalik /exec aadress: ').strip(),getpass.getpass('Privaatne reader-võti: ').strip())
    print('Tagasiside menüü paigaldatud. Taaskäivita adminiserver ja värskenda brauserit.')
