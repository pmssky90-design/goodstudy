"""Elementary English previews and validated regional rollout."""
import json
import re
import argparse
import shutil
import subprocess
from copy import deepcopy
from collections import Counter
from pathlib import Path
from html import escape as e
from itertools import combinations
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'
PAGES=json.loads((ROOT/'intermediate/normalized-pages.json').read_text(encoding='utf-8'))
SAMPLES=[
dict(region='강남구',key='gangnam',topic='소리부터 읽기까지',headline='알파벳 다음에 만나는, 의미 있는 영어.',
lead='강남구 초등영어과외는 파닉스와 어휘만 따로 쌓기보다 듣기·말하기·읽기·쓰기가 이어지는지 살펴보는 데서 시작합니다. 글자 이름을 알고 있는 것과 단어를 읽는 것은 다를 수 있어, 현재 사용하는 교재에서 소리와 철자의 연결을 먼저 확인합니다.',
feature='파닉스 교재를 끝냈다면, 무엇을 읽어볼까요?',intro='책 한 권을 끝낸 사실만으로 다음 수준을 결정하지 않습니다. 배운 소리 규칙이 포함된 짧은 단어를 처음 보았을 때 읽을 수 있는지, 읽은 뒤 뜻을 떠올리는지를 나누어 살펴봅니다.',
quote='cat · map · bag',caption='짧은 a 소리가 들어가는 단어 예시',explain='c, a, t의 글자 이름을 차례로 말하는 것과 cat을 한 단어로 읽는 것은 다릅니다. 이미 배운 글자 소리를 연결해 읽고, 고양이를 뜻한다는 것까지 확인합니다. 모든 영어 단어가 같은 규칙으로 읽히는 것은 아니므로 예외 표현은 별도로 익힙니다.',
choices=[('소리 규칙을 다시 볼 자료','이미 배운 철자와 소리가 들어간 단어를 중심으로 고릅니다. 아직 배우지 않은 규칙이 한꺼번에 많이 등장하는 책은 잠시 미룹니다.'),('뜻과 연결할 자료','그림과 짧은 문장이 함께 있는 자료를 선택합니다. 그림만 보고 맞힌 것인지 실제 글자를 읽은 것인지도 구분합니다.'),('듣기를 곁들일 자료','출판사 등 제공처가 분명한 음원을 활용합니다. 이 페이지에는 재생 음원이 없으며, 실제 듣기에는 교재 음원이 필요합니다.')],
bridge='파닉스 연습에서 읽은 단어를 학교 교과서에서 다시 찾아보세요. 익숙한 단어라도 문장 안에서 놓친다면 단어장 분량을 늘리기보다 짧은 문장을 읽는 시간을 확보합니다.',
balance='소리 내어 읽기는 읽기 연습이지, 그 자체로 말하기 전부는 아닙니다. 읽은 단어를 실제 물건이나 그림과 연결하고, 익숙한 표현으로 선택을 말할 기회도 따로 둡니다.',order=['feature','selection','bridge']),
dict(region='복대동',key='bokdae',topic='읽기와 표현의 균형',headline='많이 읽기 전에, 이해할 수 있는 한 권부터.',
lead='복대동 초등영어과외에서는 읽기 책의 권수보다 아이가 이해하고 사용할 수 있는 표현을 먼저 살펴봅니다. 파닉스·어휘의 빈틈을 확인하면서 듣기와 말하기, 짧은 문장 쓰기를 함께 연결하고, 교재 난도는 학년 이름만으로 결정하지 않습니다.',
feature='줄줄 읽어도, 이야기가 남지 않는다면',intro='모든 단어를 번역시키기 전에 누가 무엇을 하는 이야기인지 확인해 보세요. 소리 내어 읽는 속도와 내용을 이해하는 정도는 서로 다를 수 있습니다.',
quote='Mina has a red bag.\nHer book is in the bag.',caption='읽기 수준을 설명하기 위해 만든 두 문장',explain='가방 색은 빨간색이고, 책은 가방 안에 있습니다. red의 뜻만 아는지, 두 번째 문장에서 책의 위치까지 이해하는지 구분합니다. 줄거리를 한국어로 간단히 말하는 것도 이해를 확인하는 방법이며 처음부터 긴 영어 답변을 요구할 필요는 없습니다.',
choices=[('혼자 읽을 책','대부분의 표현이 익숙하고 도움 없이도 대략의 상황을 알 수 있는 자료를 고릅니다. 모르는 단어 수 하나만으로 난도를 결정하지 않습니다.'),('함께 읽을 책','새 표현이 조금 있어도 그림과 문맥으로 내용을 이어갈 수 있는 책을 선택합니다. 매 문장마다 설명이 길어지면 더 짧은 자료로 조정합니다.'),('나중에 읽을 책','문장 대부분이 낯설거나 내용을 따라가기 어려우면 잠시 보류합니다. 어려운 책을 끝내는 것이 초등 영어의 유일한 목표는 아닙니다.')],
bridge='교과서에서 배운 위치 표현을 읽기 책에서 만나면 두 자료를 연결할 수 있습니다. 다만 학교 과제 완성과 자유 읽기를 같은 일로 취급하지 말고, 해야 할 과제와 즐겁게 읽을 분량을 나누어 정합니다.',
balance='읽기 이해가 된 뒤에는 자신이 가진 물건에 맞춰 짧게 말하거나 써봅니다. 원문을 그대로 외우는 것과 내용을 바꾸어 사용하는 것을 구분하고, 쓰기 부담이 크면 말하기부터 시작할 수 있습니다.',order=['selection','feature','bridge']),
dict(region='울릉군',key='ulleung',topic='듣기와 말하기의 연결',headline='외운 문장이, 내 뜻을 전하는 표현이 되도록.',
lead='울릉군 초등영어과외는 듣고 아는 표현을 상황에 맞게 말하고, 읽고 쓸 수 있는 범위로 넓혀가는 과정을 다룹니다. 파닉스와 어휘 기초도 함께 살피되, 따라 말한 횟수만으로 표현을 익혔다고 판단하지 않습니다.',
feature='따라 말하기와 직접 고르기는 다릅니다',intro='모범 문장을 듣고 반복하는 연습 뒤에는 자신의 선택을 말할 자리가 필요합니다. 실제 생각과 맞는 말을 골랐는지 살펴보면 외운 표현을 활용하는 범위를 알 수 있습니다.',
quote='I like apples.\nI like bananas.',caption='좋아하는 것을 말하는 표현 예시',explain='두 문장 중 자신의 취향에 맞는 말을 고르거나 이미 아는 다른 과일 이름으로 바꾸어 봅니다. 좋아하지 않는 것을 좋아한다고 따라 말하게 하는 것이 목표는 아닙니다. 복수형 표현은 예문 속에서 함께 익히고, 아직 모르는 문법 용어를 길게 설명하지 않아도 됩니다.',
choices=[('들을 자료','배우는 표현과 대본이 함께 제공되는 짧은 음원을 고릅니다. 배경음처럼 오래 틀어두기보다 어느 상황의 말인지 알 수 있는 자료를 사용합니다.'),('말할 상황','좋아하는 음식, 가진 물건처럼 아이가 선택할 수 있는 상황을 정합니다. 다른 사람 앞에서 발표하는 것이 부담스럽다면 익숙한 상대와 짧게 시작합니다.'),('읽고 쓸 자료','말로 익힌 표현을 글자로도 만나게 합니다. 말하기가 가능해도 철자를 바로 쓸 수 있는 것은 아니므로 보고 쓰기와 혼자 쓰기를 구분합니다.')],
bridge='학교에서 배우는 인사나 소개 표현은 실제로 사용할 상황과 함께 복습합니다. 평가가 있다면 학교가 안내한 과제와 기준부터 확인하고, 임의로 어려운 발표문을 만들기보다 배운 표현을 정확히 이해하는 데 집중합니다.',
balance='듣기 음원이 없을 때 글만 읽고 듣기를 평가했다고 보기는 어렵습니다. 교재 음원으로 이해를 확인하는 시간과 자신의 뜻을 말하는 시간을 구분해 계획합니다. 아래는 지도 방법 예시이며 지역의 실제 수업 운영 사례는 아닙니다.',order=['bridge','feature','selection']),
]

