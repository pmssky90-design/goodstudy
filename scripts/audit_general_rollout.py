"""Read-only checks for regional general-tutoring rollout."""
import json
import subprocess
from pathlib import Path
from collections import Counter
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
pages = json.loads((ROOT / 'intermediate/normalized-pages.json').read_text(encoding='utf-8'))
targets = [p for p in pages if p['page_type'] == '과외' and not p.get('school_name') and not any(w in p['breadcrumb_label'] for w in ['수학','영어','초등','중등','고등'])]
allowed = {f"output/{p['slug']}/index.html" for p in targets}
changed = set(filter(None,subprocess.check_output(['git','diff','HEAD','--name-only','-z','--','output'],cwd=ROOT).decode('utf-8').split('\0')))
assert changed <= allowed, changed - allowed
titles = []
for page in targets:
    path = ROOT / 'output' / page['slug'] / 'index.html'
    doc = BeautifulSoup(path.read_text(encoding='utf-8'),'html.parser')
    old = BeautifulSoup((ROOT / 'backup_output_general' / page['slug'] / 'index.html').read_text(encoding='utf-8'),'html.parser')
    assert doc.select_one('meta[name=goodstudy-template]')
    assert len(doc.select('h1')) == 1
    assert len(doc.select('#guide-1, #guide-2')) == 2
    assert not doc.select_one('meta[name=robots][content*=noindex]')
    assert doc.select_one('link[rel=canonical]')['href'] == old.select_one('link[rel=canonical]')['href']
    assert doc.select_one('meta[property="og:image"]')['content'] == old.select_one('meta[property="og:image"]')['content']
    assert doc.select_one('.hero h1').find_next('img')['src'] == '/assets/images/content/body-common.webp'
    ids = [n['id'] for n in doc.select('[id]')]
    assert len(ids) == len(set(ids)),page['slug']
    for a in doc.select('a[href^="#"]'):
        assert a['href'][1:] in ids,(page['slug'],a['href'])
    assert doc.select_one('a[href="tel:01049479030"]')
    assert doc.select_one('a[href="sms:01049479030"]')
    assert 'preview-' not in str(doc)
    titles.append(doc.title.text)
duplicates = {t:n for t,n in Counter(titles).items() if n > 1}
assert not duplicates, duplicates
print(json.dumps({'pages_checked':len(targets),'unique_titles':len(set(titles)),'other_page_changes':0,'passed':True}))
