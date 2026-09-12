"""High-school English local previews with original content preservation."""
import json
import re
import argparse
import shutil
import subprocess
from collections import Counter
from itertools import combinations
from pathlib import Path
from html import escape as e
from copy import deepcopy
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'
PAGES=json.loads((ROOT/'intermediate/normalized-pages.json').read_text(encoding='utf-8'))
SAMPLES=[
dict(region='강남구',key='gangnam',focus='논리 독해와 내신 연결',headline='해석 다음에는, 글쓴이의 생각을 읽습니다.',
lead='강남구 고등영어과외는 고1·고2·고3의 어휘와 구문 기초를 살피면서 내신과 모의고사 독해를 연결합니다. 문장마다 뜻은 알지만 글 전체의 주장을 놓친다면, 글쓴이가 소개한 생각과 실제로 지지하는 생각을 구분하는 연습이 필요합니다.',
question='이 글은 빠른 답변과 이해의 관계를 어떻게 보고 있나요?',
passage=[('배경의 믿음','People often assume that the student who answers first understands a question best. In a classroom where speed is rewarded, pausing may therefore appear to be a weakness.','첫 문장은 사람들이 흔히 하는 생각을 소개합니다. 이 생각이 곧 글쓴이의 결론인지 아직 단정하지 않습니다.'),('관점 전환','Yet a pause can give a learner time to compare an attractive answer with the evidence and notice a hidden assumption.','Yet 뒤에서 멈춤의 다른 역할을 제시합니다. can은 가능성을 나타내며 모든 멈춤이 유익하다고 단정하지 않습니다.'),('주장의 범위','This does not mean that slow answers are always better. It means that speed alone is an unreliable measure of understanding.','느린 답이 언제나 더 좋다는 주장도 배제합니다. 핵심은 속도 하나만으로 이해를 평가하기 어렵다는 것입니다.')],
options=[('A','Slow answers always reveal deeper understanding.','범위 확대','always가 느린 답의 우월성을 단정합니다. 마지막 문장이 이 해석을 명시적으로 배제합니다.',False),('B','Understanding should not be judged by speed alone.','주장 일치','speed alone이라는 한정 조건을 유지하며 마지막 문장의 요지를 바꾸어 표현합니다.',True),('C','Students should avoid answering questions in class.','내용 추가','수업에서 답하지 말라는 행동 지침은 제시되지 않았습니다. 멈춤의 가능성을 침묵 권고로 바꿨습니다.',False)],
school='학교 범위 지문에서는 글의 주장을 한 문장으로 정리한 뒤, 대조 표현과 한정어가 들어간 문장을 정확히 해석합니다. 본문을 외운 것과 낯선 선택지로 바꾸어 표현한 주장을 알아보는 것은 따로 확인합니다.',
unseen='처음 보는 글에서는 주장을 먼저 정해 놓지 말고, 뒤 문장이 앞의 생각을 지지하는지 제한하는지 갱신하며 읽습니다. 익숙한 연결어가 없어도 문장 사이의 의미 관계를 확인합니다.',
next='정답을 골랐다면 A의 always를 지문이 왜 허용하지 않는지 말로 설명해 보세요. 다음 글에서도 통념 소개와 글쓴이의 결론을 구분할 수 있는지 확인합니다.'),
dict(region='복대동',key='bokdae',focus='구문 이해와 선택지 판단',headline='맞는 말처럼 보여도, 지문이 말한 범위까지.',
lead='복대동 고등영어과외에서는 어휘·구문·독해를 분리해서 점검한 뒤 학교 내신과 수능형 학습에 연결합니다. 특히 해석한 내용보다 강한 결론을 선택하는 경우에는 문장의 구조뿐 아니라 근거가 뒷받침하는 범위를 함께 살펴봅니다.',
question='독서 모임 참여와 과제 제출의 관계에서 확정할 수 없는 것은 무엇인가요?',
passage=[('관찰된 사실','At one school, students who joined an optional reading group submitted more assignments on time than students who did not join.','선택적으로 참여한 집단에서 관찰된 차이입니다. who절은 어떤 학생들인지 한정하며, 두 집단이 처음부터 같았다고 말하지 않습니다.'),('가능한 다른 설명','It is tempting to conclude that the group caused the difference. However, students who were already well organized may have been more likely to participate.','However 뒤에서 기존의 학습 습관이라는 다른 가능성을 제시합니다. may have been은 확인된 사실이 아니라 가능한 설명입니다.'),('근거의 한계','Without information about their earlier habits, the observation cannot establish cause and effect. The group may still be helpful, but the evidence supports a more cautious conclusion.','인과관계를 확정할 근거가 부족하다는 결론입니다. 효과가 없다고 증명한 것과는 다릅니다.')],
options=[('A','The reading group certainly improved assignment habits.','인과 단정','certainly와 improved는 참여가 변화의 원인임을 확정합니다. 지문은 그 인과관계를 확정할 수 없다고 말합니다.',False),('B','The observation alone does not prove the group caused the difference.','근거 수준 일치','관찰된 차이를 인정하면서도 그 차이의 원인을 확정하지 않는 결론입니다.',True),('C','Organized students never benefit from reading groups.','근거 없는 일반화','never와 전체 집단에 대한 주장은 지문에 없습니다. 다른 설명의 가능성을 효과 부정으로 바꿨습니다.',False)],
school='내신 준비에서는 관계절과 조동사 표현을 정확히 읽고, 문장에서 확정한 사실과 가능성으로 남긴 내용을 구분합니다. 문법 용어를 외우는 데서 멈추지 않고 그 형태가 의미를 어떻게 제한하는지 설명합니다.',
unseen='모의고사형 독해에서는 선택지가 원문의 가능성을 확정으로 바꾸거나 관찰을 원인으로 바꾸지 않았는지 확인합니다. 다만 모든 지문에 같은 의심을 적용하지 말고, 해당 글이 제공한 근거를 기준으로 판단합니다.',
next='오답을 지울 때 낯선 단어가 있어서인지, 글이 말하지 않은 결론이라서인지 구분해 보세요. 이 예시에서는 독서 모임의 실제 효과를 평가하는 것이 아니라 근거의 범위를 읽는 연습을 합니다.'),
dict(region='울릉군',key='ulleung',focus='조건 해석과 독해 전략',headline='중요한 조건 하나가, 결론의 범위를 바꿉니다.',
lead='울릉군 고등영어과외는 현재 학년의 교과 내용과 어휘·문법 기초를 점검하면서 내신과 모의고사 준비를 함께 다룹니다. 긴 문장을 읽고도 조건이나 예외를 놓친다면, 핵심 주장과 그 주장이 성립하는 범위를 나누어 정리해 봅니다.',
question='도서관 운영 시간 확대의 효과에는 어떤 조건이 붙어 있나요?',
passage=[('제안된 변화','Keeping a library open later may seem an obvious way to give students more study time. The extra hours, however, are useful only if students can reach the building and return home safely.','운영 시간 확대만 제시한 것이 아니라 안전하게 오갈 수 있어야 한다는 조건을 붙입니다. only if 뒤의 내용을 빠뜨리면 의미가 넓어집니다.'),('조건을 보여주는 경우','For those whose last bus leaves early, a longer opening schedule may change little.','마지막 버스가 일찍 떠나는 학생들의 경우로 접근 문제를 구체화합니다. 모든 학생이 버스를 이용한다고 일반화하지 않습니다.'),('제안의 재정리','A policy designed to increase access must therefore consider transport as well as opening times. More availability on paper does not necessarily produce more opportunity in practice.','결론은 운영 시간을 줄이라는 것이 아니라 교통도 함께 고려하라는 것입니다. 서류상의 확대와 실제 이용 기회를 구분합니다.')],
options=[('A','Later opening hours guarantee more study opportunities for every student.','조건 삭제','guarantee와 every student가 조건을 지웁니다. 지문은 실제 접근성이 없으면 효과가 제한될 수 있다고 설명합니다.',False),('B','Transport conditions matter when longer hours are intended to improve access.','조건 보존','운영 시간과 함께 교통 조건을 고려해야 한다는 결론을 유지합니다.',True),('C','Libraries should close before the last bus leaves.','해결책 추가','폐관 시간을 마지막 버스 이전으로 정하라는 제안은 지문에 없습니다. 예시에서 임의의 정책을 끌어냈습니다.',False)],
school='학교 지문에서는 only if, whose, as well as가 연결하는 내용을 문장 안에서 확인합니다. 접속 표현의 뜻만 적는 대신, 무엇이 조건이고 무엇을 추가로 고려해야 하는지 주어와 함께 정리합니다.',
unseen='낯선 글에서는 사례가 결론을 설명하는지 반박하는지 구분합니다. 버스라는 소재에만 집중하기보다, 실제 이용 조건을 고려해야 한다는 일반적 주장으로 돌아와 선택지를 판단합니다.',
next='only if 뒤를 빼고 첫 두 문장을 요약했을 때 어떤 뜻이 사라지는지 확인해 보세요. 다음 독해에서도 조건·예외·가능성을 나타내는 표현을 빠뜨리지 않고 요약하는지 점검합니다.'),
]

