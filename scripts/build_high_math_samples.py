"""Three isolated high-school math previews; never modifies production pages."""
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
from urllib.parse import unquote, urlsplit
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'
SAMPLES=[
dict(region='강남구',key='gangnam',focus='함수의 범위와 최솟값',headline='공식을 쓰기 전에, x가 움직일 자리를 봅니다.',
lead='강남구 고등수학과외는 학교 진도와 누적된 개념을 함께 살피며 내신과 수능 기초를 준비합니다. 기존 학습 설명에서 강조한 그래프·식·조건의 연결을, 이차함수의 최솟값을 판단하는 짧은 문제로 구체화했습니다.',
problem='실수 a에 대하여 0 ≤ x ≤ 2에서 f(x) = (x − a)² + 1의 최솟값을 구하세요.',
given='움직이는 값은 x, 고정해 두고 경우를 나눌 값은 a입니다. 꼭짓점의 x좌표 a가 허용 구간 안에 있는지부터 확인합니다.',
route='완전제곱식이므로 먼저 전개할 필요가 없습니다. (x − a)²은 x와 a 사이 거리의 제곱입니다. 구간 [0, 2]에서 a에 가장 가까운 x를 찾으면 됩니다.',
cases=[('a < 0','가장 가까운 점은 x = 0','최솟값 a² + 1'),('0 ≤ a ≤ 2','꼭짓점 x = a가 구간 안','최솟값 1'),('a > 2','가장 가까운 점은 x = 2','최솟값 (2 − a)² + 1')],
verify='a = −1이면 꼭짓점 x = −1은 구간 밖입니다. x = 0에서 최솟값 2를 얻습니다. a = 0과 a = 2에서는 양옆 식도 1이 되어 경계에서 결과가 맞물립니다.',
trap='제곱은 0 이상이므로 최솟값은 항상 1이라고 끝내면 안 됩니다. 등호가 성립하는 x = a가 문제에서 허용되는지를 확인해야 합니다.',
answer='a < 0: a² + 1 / 0 ≤ a ≤ 2: 1 / a > 2: (2 − a)² + 1',
record='답안에는 꼭짓점의 위치에 따른 세 구간과 각 구간에서 최솟값을 만드는 x를 남깁니다. 숫자로 나온 답만 적으면 범위 판단을 했는지 확인하기 어렵습니다.',
practice='복습에서는 구간을 1 ≤ x ≤ 3으로 바꿔보세요. 외운 세 식을 옮기는 대신, a와 구간 사이의 거리를 다시 판단합니다. 최솟값이 1인 범위가 1 ≤ a ≤ 3으로 바뀌는지 설명해 봅니다.'),
dict(region='복대동',key='bokdae',focus='로그방정식의 정의역과 검산',headline='계산에서 나온 값과, 답으로 남길 값은 다릅니다.',
lead='복대동 고등수학과외에서는 개념을 알고도 문제에 적용하지 못하는 지점과 서술형 풀이의 근거를 나누어 점검합니다. 원문에 있는 식 세우기·계산 구분을 바탕으로, 로그방정식에서 후보 해를 걸러내는 과정을 살펴봅니다.',
problem='log₂(x − 1) + log₂(x − 3) = 3을 만족하는 실수 x를 구하세요.',
given='로그의 진수는 양수여야 합니다. x − 1 > 0이고 x − 3 > 0이므로 처음부터 x > 3이라는 범위를 기록합니다.',
route='두 진수가 양수인 범위에서 로그의 합을 곱의 로그로 묶습니다. log₂((x − 1)(x − 3)) = 3이므로 (x − 1)(x − 3) = 8입니다.',
cases=[('대수적 후보','x² − 4x − 5 = 0','(x − 5)(x + 1) = 0'),('x = −1 검토','진수가 −2와 −4','실수 로그가 정의되지 않아 제외'),('x = 5 검토','진수가 4와 2','log₂4 + log₂2 = 2 + 1 = 3')],
verify='x = −1에서 두 진수의 곱은 양수이지만 각각의 로그는 정의되지 않습니다. 곱이 양수라는 조건만으로 원래 식의 정의역을 대체할 수 없습니다.',
trap='이차방정식의 두 근 −1, 5를 모두 답으로 쓰는 것은 변형한 식과 원래 식의 범위를 혼동한 결과입니다. 정리한 식에서 찾은 값은 원래 조건을 통과하기 전까지 후보입니다.',
answer='x = 5',
record='답안의 첫 줄에 x > 3을 쓰고, 마지막 줄에 후보 중 x = 5만 그 조건을 만족한다고 남깁니다. 검산은 원래 로그식에 대입해 수행합니다.',
practice='같은 식의 우변을 0으로 바꾸면 후보는 2 ± √2가 됩니다. 이 중 x > 3인 2 + √2만 남는 이유를 말해보세요. 숫자가 바뀌어도 정의역을 먼저 쓰는 습관이 유지되는지 확인합니다.'),
dict(region='울릉군',key='ulleung',focus='수열의 조건과 합의 연결',headline='부분의 합에서 전체의 규칙을 찾아갑니다.',
lead='울릉군 고등수학과외는 문제 수를 늘리기 전에 조건과 구해야 할 값을 표시하고 개념을 설명하는 학습을 다룹니다. 원문에서 강조한 조건 읽기를 등차수열의 부분합 문제에 적용해, 주어진 합이 어떤 항을 알려주는지 살펴봅니다.',
problem='등차수열 {aₙ}에서 a₁ + a₂ + a₃ = 12, a₄ + a₅ + a₆ = 30일 때 첫 10개 항의 합 S₁₀을 구하세요.',
given='연속한 세 항의 합이 두 번 주어졌습니다. 등차수열에서 세 항의 평균은 가운데 항과 같다는 관계를 이용할 수 있습니다.',
route='첫 조건은 3a₂ = 12, 둘째 조건은 3a₅ = 30입니다. 따라서 a₂ = 4, a₅ = 10입니다. 항 번호 차이가 3이므로 두 값의 차이는 공차의 세 배입니다.',
cases=[('공차 결정','a₅ − a₂ = 3d = 6','d = 2'),('첫째항 복원','a₁ = a₂ − d','a₁ = 2, a₁₀ = 20'),('전체 합 계산','S₁₀ = 10(a₁ + a₁₀) ÷ 2','S₁₀ = 110')],
verify='찾은 수열은 2, 4, 6, 8, 10, 12, …입니다. 첫 세 항의 합은 12, 다음 세 항의 합은 30이므로 두 조건을 모두 만족합니다. 첫 조건만 맞는다고 검산을 끝내지 않습니다.',
trap='a₅ − a₂ = 6을 공차라고 생각하면 항 사이의 간격을 놓친 것입니다. 둘째항에서 다섯째항까지는 공차를 세 번 더합니다.',
answer='S₁₀ = 110',
record='가운데 항을 사용한 근거와 3d = 6을 남기고, 첫째항과 열째항으로 합을 계산합니다. a₁과 d의 연립방정식을 먼저 세우는 방법도 올바른 대안입니다.',
practice='같은 조건에서 S₁₁을 구해보세요. a₁₁ = 22이므로 S₁₁ = S₁₀ + a₁₁ = 132입니다. 합 공식으로 다시 계산한 결과와 비교하면 항 번호를 잘못 넣었는지 확인할 수 있습니다.')]

