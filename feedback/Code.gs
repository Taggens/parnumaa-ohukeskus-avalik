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
    return HtmlService.createHtmlOutput('Kontrolli lehte, teemat ja sõnumit ning proovi uuesti.');
  // Prefix formula-like text to store it literally in Sheets.
  sheet().appendRow([new Date(),p.Leht,p.Teema,/^[=+@-]/.test(message)?"'"+message:message]);
  return HtmlService.createHtmlOutput('<html lang="et"><meta name="viewport" content="width=device-width, initial-scale=1"><h2>Aitäh tagasiside eest!</h2><p>Sõnum on salvestatud.</p><a target="_top" href="https://taggens.github.io/parnumaa-ohukeskus-avalik/#feedback">Tagasi ilmakeskusesse</a></html>');
}