CSS='''*{box-sizing:border-box}html{scroll-padding-top:24px}body{margin:0;background:#f9f7f3;color:#292b31;font:16px/1.85 "Malgun Gothic",sans-serif}a{color:inherit}header{background:#292b31;color:#fff;padding:18px max(22px,calc((100vw - 1120px)/2));display:flex;justify-content:space-between}header a{text-decoration:none}.brand{font-size:24px;font-weight:bold}main{max-width:1120px;margin:auto;padding:24px 28px}.review,.jump,.related{display:flex;gap:22px;flex-wrap:wrap;font-size:14px}h1{font-size:46px;line-height:1.35;margin:35px 0 12px;letter-spacing:-2px}.subtitle{font-size:24px}.image{max-width:800px;margin:30px auto}.image img{width:100%;height:auto;display:block}p{margin:0 0 20px}h2{font-size:30px;line-height:1.45;letter-spacing:-1px}h3{font-size:20px;line-height:1.5}.kicker{font-size:12px;letter-spacing:1.5px;color:#94523a}.intro{padding:35px 0;border-top:5px solid #a45f43;margin-top:35px}.lead{font-size:18px;max-width:900px}.small{font-size:13px;color:#62636a}.jump{padding:20px 0;border-block:1px solid #cfc9c0}.passage{margin:45px 0}.passage h2{max-width:830px}.paragraph{display:grid;grid-template-columns:58% 1fr;border-top:1px solid #cfc9c0}.text{padding:30px 32px;background:#fff;font:22px/1.8 Georgia,serif}.text p{margin:0}.number{font:12px/1.4 "Malgun Gothic",sans-serif;color:#94523a;display:block;margin-bottom:14px}.margin{padding:30px 25px;background:#efe9df}.margin h3{font-size:17px;margin:0 0 12px}.margin p{font-size:15px;margin:0}.judgment{padding:35px;background:#292b31;color:#fff}.judgment .kicker{color:#dfb39d}.judgment .small{color:#d4d0ca}.option{padding:24px 0;border-top:1px solid #66656a;display:grid;grid-template-columns:45px 1fr;gap:16px}.letter{border:1px solid #aba6a1;width:34px;height:34px;line-height:32px;text-align:center}.option .english{font:21px/1.7 Georgia,serif;margin:0 0 10px}.option details{font-size:14px}.option summary{cursor:pointer;color:#e6bd9f;padding:5px 0}.option details p{margin:12px 0 0}.two-tracks{display:grid;grid-template-columns:1fr 1fr;gap:30px;padding:42px 0}.track{border-top:4px solid #a45f43;padding-top:22px}.transfer{border-left:4px solid #a45f43;padding:10px 25px;margin:10px 0 45px}.source{padding:35px 0;border-top:1px solid #cfc9c0}.source section{padding:22px 0;border-bottom:1px solid #d8d2c9}.source h3{margin:0 0 16px}.source ul{padding-left:22px}.contact{padding:30px;border:1px solid #aca69f;margin-top:35px}.contact a{display:inline-block;padding:10px 20px;background:#292b31;color:white;margin:6px 12px 6px 0}.related{padding:25px 0}footer{text-align:center;padding:25px;font-size:12px;color:#62636a}@media(max-width:760px){main{padding:20px}h1{font-size:33px}.subtitle{font-size:21px}h2{font-size:25px}.paragraph,.two-tracks{grid-template-columns:1fr}.text{padding:24px;font-size:21px}.margin{padding:22px}.judgment{padding:24px 20px}.option{grid-template-columns:32px minmax(0,1fr);gap:12px}.letter{width:30px;height:30px;line-height:28px}.option .english{font-size:20px}.contact{padding:22px}}'''