CSS='''*{box-sizing:border-box}body{margin:0;color:#21313d;background:#f3f6f8;font:16px/1.85 "Malgun Gothic",sans-serif}a{color:inherit}header{padding:20px max(22px,calc((100vw - 1100px)/2));background:#fff;border-bottom:1px solid #ccd6df;display:flex;justify-content:space-between}.brand{font-size:23px;font-weight:700;text-decoration:none}main{max-width:1100px;margin:auto;padding:25px}h1{font-size:44px;line-height:1.3;letter-spacing:-2px}h2{font-size:29px;line-height:1.45}h3{font-size:20px}.subtitle{font-size:23px}.image{max-width:800px;margin:30px auto}.image img{display:block;width:100%;height:auto}.review,.jump,.related{display:flex;flex-wrap:wrap;gap:18px;font-size:14px}.intro{padding:35px 0}.label{font-size:12px;letter-spacing:2px;color:#456d8a}.small{font-size:13px;color:#526573}.jump{padding:18px 0;border-block:1px solid #b9c9d6}.lab{display:grid;grid-template-columns:240px minmax(0,1fr);margin:40px 0;background:white;border:1px solid #bdcdd9}.rail{padding:26px;background:#e1eaf1}.rail h2{font-size:22px}.work{padding:30px}.problem{font-size:23px;line-height:1.7;padding-bottom:24px;border-bottom:2px solid #315d7c}.cases{margin:30px 0}.case{display:grid;grid-template-columns:140px 1fr;gap:18px;padding:20px 0;border-bottom:1px solid #ced8df}.case p{margin:0}.case strong{color:#315d7c}.result{padding:24px;background:#183d59;color:white;margin-top:25px}.result p{font-size:21px;margin-bottom:0}.checkpoint{padding:5px 0 30px}.checkpoint h2{border-left:5px solid #698b47;padding-left:18px}.warning{background:#edf1e7;padding:24px}.record{padding:25px 0;border-block:1px solid #b9c9d6}.source{padding:30px 0}.source section{margin:25px 0;padding-left:24px;border-left:2px solid #bdcdd9}.source h3{margin-top:0}.contact{background:#e1eaf1;padding:28px}.contact a{display:inline-block;background:#183d59;color:white;padding:10px 20px;margin-right:15px}.related{padding:25px 0}footer{text-align:center;font-size:12px;padding:25px}html{scroll-padding-top:20px}@media(max-width:760px){main{padding:20px}h1{font-size:32px}h2{font-size:25px}.lab{grid-template-columns:1fr}.rail,.work{padding:22px}.case{grid-template-columns:1fr;gap:6px}.problem{font-size:21px}.source section{padding-left:16px}.subtitle{font-size:20px}}'''

