"""Initialize ignored local data from the synthetic, credential-free demo."""
from pathlib import Path
import json
import refresh

if __name__ == '__main__':
    target = refresh.DATA / 'latest.json'
    if target.exists():
        raise SystemExit('Local data already exists; demo initialization stopped.')
    demo = json.loads((refresh.DATA / 'demo.json').read_text(encoding='utf-8'))
    refresh.write_digest(demo)
    print('Demo ready. Open index.html or the generated standalone HTML.')