def render(s,p=None):
    production=p is not None
    p=p or next(p for p in PAGES if p['page_type']=='고등영어과외' and p['breadcrumb_label']==s['region'])
    backup=ROOT/'backup_output_high_english'/p['slug']/'index.html'
    old=BeautifulSoup((backup if backup.exists() else OUT/p['slug']/'index.html').read_text(encoding='utf-8'),'html.parser')
    content=old.select_one('article .content'); groups=[]; active=None
    for n in content.find_all(recursive=False):
        if n.name in ['h2','h3']:
            if n.name=='h2' and active is None: continue
            active=[n.get_text(' ',strip=True),[]]; groups.append(active)
        elif active is not None and n.name in ['p','ul','ol']: active[1].append(str(n))
    source=''.join(f'<section><h3>{e(h)}</h3>{"".join(ns)}</section>' for h,ns in groups)
    paragraphs=''.join(f'<div class="paragraph"><div class="text"><span class="number">PASSAGE {i:02d}</span><p lang="en">{e(t)}</p></div><aside class="margin"><h3>{e(h)}</h3><p>{e(note)}</p></aside></div>' for i,(h,t,note) in enumerate(s['passage'],1))
    options=''.join(f'<div class="option"><span class="letter">{e(k)}</span><div><p class="english" lang="en">{e(t)}</p><details><summary>판단 근거 보기</summary><p><strong>{"적절한 요약" if correct else "부적절한 요약"} · {e(label)}</strong><br>{e(reason)}</p></details></div></div>' for k,t,label,reason,correct in s['options'])
    links=''
    for kind in ['영어과외','중등영어과외','고등수학과외']:
        target=next((x for x in PAGES if x['page_type']==kind and all(x.get(k)==p.get(k) for k in ['province','city','locality','breadcrumb_label'])),None)
        if target: links+=f'<a href="/{target["slug"]}/">{e(s["region"])} {kind}</a>'
    nav=''.join(f'<a href="/preview-high-english-{x["key"]}/#start">{x["region"]} 예시</a>' for x in SAMPLES)
    title=s.get('title',f'{s["region"]} 고등영어과외 | {s["focus"]} – 좋은공부')
    html=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{e(title)}</title><meta name="description" content="{e(s['lead'])}"><style>{CSS}</style></head><body><header><a class="brand" href="/">좋은공부</a><a href="#consult">고등영어 상담</a></header><main><nav class="review">{nav}<a href="/{p['slug']}/">기존 페이지</a></nav><h1>{e(s['region'])} 고등영어과외</h1><p class="subtitle">{e(s['headline'])}</p><figure class="image"><img src="/assets/images/content/body-common.webp" width="800" height="8000" alt="좋은공부 과외 학습 안내"></figure><section class="intro" id="start"><span class="kicker">HIGH SCHOOL ENGLISH / 읽은 뒤의 판단</span><h2>문장의 뜻과 글의 주장을 함께 읽습니다</h2><p class="lead">{e(s['lead'])}</p><p class="small">고등영어 전반의 학습 안내입니다. 아래 지문은 설명용으로 직접 만든 짧은 예시이며 실제 연구 결과·학교 시험·수능 기출이 아닙니다. 실제 시험의 길이나 난도를 그대로 재현하지 않습니다.</p></section><nav class="jump"><a href="#argument">글의 흐름</a><a href="#choices">선택지의 범위</a><a href="#tracks">내신과 모의고사</a><a href="#original">학습 설명</a></nav><section class="passage" id="argument"><span class="kicker">TEXT &amp; COMMENTARY</span><h2>{e(s['question'])}</h2><p>한 문장의 번역에 머무르지 않고, 각 부분이 글 전체에서 맡는 역할을 살펴봅니다.</p>{paragraphs}</section><section class="judgment" id="choices"><span class="kicker">READ, THEN DECIDE</span><h2>글 전체를 가장 적절하게 요약한 것은?</h2><p class="small">세 문장의 범위를 비교한 뒤 판단 근거를 펼쳐보세요. 실제 시험의 선택지 수나 배점을 재현한 문제는 아닙니다.</p>{options}</section><section class="two-tracks" id="tracks"><article class="track"><span class="kicker">KNOWN TEXT / 학교 범위</span><h2>배운 글은 정확하게</h2><p>{e(s['school'])}</p></article><article class="track"><span class="kicker">UNSEEN TEXT / 새로운 글</span><h2>처음 보는 글은 근거 있게</h2><p>{e(s['unseen'])}</p></article></section><section class="transfer"><h3>이 지문을 마친 뒤 남길 질문</h3><p>{e(s['next'])}</p></section><section class="source" id="original"><span class="kicker">STUDY FOUNDATION</span><h2>{e(s['region'])} 고등영어 학습의 바탕</h2><p>어휘·구문 기초와 학교 학습, 모의고사 결과를 함께 살피며 실제 복습할 수 있는 범위로 계획을 조정합니다.</p>{source}</section><section class="contact" id="consult"><h2>최근 지문과 선택한 답을 함께 준비해 주세요.</h2><p>학교·학년, 교과서와 범위 자료, 최근 답안에서 어려웠던 지점을 알려주세요. 학교별 출제 경향이나 성적 향상을 임의로 단정하지 않습니다. 지도 가능 여부·방식·일정·비용은 문의 시 확인합니다.</p><a href="tel:01049479030">전화 상담</a><a href="sms:01049479030">문자 문의</a></section><nav class="related">{links}</nav></main><footer>고등영어과외 검토용 미리보기 · 미배포</footer></body></html>'''
    doc=BeautifulSoup(html,'html.parser')
    if production:
        doc.select_one('.review').decompose()
        doc.footer.string='좋은공부 · 고등영어 학습 안내'
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
        head.append(doc.new_tag('meta',attrs={'name':'goodstudy-template','content':'high-english-v1'}))
        doc.head.replace_with(head)
        seen={a['href'] for a in doc.select('a[href]')}|{'/'+p['slug']+'/'}
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
    text=doc.get_text(' ',strip=True)
    assert doc.h1.find_next('img')['src']=='/assets/images/content/body-common.webp'
    assert len(doc.select('h1'))==1
    ids=[n['id'] for n in doc.select('[id]')]; assert len(ids)==len(set(ids))
    for a in doc.select('a[href^="#"]'): assert doc.find(id=a['href'][1:])
    for a in doc.select('a[href^="/"]'):
        if not a['href'].startswith('/preview-'): assert (OUT/a['href'].strip('/')).exists(),a['href']
    assert all(n.get_text(' ',strip=True) in text for n in BeautifulSoup(source,'html.parser').select('p,li'))
    before=[n.get_text(' ',strip=True) for n in content.select('p,li')]
    folder=ROOT/'candidate_output_high_english'/p['slug'] if production else OUT/f'preview-high-english-{s["key"]}'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'index.html').write_text(str(doc),encoding='utf-8')
    return {'region':s['region'],'slug':p['slug'],'title':title,'description':s['lead'],'variant':s['key'],'original_items':len(before),'retained_items':sum(t in text for t in before)}

def shingles(path):
    doc=BeautifulSoup(path.read_text(encoding='utf-8'),'html.parser')
    for n in doc.select('head,header,nav,footer,.contact,.image,.original-image'): n.decompose()
    text=doc.get_text(' ',strip=True)
    for s in SAMPLES: text=text.replace(s['region'],'지역')
    text=re.sub(r'\s+','',text)
    return {text[i:i+5] for i in range(len(text)-4)}

def preview():
    print(json.dumps([render(s) for s in SAMPLES],ensure_ascii=False))
    sets={s['region']:shingles(OUT/f'preview-high-english-{s["key"]}'/'index.html') for s in SAMPLES}
    score=lambda a,b:round(100*len(a&b)/len(a|b),1)
    report={'method':'5-character set Jaccard; whitespace removed, region normalized; head/navigation/contact/image excluded. Not a Naver score.', 'pairwise':{a+' / '+b:score(sets[a],sets[b]) for a,b in combinations(sets,2)},'bokdae_vs_existing':{kind:score(sets['복대동'],shingles(OUT/f'복대동{kind}'/'index.html')) for kind in ['과외','영어과외','초등영어과외','중등영어과외','중등수학과외']}}
    (ROOT/'audit/high-english-preview-similarity.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

def rollout(apply_output):
    targets=[p for p in PAGES if p['page_type']=='고등영어과외']
    reports=[]
    print(f'Targets: {len(targets)}',flush=True)
    for p in targets:
        text=BeautifulSoup(p['body_html'],'html.parser').get_text(' ',strip=True)
        scores=[sum(text.count(w) for w in words) for words in [('독해','흐름','연결어'),('문법','근거','문장'),('조건','범위','모의고사')]]
        base=next((s for s in SAMPLES if s['region']==p['breadcrumb_label']),SAMPLES[max(range(3),key=lambda i:scores[i])])
        s=deepcopy(base); s['region']=p['breadcrumb_label']
        label=' '.join(dict.fromkeys(filter(None,[p['province'],p['city'],p['locality'],p['breadcrumb_label']])))
        s['title']=label+' 고등영어과외 | '+s['focus']+' – 좋은공부'
        s['lead']=base['lead'].replace(base['region'],label,1)
        reports.append(render(s,p))
        if len(reports)%200==0: print(f'Validated {len(reports)}',flush=True)
    assert len({r['title'] for r in reports})==len(reports)
    assert len({r['description'] for r in reports})==len(reports)
    assert all(r['retained_items']>=r['original_items']-1 for r in reports)
    if apply_output:
        for p in targets:
            backup=ROOT/'backup_output_high_english'/p['slug']/'index.html'
            backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists(): shutil.copy2(OUT/p['slug']/'index.html',backup)
            shutil.copy2(ROOT/'candidate_output_high_english'/p['slug']/'index.html',OUT/p['slug']/'index.html')
        changed=set(filter(None,subprocess.check_output(['git','diff','HEAD','--name-only','-z','--','output'],cwd=ROOT).decode('utf-8').split('\0')))
        assert changed=={f'output/{p["slug"]}/index.html' for p in targets}
    (ROOT/'audit/high-english-rollout.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'validated':len(reports),'applied':apply_output,'variants':dict(Counter(r['variant'] for r in reports)),'retention':dict(Counter(f"{r['retained_items']}/{r['original_items']}" for r in reports))}))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--apply-output',action='store_true')
    args=parser.parse_args()
    assert not args.apply_output or args.all
    if args.all: rollout(args.apply_output)
    else: preview()
