"""Compare the deployed Pages JSON with the publisher's committed snapshots."""
import json
import math
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

BASE = 'https://taggens.github.io/parnumaa-ohukeskus-avalik/data/'
FILES = ('state', 'radar', 'marine', 'rivers')


def coverage(hours, published):
    first = math.floor(published / 3600) * 3600 + 3600
    available = {row['t'] for row in hours if isinstance(row, dict) and 't' in row}
    count = 0
    while first + count * 3600 in available:
        count += 1
    return count


def report(files):
    state = files['state']
    published = datetime.fromisoformat(state['published_at_utc'])
    weather = state['weather']
    print('Avaldatud:', published.isoformat(), 'UTC nihe ajatempli lõpus')
    now = datetime.now(timezone.utc)
    def warn_age(label, moment, minutes):
        if moment is None or not -300 <= (now - moment).total_seconds() <= minutes * 60:
            print(f'::warning::{label}: avaldatud failis on aegunud või puuduva ajaga andmed.')
    warn_age('Avaldamine', published, 30)
    for field, limit in [('live', 30), ('sea', 40), ('hourly_rain', 120)]:
        stamp = (weather.get(field) or {}).get('observed_at_utc')
        print(field, stamp)
        warn_age(field, datetime.fromisoformat(stamp) if stamp else None, limit)
    marine = files['marine']
    print('EEPU:', (marine.get('airport') or {}).get('observed_at_utc'))
    print('Rannikujaama XML:', (marine.get('official_observations') or {}).get('feed_timestamp_utc'))
    frame = files['radar'].get('frame')
    print('Radar:', datetime.fromtimestamp(frame, timezone.utc) if frame else 'kaader puudub')
    warn_age('Radar', datetime.fromtimestamp(frame, timezone.utc) if frame else None, 15)
    for place, data in weather['places'].items():
        for model in data.get('models', []):
            count = coverage(model.get('hours') or [], published.timestamp())
            print(place, model['id'], count, 'järjestikust tulevikutundi')


def main():
    pending = set(FILES)
    verified = {}
    for attempt in range(6):
        # A later deployment can overtake this run. Accept a complete file from
        # the current publisher head as well as the originally checked-out file.
        subprocess.run(['git', 'fetch', '-q', 'origin', 'main'], check=True)
        for name in sorted(pending.copy()):
            path = f'docs/data/{name}.json'
            expected = json.loads(Path(path).read_bytes())
            newer = json.loads(subprocess.check_output(['git', 'show', f'FETCH_HEAD:{path}']))
            request = Request(f'{BASE}{name}.json?check={time.time_ns()}', headers={'Cache-Control': 'no-cache'})
            try:
                with urlopen(request, timeout=15) as response:
                    actual = json.load(response)
            except (OSError, ValueError) as error:
                print(name, error)
                continue
            if actual == expected or actual == newer:
                verified[name] = actual
                pending.remove(name)
            else:
                print(name, 'Pagesi sisu erineb avaldamiseks ette valmistatud failist.')
        if not pending:
            report(verified)
            return
        if attempt < 5:
            time.sleep(40)
    raise SystemExit('Pagesi edastuskontroll ebaõnnestus: ' + ', '.join(sorted(pending)))


if __name__ == '__main__':
    main()
