"""Local-only middle mathematics examples; preserve source explanations."""
import json
import argparse
import shutil
import subprocess
from copy import deepcopy
from collections import Counter
from pathlib import Path
from html import escape as e
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'
PAGES=json.loads((ROOT/'intermediate/normalized-pages.json').read_text(encoding='utf-8'))
SAMPLES=[
dict(region='강남구',key='gangnam',topic='방정식과 풀이의 근거',headline='계산 한 줄에도, 이유가 있어야 합니다.',lead='강남구 중등수학과외는 중1·중2·중3의 학교 진도와 누적된 계산·개념 기초를 함께 살펴봅니다. 문자와 식, 함수, 도형을 공부할 때 답을 구하는 것뿐 아니라 풀이의 각 단계가 왜 가능한지 설명하는 힘을 확인합니다. 아래 방정식은 그 과정을 보여주는 대표 예시입니다.',chain=[('먼저 확인','분배법칙과 동류항 계산'),('오늘 연결','등식의 성질로 방정식 풀기'),('다음 적용','구한 해를 원래 식에 대입')],question='3(x − 2) = 12를 풀고, 각 단계의 이유를 적어보세요.',steps=[('3x − 6 = 12','괄호 안의 두 항에 각각 3을 곱합니다. 분배법칙을 적용한 단계입니다.'),('3x = 18','양변에 6을 더합니다. 등식의 양변에 같은 수를 더해도 등식은 유지됩니다.'),('x = 6','양변을 0이 아닌 같은 수 3으로 나눕니다.'),('3(6 − 2) = 12','구한 해를 원래 식에 넣었을 때 좌변과 우변이 같으므로 확인됩니다.')],change='3(x − 2) = 15로 우변만 바꾸면 무엇이 달라질까요?',result='같은 원리로 3x = 21, x = 7을 얻습니다. 바뀐 답을 외우는 대신 양변에 같은 연산을 한다는 기준이 유지되는지 설명해 봅니다.',review='분배법칙에서 막혔다면 방정식 전체를 반복하기 전에 괄호를 푸는 계산을 보완합니다. 식은 풀었지만 대입 확인을 하지 못한다면 해의 의미와 검산을 연결합니다.'),
dict(region='복대동',key='bokdae',topic='함수의 식과 좌표 연결',headline='식으로 본 관계를, 좌표에서도 읽습니다.',lead='복대동 중등수학과외에서는 문자와 식, 함수, 도형 등 현재 배우는 단원을 연결해 이해하는지 살펴봅니다. 식에 수를 넣어 계산하는 능력과 두 양의 관계를 설명하는 능력은 따로 확인할 수 있습니다. 함수 예시로 식과 좌표 사이를 오가는 과정을 살펴보겠습니다.',chain=[('먼저 확인','문자에 수 대입하기'),('오늘 연결','x와 y의 관계를 순서쌍으로 표현'),('다음 적용','변화량과 절편의 의미 구분')],question='y = 2x + 1에서 x가 0, 1, 2일 때의 좌표와 변화량을 설명해 보세요.',steps=[('x = 0 → y = 1 → (0, 1)','x에 0을 넣습니다. x가 0일 때 y가 1이므로 그래프의 y절편은 1입니다.'),('x = 1 → y = 3 → (1, 3)','좌표는 (x, y)의 순서로 씁니다. x값과 y값의 자리를 바꾸지 않습니다.'),('x = 2 → y = 5 → (2, 5)','x가 1씩 증가할 때 y는 2씩 증가합니다. 이 변화 관계가 기울기 2와 연결됩니다.'),('Δy / Δx = 2 / 1 = 2','서로 다른 두 점의 y변화량을 x변화량으로 나눕니다. y값 3 자체를 기울기라고 부르는 것은 아닙니다.')],change='y = 2x − 3으로 바꾸면 같은 점과 달라진 점은 무엇일까요?',result='기울기는 2로 같고 y절편은 1에서 −3으로 바뀝니다. 같은 x에서 y값은 이전보다 4 작습니다. 예를 들어 x = 1이면 y = −1입니다.',review='대입 계산이 불안하면 부호를 포함한 계산부터 보완합니다. 좌표는 찾지만 관계를 설명하지 못하면 두 점의 변화량을 비교합니다. 어려운 그래프 문제를 추가하기 전에 어느 연결에서 막혔는지 좁힙니다.'),
dict(region='울릉군',key='ulleung',topic='도형 조건과 설명하는 풀이',headline='그림의 모양보다, 주어진 조건을 읽습니다.',lead='울릉군 중등수학과외는 학교 진도와 기초 개념을 함께 살피며 식·함수·도형의 풀이를 설명하는 과정을 다룹니다. 도형에서는 눈에 보이는 모양만으로 길이나 각을 판단하지 않고, 문제에 명시된 조건과 성질을 구분하는 것이 중요합니다. 아래 각도 문제는 그 원칙을 설명하는 예시입니다.',chain=[('먼저 확인','삼각형의 내각의 합'),('오늘 연결','같은 크기인 두 각을 문자로 표현'),('다음 적용','방정식의 해를 도형 조건과 대조')],question='삼각형 ABC에서 ∠A = 40°, ∠B = ∠C입니다. ∠B와 ∠C를 구하고 이유를 설명해 보세요.',steps=[('∠B = ∠C = x°','두 각이 같다는 주어진 조건을 같은 문자 x로 나타냅니다. 그림이 대칭처럼 보인다는 이유로 가정하지 않습니다.'),('40 + x + x = 180','삼각형의 내각의 합이 180°라는 성질을 사용합니다.'),('2x = 140 → x = 70','식을 풀면 두 각은 각각 70°입니다. 140°는 두 각의 합이지 한 각의 크기가 아닙니다.'),('40° + 70° + 70° = 180°','구한 각이 내각의 합과 두 각이 같다는 조건을 모두 만족하는지 확인합니다.')],change='∠A가 50°이고 ∠B = ∠C인 조건은 같다면 어떻게 될까요?',result='50 + 2x = 180이므로 두 각은 각각 65°입니다. ∠A가 10° 커졌을 때 나머지 두 각은 각각 5° 작아집니다. 두 각이 같다는 조건이 없다면 각을 하나씩 확정할 수 없습니다.',review='각의 합을 알면서도 식을 세우지 못하면 주어진 조건을 문자로 표현하는 연습을 합니다. 계산 뒤에는 구한 값이 어떤 각을 뜻하는지 단위와 함께 적습니다. 학교별 출제 방식은 실제 자료를 확인한 범위에서만 다룹니다.'),
]
CSS='''*{box-sizing:border-box}body{margin:0;background:#faf9f5;color:#303c35;font:16px/1.9 "Malgun Gothic",sans-serif}html{scroll-padding-top:24px}a{color:inherit}header{padding:18px max(22px,calc((100vw - 1050px)/2));border-bottom:1px solid #c9d1c9;display:flex;justify-content:space-between;background:white}.brand{font-size:24px;font-weight:bold;text-decoration:none}main{max-width:1050px;margin:auto;padding:25px 28px}.review,.nav,.related{display:flex;gap:20px;flex-wrap:wrap;font-size:14px}.tag{font-size:12px;letter-spacing:1.5px;color:#627361}h1{font-size:44px;line-height:1.4;letter-spacing:-2px;margin:32px 0 10px}.subtitle{font-size:24px}h2{font-size:29px;line-height:1.5}h3{font-size:19px}p{margin:0 0 20px}.image{max-width:800px;margin:30px auto}.image img{display:block;width:100%;height:auto}.intro{padding:35px 0;border-top:4px solid #526e4d;margin-top:35px}.lead{font-size:18px}.nav{padding:18px 0;border-block:1px solid #c9d1c9}.chain{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;margin:28px 0}.chain div{padding:20px;background:#e9eee3;border-top:3px solid #65845b;position:relative}.chain div:not(:last-child):after{content:"→";position:absolute;right:-18px;top:40%}.chain b{display:block;margin-top:10px}.section{padding:35px 0}.problem{font-size:22px;font-weight:bold;background:#354b3b;color:white;padding:25px}.working{background:white;border:1px solid #bdc9bb}.line{display:grid;grid-template-columns:40% 1fr;gap:25px;padding:24px;border-bottom:1px dashed #bdc9bb}.line:last-child{border:0}.formula{font:24px/1.7 Georgia,"Malgun Gothic",sans-serif;overflow-wrap:anywhere}.line p{margin:0;font-size:15px}.change{background:#f1e8d4;padding:30px;border-left:5px solid #a18445;margin:30px 0}.change summary{cursor:pointer;font-weight:bold;padding:12px 0}.change details p{padding-top:18px}.reviewnote{border-left:3px solid #526e4d;padding-left:25px}.source{max-width:820px;margin:20px auto}.source h3{border-top:1px solid #bdc9bb;padding-top:25px}.source ul{padding-left:22px}.small{font-size:13px;color:#5d6b60}.contact{background:#354b3b;color:white;padding:30px}.contact a{display:inline-block;padding:10px 20px;border:1px solid white;margin:5px 15px 5px 0}.related{padding:25px 0}footer{text-align:center;font-size:12px;padding:25px;color:#5d6b60}@media(max-width:700px){main{padding:20px}h1{font-size:33px}.subtitle{font-size:21px}h2{font-size:25px}.chain,.line{grid-template-columns:1fr;gap:14px}.chain div:not(:last-child):after{content:"↓";right:50%;top:auto;bottom:-25px}.chain{gap:25px}.formula{font-size:23px}.line{padding:20px}.problem{font-size:20px}.change{padding:22px}}'''
def render(s,p=None):
    production=p is not None
    p=p or next(p for p in PAGES if p['page_type']=='중등수학과외' and p['breadcrumb_label']==s['region'])
    backup=ROOT/'backup_output_middle_math'/p['slug']/'index.html'
    old=BeautifulSoup((backup if backup.exists() else OUT/p['slug']/'index.html').read_text(encoding='utf-8'),'html.parser')
    content=old.select_one('article .content'); nodes=[]; active=False
    for n in content.find_all(recursive=False):
        if n.name=='h3': active=True
        if active and n.name in ['h3','p','ul']: nodes.append(str(n))
    source=''.join(nodes)
    chain=''.join(f'<div><span class="tag">{e(h)}</span><b>{e(t)}</b></div>' for h,t in s['chain'])
    work=''.join(f'<div class="line"><div class="formula">{e(f)}</div><p>{e(t)}</p></div>' for f,t in s['steps'])
    nav=''.join(f'<a href="/preview-middle-math-{x["key"]}/#start">{x["region"]} 예시</a>' for x in SAMPLES)
    links=''
    for kind in ['수학과외','초등수학과외','고등수학과외']:
        t=next((x for x in PAGES if x['page_type']==kind and all(x.get(k)==p.get(k) for k in ['province','city','locality','breadcrumb_label'])),None)
        if t: links+=f'<a href="/{t["slug"]}/">{e(s["region"])} {kind}</a>'
    html=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{e(s['region'])} 중등수학과외 | {e(s['topic'])} – 좋은공부</title><meta name="description" content="{e(s['lead'])}"><style>{CSS}</style></head><body><header><a class="brand" href="/">좋은공부</a><a href="#consult">중등수학 상담</a></header><main><nav class="review">{nav}<a href="/{p['slug']}/">기존 페이지</a></nav><h1>{e(s['region'])} 중등수학과외</h1><p class="subtitle">{e(s['headline'])}</p><figure class="image"><img src="/assets/images/content/body-common.webp" width="800" height="8000" alt="좋은공부 과외 학습 안내"></figure><section class="intro" id="start"><span class="tag">MIDDLE MATH / 풀이를 설명하는 연습</span><h2>답만 남기지 않고, 개념의 연결을 남깁니다</h2><p class="lead">{e(s['lead'])}</p><p class="small">중등수학 전반을 안내하는 페이지입니다. 예시 단원만 지도한다는 뜻은 아니며, 학생이 배우는 단원과 이해 수준에 맞춰 조정합니다.</p></section><nav class="nav"><a href="#connect">필요한 개념</a><a href="#solution">근거가 있는 풀이</a><a href="#change">조건 바꾸기</a><a href="#original">학습 설명</a></nav><section class="section" id="connect"><span class="tag">CONCEPT CONNECTION</span><h2>지금 풀이에 필요한 개념부터 연결합니다</h2><div class="chain">{chain}</div></section><section class="section" id="solution"><h2>풀이 한 줄, 설명 한 줄</h2><p class="problem">{e(s['question'])}</p><div class="working">{work}</div><p class="small">지도 방법을 설명하기 위해 만든 예시입니다. 실제 학교 시험 문항이나 학생 답안은 아닙니다.</p></section><section class="change" id="change"><span class="tag">TRANSFER / 조건을 바꿔보기</span><h2>같은 기준을 다시 사용할 수 있을까요?</h2><p>{e(s['change'])}</p><details><summary>생각한 뒤 설명 펼치기</summary><p>{e(s['result'])}</p></details></section><section class="section reviewnote"><h2>막힌 단계에 맞춰 복습을 좁힙니다</h2><p>{e(s['review'])}</p></section><section class="section source" id="original"><span class="tag">STUDY FOUNDATION</span><h2>{e(s['region'])} 중등수학 학습의 바탕</h2><p>학교 자료와 최근 풀이 기록을 함께 보며 내신 준비와 누적된 개념 복습을 연결합니다.</p>{source}</section><section class="contact" id="consult"><h2>최근 막힌 풀이와 현재 단원을 알려주세요.</h2><p>학교·학년, 교재, 시험 범위와 풀이 기록을 준비해 주세요. 확인되지 않은 학교별 난도는 단정하지 않습니다. 수업 가능 여부·방식·일정·비용은 문의 시 확인합니다.</p><a href="tel:01049479030">전화 상담</a><a href="sms:01049479030">문자 문의</a></section><nav class="related">{links}</nav></main><footer>중등수학과외 검토용 미리보기 · 미배포</footer></body></html>'''
    doc=BeautifulSoup(html,'html.parser')
    if production:
        doc.select_one('.review').decompose()
        doc.footer.string='좋은공부 · 중등수학 학습 안내'
        head=deepcopy(old.head)
        for n in head.select('link[rel=stylesheet],style,meta[name=robots]'): n.decompose()
        head.append(deepcopy(doc.style))
        head.title.string=s['title']
        head.select_one('meta[name=description]')['content']=s['lead']
        for selector,value in [('meta[property="og:title"]',s['title']),('meta[name="twitter:title"]',s['title']),('meta[property="og:description"]',s['lead']),('meta[name="twitter:description"]',s['lead'])]:
            if head.select_one(selector): head.select_one(selector)['content']=value
        for script in head.select('script[type="application/ld+json"]'):
            data=json.loads(script.string)
            for node in data.get('@graph',[]):
                if node.get('@type')=='WebPage': node.update(name=s['title'],description=s['lead'])
            script.string=json.dumps(data,ensure_ascii=False,separators=(',',':'))
        head.append(doc.new_tag('meta',attrs={'name':'goodstudy-template','content':'middle-math-v1'}))
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
    after=doc.get_text(' ',strip=True)
    assert len(doc.select('h1'))==1
    for a in doc.select('a[href^="#"]'): assert doc.find(id=a['href'][1:])
    for a in doc.select('a[href^="/"]'):
        if not a['href'].startswith('/preview-'): assert (OUT/a['href'].strip('/')).exists()
    assert all(n.get_text(' ',strip=True) in after for n in BeautifulSoup(source,'html.parser').select('p,li'))
    before=[n.get_text(' ',strip=True) for n in content.select('p,li')]
    folder=ROOT/'candidate_output_middle_math'/p['slug'] if production else OUT/f'preview-middle-math-{s["key"]}'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'index.html').write_text(str(doc),encoding='utf-8')
    return {'region':s['region'],'slug':p['slug'],'title':doc.title.string,'description':s['lead'],'variant':s['key'],'original_items':len(before),'retained_items':sum(t in after for t in before)}

def rollout(apply_output):
    targets=[p for p in PAGES if p['page_type']=='중등수학과외']
    reports=[]
    print(f'Targets: {len(targets)}',flush=True)
    for p in targets:
        text=BeautifulSoup(p['body_html'],'html.parser').get_text(' ',strip=True)
        scores=[sum(text.count(w) for w in words) for words in [('계산','방정식','연산'),('함수','좌표','그래프'),('도형','조건','서술형')]]
        base=next((s for s in SAMPLES if s['region']==p['breadcrumb_label']),SAMPLES[max(range(3),key=lambda i:scores[i])])
        s=deepcopy(base); s['region']=p['breadcrumb_label']
        label=' '.join(dict.fromkeys(filter(None,[p['province'],p['city'],p['locality'],p['breadcrumb_label']])))
        s['title']=label+' 중등수학과외 | '+s['topic']+' – 좋은공부'
        s['lead']=base['lead'].replace(base['region'],label,1)
        reports.append(render(s,p))
        if len(reports)%200==0: print(f'Validated {len(reports)}',flush=True)
    assert len({r['title'] for r in reports})==len(reports)
    assert len({r['description'] for r in reports})==len(reports)
    assert all(r['retained_items']>=r['original_items']-1 for r in reports)
    if apply_output:
        for p in targets:
            backup=ROOT/'backup_output_middle_math'/p['slug']/'index.html'
            backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists(): shutil.copy2(OUT/p['slug']/'index.html',backup)
            shutil.copy2(ROOT/'candidate_output_middle_math'/p['slug']/'index.html',OUT/p['slug']/'index.html')
        changed=set(filter(None,subprocess.check_output(['git','diff','HEAD','--name-only','-z','--','output'],cwd=ROOT).decode('utf-8').split('\0')))
        assert changed=={f'output/{p["slug"]}/index.html' for p in targets}
    (ROOT/'audit/middle-math-rollout.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'validated':len(reports),'applied':apply_output,'variants':dict(Counter(r['variant'] for r in reports)),'retention':dict(Counter(f"{r['retained_items']}/{r['original_items']}" for r in reports))}))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--apply-output',action='store_true')
    args=parser.parse_args()
    assert not args.apply_output or args.all
    if args.all: rollout(args.apply_output)
    else: print(json.dumps([render(s) for s in SAMPLES],ensure_ascii=False))
