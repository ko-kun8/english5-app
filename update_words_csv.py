import csv
from pathlib import Path

path = Path('words.csv')
with path.open(encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    rows = []
    if not reader.fieldnames:
        raise SystemExit('No csv header found')

    fieldnames = [name.strip().lstrip('\ufeff').lower() for name in reader.fieldnames]
    if 'type' in fieldnames:
        type_idx = fieldnames.index('type')
        english_idx = fieldnames.index('english')
        japanese_idx = fieldnames.index('japanese')
        for row in reader:
            english = (row.get(reader.fieldnames[english_idx], '') or '').strip()
            japanese = (row.get(reader.fieldnames[japanese_idx], '') or '').strip()
            item_type = (row.get(reader.fieldnames[type_idx], '') or '').strip().lower()
            if item_type not in {'word', 'phrase', 'grammar'}:
                item_type = 'word'
            if english and japanese:
                rows.append((item_type, english, japanese))
    else:
        english_idx = fieldnames.index('english')
        japanese_idx = fieldnames.index('japanese')
        for row in reader:
            english = (row.get(reader.fieldnames[english_idx], '') or '').strip()
            japanese = (row.get(reader.fieldnames[japanese_idx], '') or '').strip()
            if english and japanese:
                rows.append(('word', english, japanese))

rows.extend([
    ('phrase', 'look for', '〜を探す'),
    ('phrase', 'be good at', '〜が得意だ'),
    ('grammar', 'be going to', '〜するつもりだ'),
    ('grammar', 'have to', '〜しなければならない'),
])

with path.open('w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['type', 'english', 'japanese'])
    writer.writerows(rows)

print(f'Wrote {len(rows)} rows to {path}')