CSS='''*{box-sizing:border-box}html{scroll-padding-top:25px}body{margin:0;background:#fffdf8;color:#253b3b;font:16px/1.9 "Malgun Gothic",sans-serif}a{color:inherit}header{border-bottom:1px solid #bfcfca;padding:18px max(22px,calc((100vw - 1080px)/2));display:flex;justify-content:space-between}header a{text-decoration:none}.brand{font-size:24px;font-weight:bold}main{max-width:1080px;margin:auto;padding:25px 28px}.review{font-size:13px;display:flex;gap:18px;flex-wrap:wrap}.eyebrow{font-size:12px;letter-spacing:2px;color:#446d67;text-transform:uppercase}h1{font-size:48px;line-height:1.35;margin:35px 0 12px;letter-spacing:-2px}.subtitle{font-size:24px}.image{max-width:800px;margin:30px auto}.image img{width:100%;height:auto;display:block}h2{font-size:30px;line-height:1.5;letter-spacing:-1px}h3{font-size:20px;line-height:1.6}p{margin:0 0 20px}.opening{border-top:5px solid #235f59;padding:30px 0;margin:45px 0;display:grid;grid-template-columns:220px 1fr;gap:40px}.opening h2{margin:0;font-size:26px}.contents{display:flex;flex-wrap:wrap;gap:25px;padding:18px 0;border-block:1px solid #bfcfca}.contents a{font-size:14px;text-underline-offset:5px}.feature{padding:45px 0}.spread{display:grid;grid-template-columns:1fr 1fr;border:1px solid #bfcfca;margin-top:25px}.excerpt{background:#e0eee8;padding:35px;display:flex;flex-direction:column;justify-content:center}.excerpt blockquote{font:30px/1.8 Georgia,serif;white-space:pre-line;margin:20px 0}.annotation{padding:35px;background:white}.small{font-size:13px;color:#526b65}.selection{padding:35px 0}.selection dl{margin:0;border-top:2px solid #235f59}.selection dl div{display:grid;grid-template-columns:240px 1fr;gap:30px;padding:24px 10px;border-bottom:1px solid #bfcfca}.selection dt{font-size:18px;font-weight:bold}.selection dd{margin:0}.bridge{background:#f4e8d0;padding:35px;margin:40px 0;border-left:6px solid #b4813d}.archive{display:grid;grid-template-columns:220px 1fr;gap:40px;margin:60px 0}.archive aside{border-top:4px solid #235f59;padding-top:20px}.source section{margin-bottom:30px;padding-bottom:20px;border-bottom:1px solid #cbd7d2}.source h3{margin-top:0}.source ul{padding-left:22px}.contact{background:#245e57;color:white;padding:35px;margin-top:35px}.contact a{display:inline-block;margin:8px 15px 8px 0}.related{padding:25px 0;display:flex;gap:20px;flex-wrap:wrap}footer{padding:30px;text-align:center;font-size:12px;color:#526b65}@media(max-width:700px){main{padding:20px}h1{font-size:34px}.subtitle{font-size:21px}.opening,.archive,.spread{grid-template-columns:1fr;gap:20px}.selection dl div{grid-template-columns:1fr;gap:8px}.spread{gap:0}.excerpt,.annotation,.bridge,.contact{padding:24px}h2{font-size:25px}.excerpt blockquote{font-size:27px}.opening{margin-top:25px}header{gap:20px}.archive{margin:35px 0}}'''

