"""Read-only incoming-link inventory for existing high math URLs."""
import json
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
pages=json.loads((ROOT/'intermediate/normalized-pages.json').read_text(encoding='utf-8'))
targets={p['slug'] for p in pages if p['page_type']=='고등수학과외'}
incoming=Counter(); examples={k:[] for k in ['강남구고등수학과외','복대동고등수학과외','울릉군고등수학과외']}
class Links(HTMLParser):
    def __init__(self): super().__init__();self.hrefs=set()
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            href=dict(attrs).get('href','');url=urlsplit(href)
            if (not url.netloc or url.netloc=='goodstudy.co.kr') and url.path.startswith('/'):
                self.hrefs.add(unquote(url.path).strip('/'))
for p in pages:
    parser=Links();parser.feed((ROOT/'output'/p['slug']/'index.html').read_text(encoding='utf-8'))
    for target in (parser.hrefs & targets)-{p['slug']}:
        incoming[target]+=1
        if target in examples and len(examples[target])<5: examples[target].append(p['slug'])
report=dict(targets=len(targets),with_incoming=len(incoming),without_incoming=sorted(targets-set(incoming)),examples=examples,method='Distinct source pages containing an HTML anchor to the existing URL; previews and self-links excluded.')
(ROOT/'audit/high-math-connections.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