def render(s,p=None):
    production=p is not None
    slug=p['slug'] if production else s['region']+'고등수학과외'
    backup=ROOT/'backup_output_high_math'/slug/'index.html'
    old=BeautifulSoup((backup if backup.exists() else OUT/slug/'index.html').read_text(encoding='utf-8'),'html.parser')
    content=old.select_one('article .content')
    groups=[]; active=None
    for n in content.find_all(recursive=False):
        if n.name in ['h2','h3']:
            if n.name=='h2' and active is None: continue
            active=[n.get_text(' ',strip=True),[]]; groups.append(active)
        elif active is not None and n.name in ['p','ul','ol']: active[1].append(str(n))
    source=''.join(f'<section><h3>{e(h)}</h3>{"".join(ns)}</section>' for h,ns in groups)
    cases=''.join(f'<div class="case"><strong>{e(a)}</strong><div><p>{e(b)}</p><p>{e(c)}</p></div></div>' for a,b,c in s['cases'])
    nav=''.join(f'<a href="/preview-high-math-{x["key"]}/#start">{x["region"]} 예시</a>' for x in SAMPLES)
    related=''; seen={'/'+slug+'/'}
    for a in old.select('.related-section a[href]'):
        if a['href'] in seen: continue
        seen.add(a['href'])
        label=(a.select_one('strong') or a).get_text(' ',strip=True)
        related+=f'<a href="{e(a["href"])}">{e(label)}</a>'
    title=s.get('title',f'{s["region"]} 고등수학과외 | {s["focus"]} – 좋은공부')
    html=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{e(title)}</title><meta name="description" content="{e(s['lead'])}"><style>{CSS}</style></head><body><header><a class="brand" href="/">좋은공부</a><a href="#consult">고등수학 상담</a></header><main><nav class="review">{nav}<a href="/{slug}/">기존 페이지</a></nav><h1>{s['region']} 고등수학과외</h1><p class="subtitle">{s['headline']}</p><figure class="image"><img src="/assets/images/content/body-common.webp" width="800" height="8000" alt="좋은공부 과외 학습 안내"></figure><section class="intro" id="start"><span class="label">HIGH SCHOOL MATH / 풀이 설계실</span><h2>{s['focus']}으로 살펴보는 학습 방법</h2><p>{s['lead']}</p><p class="small">고등수학 전반의 학습 안내이며, 아래 단원만 지도한다는 뜻은 아닙니다. 직접 만든 개념 설명용 예시로 실제 학교 기출·수능 난도·성적 향상 사례가 아닙니다. 학년과 이수 과목, 학교 범위에 맞춰 적용 여부를 확인합니다.</p></section><nav class="jump"><a href="#design">조건과 풀이 설계</a><a href="#check">답의 검증</a><a href="#record">서술형 기록과 복습</a><a href="#original">기존 학습 안내</a></nav><section class="lab" id="design"><aside class="rail"><span class="label">BEFORE CALCULATION</span><h2>먼저 고정할 조건</h2><p>{s['given']}</p></aside><article class="work"><span class="label">ONE PROBLEM / 한 문제를 깊게</span><h2>어디서 시작할까요?</h2><p class="problem">{e(s['problem'])}</p><h3>이 풀이를 선택한 이유</h3><p>{e(s['route'])}</p><div class="cases">{cases}</div><div class="result"><span>조건을 반영한 결론</span><p>{e(s['answer'])}</p></div></article></section><section class="checkpoint" id="check"><h2>정답 뒤에 한 번 더 확인합니다</h2><p>{e(s['verify'])}</p><div class="warning"><h3>이렇게 끝내면 놓치는 것</h3><p>{e(s['trap'])}</p></div></section><section class="record" id="record"><span class="label">LEAVE A REASON, NOT JUST A NUMBER</span><h2>답안에 남길 근거와 다음 복습</h2><h3>서술형 기록</h3><p>{e(s['record'])}</p><h3>스스로 다시 확인할 문제</h3><p>{e(s['practice'])}</p></section><section class="source" id="original"><span class="label">STUDY FOUNDATION</span><h2>{s['region']} 고등수학 학습 안내</h2>{source}</section><section class="contact" id="consult"><h2>최근 시험지와 풀다 멈춘 풀이를 준비해 주세요.</h2><p>학교·학년·이수 과목·시험 범위를 확인하고, 개념을 모르는 부분과 풀이 선택이 어려운 부분을 구분합니다. 수업 가능 여부, 방식, 일정과 비용은 문의 시 확인합니다.</p><a href="tel:01049479030">전화 상담</a><a href="sms:01049479030">문자 문의</a></section><nav class="related">{related}</nav></main><footer>고등수학 검토용 미리보기 · 미배포</footer></body></html>'''
    doc=BeautifulSoup(html,'html.parser')
    if production:
        doc.select_one('.review').decompose()
        doc.footer.string='좋은공부 · 고등수학 학습 안내'
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
        head.append(doc.new_tag('meta',attrs={'name':'goodstudy-template','content':'high-math-v1'}))
        doc.head.replace_with(head)
        assert doc.select_one('link[rel=canonical]')['href']==old.select_one('link[rel=canonical]')['href']
        assert doc.select_one('meta[property="og:image"]')['content']==old.select_one('meta[property="og:image"]')['content']
        assert not doc.select_one('meta[name=robots][content*=noindex]')
        assert 'preview-' not in str(doc)
        previous={a['href'] for a in old.select('article .content a[href],.related-section a[href]')}-{'/'+slug+'/'}
        assert previous<={a['href'] for a in doc.select('a[href]')},slug
    original=[x.get_text(' ',strip=True) for x in content.select('p,li')]
    text=doc.get_text(' ',strip=True)
    retained=sum(x in text for x in original)
    assert retained>=len(original)-1,(slug,retained,len(original))
    assert len(doc.select('h1'))==1
    ids=[x['id'] for x in doc.select('[id]')]; assert len(ids)==len(set(ids))
    for a in doc.select('a[href^="#"]'): assert a['href'][1:] in ids
    for a in doc.select('a[href]'):
        href=a['href']
        if href.startswith('/') and not href.startswith('/preview-high-math-'):
            target=OUT/unquote(urlsplit(href).path).strip('/')/'index.html'
            assert target.exists(),href
    assert doc.h1.find_next('img')['src']=='/assets/images/content/body-common.webp'
    path=(ROOT/'candidate_output_high_math'/slug if production else OUT/f'preview-high-math-{s["key"]}')/'index.html'
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(str(doc),encoding='utf-8')
    return dict(region=s['region'],slug=slug,variant=s['key'],description=s['lead'],retention=f'{retained}/{len(original)}',title=title,path=str(path))

def grams(path):
    doc=BeautifulSoup(path.read_text(encoding='utf-8'),'html.parser')
    for n in doc.select('head,header,footer,nav,.contact,#consult'): n.decompose()
    text=doc.get_text(' ',strip=True)
    for r in ['강남구','복대동','울릉군']: text=text.replace(r,'지역')
    text=re.sub(r'\s+','',text)
    return {text[i:i+5] for i in range(len(text)-4)}

def preview():
    reports=[render(s) for s in SAMPLES]
    sets={s['key']:grams(OUT/f'preview-high-math-{s["key"]}'/'index.html') for s in SAMPLES}
    similarity={f'{a}/{b}':round(100*len(sets[a]&sets[b])/len(sets[a]|sets[b]),1) for a,b in combinations(sets,2)}
    comparisons={}
    for kind in ['과외','영어과외','수학과외','초등수학과외','초등영어과외','중등수학과외','중등영어과외','고등영어과외']:
        other=grams(OUT/('복대동'+kind)/'index.html'); own=sets['bokdae']
        comparisons[kind]=round(100*len(own&other)/len(own|other),1)
    report=dict(pages=reports,sample_similarity=similarity,bokdae_cross_category=comparisons,method='5-character set Jaccard; whitespace removed, three region labels normalized, head/navigation/contact excluded. Not a Naver ranking or duplication score.')
    (ROOT/'audit/high-math-preview.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

def rollout(apply_output):
    pages=json.loads((ROOT/'intermediate/normalized-pages.json').read_text(encoding='utf-8'))
    targets=[p for p in pages if p['page_type']=='고등수학과외'];reports=[]
    print(f'Targets: {len(targets)}',flush=True)
    for p in targets:
        text=BeautifulSoup(p['body_html'],'html.parser').get_text(' ',strip=True)
        scores=[sum(text.count(w) for w in words) for words in [('함수','그래프','도형'),('서술형','식 세우기','계산'),('조건','개념','연결')]]
        base=next((s for s in SAMPLES if s['region']==p['breadcrumb_label']),SAMPLES[max(range(3),key=lambda i:scores[i])])
        s=deepcopy(base);s['region']=p['breadcrumb_label']
        label=' '.join(dict.fromkeys(filter(None,[p['province'],p['city'],p['locality'],p['breadcrumb_label']])))
        s['title']=label+' 고등수학과외 | '+s['focus']+' – 좋은공부'
        s['lead']=base['lead'].replace(base['region'],label,1)
        reports.append(render(s,p))
        if len(reports)%200==0: print(f'Validated {len(reports)}',flush=True)
    assert len({r['title'] for r in reports})==len(reports)
    assert len({r['description'] for r in reports})==len(reports)
    if apply_output:
        for p in targets:
            backup=ROOT/'backup_output_high_math'/p['slug']/'index.html';backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists(): shutil.copy2(OUT/p['slug']/'index.html',backup)
            shutil.copy2(ROOT/'candidate_output_high_math'/p['slug']/'index.html',OUT/p['slug']/'index.html')
        changed=set(filter(None,subprocess.check_output(['git','diff','HEAD','--name-only','-z','--','output'],cwd=ROOT).decode('utf-8').split('\0')))
        assert changed=={f'output/{p["slug"]}/index.html' for p in targets}
    (ROOT/'audit/high-math-rollout.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(validated=len(reports),applied=apply_output,variants=dict(Counter(r['variant'] for r in reports)),retention=dict(Counter(r['retention'] for r in reports)))))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--all',action='store_true');parser.add_argument('--apply-output',action='store_true');args=parser.parse_args()
    assert not args.apply_output or args.all
    if args.all: rollout(args.apply_output)
    else: preview()
