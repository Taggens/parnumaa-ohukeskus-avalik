// Run setup once in the owner's Apps Script editor.
function setup() {
  const props = PropertiesService.getScriptProperties();
  if (!props.getProperty('sheet')) {
    const file = SpreadsheetApp.create('Pärnu Ilmakeskuse tagasiside');
    file.getSheets()[0].appendRow(['Aeg', 'Leht', 'Teema', 'Sõnum']);
    props.setProperty('sheet', file.getId());
  }
  if (!props.getProperty('reader')) props.setProperty('reader', Utilities.getUuid()+Utilities.getUuid());
}
function doPost(e) {
  const props = PropertiesService.getScriptProperties();
  const p = e.parameter;
  const sheet = () => SpreadsheetApp.openById(props.getProperty('sheet')).getSheets()[0];
  if (p.mode === 'read') {
    if (!p.key || p.key !== props.getProperty('reader')) throw new Error('Ligipääs puudub');
    const rows = sheet().getDataRange().getValues().slice(1);
    return ContentService.createTextOutput(JSON.stringify(rows)).setMimeType(ContentService.MimeType.JSON);
  }
  const pages=['Live-ilm','Ilmaprognoos','Sajuradar','Teeolud','Jõeseire','Mereseire','Andmeallikad','Tagasiside'];
  const topics=['Teata veast','Tee ettepanek','Muu'];
  const message=(p['Sõnum'] || '').trim();
  if (!pages.includes(p.Leht) || !topics.includes(p.Teema) || !message || message.length>4000)
    return feedbackPage(false);
  // Prefix formula-like text to store it literally in Sheets.
  sheet().appendRow([new Date(),p.Leht,p.Teema,/^[=+@-]/.test(message)?"'"+message:message]);
  return feedbackPage(true);
}

function feedbackPage(saved) {
  const site = 'https://taggens.github.io/parnumaa-ohukeskus-avalik/';
  const title = saved ? 'Aitäh tagasiside eest!' : 'Kontrolli tagasisidet';
  const detail = saved ? 'Sinu sõnum on salvestatud.' : 'Vali leht ja teema ning kirjuta kuni 4000 tähemärgi pikkune sõnum.';
  const link = saved ? 'Tagasi ilmakeskusesse' : 'Tagasi vormile';
  return HtmlService.createHtmlOutput(`<!doctype html>
<html lang="et"><head><style>
:root{color-scheme:dark;font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;color:#e8f1f7;background:#07111f}
*{box-sizing:border-box}
body{margin:0;padding:clamp(24px,8vh,88px) 16px}
main{max-width:520px;margin:auto;background:#101f30;border:1px solid #20384b;border-radius:15px;padding:clamp(22px,5vw,40px)}
header{display:flex;align-items:center;gap:10px;color:#b1c9cc;font-weight:650}
img{border-radius:10px}
h1{font-size:clamp(1.5rem,5vw,2rem);line-height:1.15;margin:32px 0 10px}
p{color:#b1c3d2;line-height:1.5;margin:0 0 26px}
a{display:inline-flex;align-items:center;min-height:46px;padding:10px 18px;border-radius:8px;background:#83e1ce;color:#103c3a;font-weight:700;text-decoration:none}
a:hover{background:#a0eddf}a:focus-visible{outline:2px solid #83e1ce;outline-offset:4px}
</style></head><body><main><header><img width="36" height="36" alt="" src="${site}icon-192.png">Pärnu Ilmakeskus</header>
<h1>${title}</h1><p>${detail}</p><a target="_top" href="${site}${saved?'#live':'#feedback'}">${link}</a>
</main></body></html>`).setTitle(title+' · Pärnu Ilmakeskus').addMetaTag('viewport','width=device-width, initial-scale=1');
}
