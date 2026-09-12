"""Read-only deployed content smoke checks."""
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
SLUGS=['강남구초등영어과외','복대동초등영어과외','울릉군초등영어과외','가경동초등영어과외','복대동과외','복대동영어과외','복대동수학과외','복대동초등수학과외','복대동중등영어과외']

def check(slug):
    with urlopen('https://goodstudy.co.kr/'+quote(slug)+'/',timeout=60) as response:
        assert response.status==200
        remote=BeautifulSoup(response.read(),'html.parser')
    local=BeautifulSoup((ROOT/'output'/slug/'index.html').read_text(encoding='utf-8'),'html.parser')
    assert remote.get_text(' ',strip=True)==local.get_text(' ',strip=True),slug
    assert remote.select_one('link[rel=canonical]')['href']==local.select_one('link[rel=canonical]')['href']
    assert not remote.select_one('meta[name=robots][content*=noindex]')
    return slug+' OK'

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(check,SLUGS): print(result)
