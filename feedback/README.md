# Kontota tagasiside

1. Ava [Google Apps Script](https://script.google.com/home/projects/create) kontoga, millele tagasiside peab kuuluma. Kopeeri faili **Code.gs** sisu redaktorisse ja salvesta. Käivita funktsioon **setup** ja kinnita ligipääs. See loob sinu Google Drive’i privaatse tabeli.
2. Vali **Deploy → New deployment → Web app**. Vali käivitajaks **Me** ning ligipääsuks **Anyone** (ka sisselogimata külalised). Kopeeri avalik veebiaadress, mille lõpus on **/exec**.
3. Avaliku vormi ühendamiseks lisa faili **docs/feedback-config.json** sisu kujul `{"endpoint":"SINU_EXEC_AADRESS"}`. Avaliku lehe ja seadistuse võib nüüd koos avaldada. Ainult /exec aadressi võid saata ka vestluses.
4. Adminimenüü jaoks laadi arvutisse kaust **feedback**. Ava seal terminal ja käivita `py install.py`. Sisesta töötava adminiserveri kaust ja sama /exec aadress. Kolmas sisend on privaatne lugemisvõti, mille leiad Apps Scriptis **Project Settings → Script properties → reader**. Sisesta võti ainult oma arvutis. Seejärel taaskäivita adminiserver ja värskenda lehte.
5. Ava avalik vorm privaatses brauseriaknas, saada üks proovisõnum ja kontrolli adminimenüüs selle lehe- ja teemafiltrit. Tabeli jagamisõigused võivad jääda **Restricted**.