def eligible(p):
    return p['page_type']=='초등영어과외' and not p.get('school_name') and not any(w in p['breadcrumb_label'] for w in ['수학','영어','초등','중등','고등'])

def render(s,p=None):
    production=p is not None
    p=p or next(p for p in PAGES if p['page_type']=='초등영어과외' and p['breadcrumb_label']==s['region'])
    backup=ROOT/'backup_output_elementary_english'/p['slug']/'index.html'
    old=BeautifulSoup((backup if backup.exists() else OUT/p['slug']/'index.html').read_text(encoding='utf-8'),'html.parser')
    content=old.select_one('article .content')
    groups=[]; active=None
    for n in content.find_all(recursive=False):
        if n.name=='h3': active=[n.get_text(' ',strip=True),[]]; groups.append(active)
        elif active is not None and n.name in ['p','ul']: active[1].append(str(n))
    source=''.join(f'<section><h3>{e(h)}</h3>{"".join(nodes)}</section>' for h,nodes in groups)
    feature=f'<section class="feature" id="reading"><div class="eyebrow">Reading room / 읽고 활용하기</div><h2>{e(s["feature"])}</h2><p>{e(s["intro"])}</p><div class="spread"><div class="excerpt"><span class="eyebrow">짧은 영어 자료</span><blockquote lang="en">{e(s["quote"])}</blockquote><p class="small">{e(s["caption"])}</p></div><div class="annotation"><h3>이 자료에서 확인할 것</h3><p>{e(s["explain"])}</p><p class="small">설명용으로 만든 예시입니다. 특정 학년의 필수 진도나 실제 학생 사례가 아닙니다.</p></div></div></section>'
    selection='<section class="selection" id="materials"><div class="eyebrow">Book selection / 자료 고르기</div><h2>교재 이름보다, 아이에게 필요한 역할부터</h2><dl>'+''.join(f'<div><dt>{e(h)}</dt><dd>{e(t)}</dd></div>' for h,t in s['choices'])+'</dl></section>'
    bridge=f'<section class="bridge" id="school"><div class="eyebrow">School connection / 학교 영어</div><h2>교과서와 별개의 공부로 남지 않도록</h2><p>{e(s["bridge"])}</p><h3>영역 사이의 균형</h3><p>{e(s["balance"])}</p></section>'
    sections={'feature':feature,'selection':selection,'bridge':bridge}
    related=''
    for kind in ['영어과외','중등영어과외']:
        target=next((x for x in PAGES if x['page_type']==kind and all(x.get(k)==p.get(k) for k in ['province','city','locality','breadcrumb_label'])),None)
        if target: related+=f'<a href="/{target["slug"]}/">{e(s["region"])} {kind}</a>'
    nav=''.join(f'<a href="/preview-elementary-english-{x["key"]}/#start">{x["region"]} 예시</a>' for x in SAMPLES)
    title=s.get('title',f'{s["region"]} 초등영어과외 | {s["topic"]} – 좋은공부')
    html=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{e(title)}</title><meta name="description" content="{e(s['lead'])}"><style>{CSS}</style></head><body><header><a class="brand" href="/">좋은공부</a><a href="#consult">초등영어 상담</a></header><main><nav class="review">{nav}<a href="/{p['slug']}/">기존 페이지</a></nav><h1>{e(s['region'])} 초등영어과외</h1><p class="subtitle">{e(s['headline'])}</p><figure class="image"><img src="/assets/images/content/body-common.webp" width="800" height="8000" alt="좋은공부 과외 학습 안내"></figure><section class="opening" id="start"><div><div class="eyebrow">Elementary English</div><h2>초등 영어를<br>이어주는 기준</h2></div><div><p>{e(s['lead'])}</p><p class="small">초등영어 전반의 안내입니다. 아래 대표 자료만 가르치는 과정이 아니며, 학년과 현재 수준에 맞춰 자료와 분량을 조정합니다.</p></div></section><nav class="contents"><a href="#materials">교재 선택 기준</a><a href="#reading">영어 자료 살펴보기</a><a href="#school">학교 영어 연결</a><a href="#original">학습 계획 읽기</a></nav>{''.join(sections[k] for k in s['order'])}<section class="archive" id="original"><aside><div class="eyebrow">Study reference</div><h2>{e(s['region'])}<br>초등영어 학습 계획</h2><p class="small">현재 교재와 학습 기록을 바탕으로 기초, 복습, 학교 학습을 함께 살펴봅니다.</p></aside><div class="source">{source}</div></section><section class="contact" id="consult"><h2>지금 읽는 교재와 배운 표현을 알려주세요.</h2><p>학교·학년, 사용 중인 교재, 듣기 자료 유무와 읽기·말하기에서 어려운 부분을 정리해 주세요. 지도 가능 지역과 방식, 일정 및 비용은 상담에서 확인이 필요합니다.</p><a href="tel:01049479030">전화 상담</a><a href="sms:01049479030">문자 문의</a></section><nav class="related">{related}</nav></main><footer>초등영어과외 검토용 미리보기 · 미배포</footer></body></html>'''
    doc=BeautifulSoup(html,'html.parser')
    if production:
        doc.select_one('.review').decompose()
        doc.footer.string='좋은공부 · 지역별 초등영어 학습 안내'
        head=deepcopy(old.head)
        for n in head.select('link[rel=stylesheet],style,meta[name=robots]'): n.decompose()
        head.append(deepcopy(doc.style))
        head.title.string=title
        head.select_one('meta[name=description]')['content']=s['lead']
        for selector,value in [('meta[property="og:title"]',title),('meta[name="twitter:title"]',title),('meta[property="og:description"]',s['lead']),('meta[name="twitter:description"]',s['lead'])]:
            if head.select_one(selector): head.select_one(selector)['content']=value
        for script in head.select('script[type="application/ld+json"]'):
            data=json.loads(script.string)
            for node in data.get('@graph',[]):
                if node.get('@type')=='WebPage': node.update(name=title,description=s['lead'])
            script.string=json.dumps(data,ensure_ascii=False,separators=(',',':'))
        head.append(doc.new_tag('meta',attrs={'name':'goodstudy-template','content':'regional-elementary-english-v1'}))
        doc.head.replace_with(head)
        seen={a['href'] for a in doc.select('.related a[href]')}|{'/'+p['slug']+'/'}
        for a in old.select('.related-section a[href]'):
            if a['href'] in seen: continue
            seen.add(a['href'])
            link=doc.new_tag('a',href=a['href']); link.string=(a.select_one('strong') or a).get_text(' ',strip=True)
            doc.select_one('.related').append(link)
        assert doc.select_one('link[rel=canonical]')['href']==old.select_one('link[rel=canonical]')['href']
        assert doc.select_one('meta[property="og:image"]')['content']==old.select_one('meta[property="og:image"]')['content']
        assert not doc.select_one('meta[name=robots][content*=noindex]')
        assert not doc.select_one('link[rel=stylesheet]')
        assert 'preview-' not in str(doc)
    ids=[n['id'] for n in doc.select('[id]')]
    assert len(ids)==len(set(ids))
    assert doc.h1.find_next('img')['src']=='/assets/images/content/body-common.webp'
    assert len(doc.select('h1'))==1
    for a in doc.select('a[href^="#"]'): assert doc.find(id=a['href'][1:])
    for a in doc.select('a[href^="/"]'):
        if not a['href'].startswith('/preview-'): assert (OUT/a['href'].strip('/')).exists()
    text=doc.get_text(' ',strip=True)
    assert all(n.get_text(' ',strip=True) in text for n in BeautifulSoup(source,'html.parser').select('p,li'))
    before=[n.get_text(' ',strip=True) for n in content.select('p,li')]
    folder=ROOT/'candidate_output_elementary_english'/p['slug'] if production else OUT/f'preview-elementary-english-{s["key"]}'
    folder.mkdir(parents=True,exist_ok=True); (folder/'index.html').write_text(str(doc),encoding='utf-8')
    return {'region':s['region'],'slug':p['slug'],'title':title,'description':s['lead'],'variant':s['key'],'original_items':len(before),'retained_items':sum(t in text for t in before)}

def grams(text):
    text=re.sub(r'\s+','',''.join(text))
    for s in SAMPLES: text=text.replace(s['region'],'지역')
    return {text[i:i+5] for i in range(max(0,len(text)-4))}

def preview():
    print(json.dumps([render(s) for s in SAMPLES],ensure_ascii=False))
    texts={}
    for s in SAMPLES:
        doc=BeautifulSoup((OUT/f'preview-elementary-english-{s["key"]}'/'index.html').read_text(encoding='utf-8'),'html.parser')
        for n in doc.select('header,nav,footer,.contact,.image'): n.decompose()
        texts[s['region']]=grams(doc.get_text(' ',strip=True))
    scores={a+' / '+b:round(100*len(texts[a]&texts[b])/len(texts[a]|texts[b]),1) for a,b in combinations(texts,2)}
    report={'metric':'5-character set Jaccard; whitespace removed, region names normalized, navigation/contact excluded; not a Naver score','pairwise_percent':scores}
    (ROOT/'audit/elementary-english-preview-similarity.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

def rollout(apply_output):
    targets=[p for p in PAGES if eligible(p)]
    reports=[]
    print(f'Targets: {len(targets)}',flush=True)
    for p in targets:
        text=BeautifulSoup(p['body_html'],'html.parser').get_text(' ',strip=True)
        scores=[sum(text.count(w) for w in words) for words in [('파닉스','발음','철자'),('읽기','문장','교재'),('듣기','말하기','표현')]]
        base=next((s for s in SAMPLES if s['region']==p['breadcrumb_label']),SAMPLES[max(range(3),key=lambda i:scores[i])])
        s=deepcopy(base); s['region']=p['breadcrumb_label']
        label=' '.join(dict.fromkeys(filter(None,[p['province'],p['city'],p['locality'],p['breadcrumb_label']])))
        s['title']=label+' 초등영어과외 | '+s['topic']+' – 좋은공부'
        s['lead']=base['lead'].replace(base['region'],label,1)
        reports.append(render(s,p))
        if len(reports)%200==0: print(f'Validated {len(reports)}',flush=True)
    assert len({r['title'] for r in reports})==len(reports)
    assert len({r['description'] for r in reports})==len(reports)
    assert all(r['retained_items']>=r['original_items']-1 for r in reports)
    if apply_output:
        for p in targets:
            backup=ROOT/'backup_output_elementary_english'/p['slug']/'index.html'
            backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists(): shutil.copy2(OUT/p['slug']/'index.html',backup)
            shutil.copy2(ROOT/'candidate_output_elementary_english'/p['slug']/'index.html',OUT/p['slug']/'index.html')
        changed=set(filter(None,subprocess.check_output(['git','diff','HEAD','--name-only','-z','--','output'],cwd=ROOT).decode('utf-8').split('\0')))
        assert changed=={f'output/{p["slug"]}/index.html' for p in targets}
    (ROOT/'audit/elementary-english-rollout.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'validated':len(reports),'applied':apply_output,'variants':dict(Counter(r['variant'] for r in reports)),'retention':dict(Counter(f"{r['retained_items']}/{r['original_items']}" for r in reports))}))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--apply-output',action='store_true')
    args=parser.parse_args()
    assert not args.apply_output or args.all
    if args.all: rollout(args.apply_output)
    else: preview()
