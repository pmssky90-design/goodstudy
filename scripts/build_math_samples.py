"""Review-only mathematics pages. Existing production pages are read, never written."""
from pathlib import Path
from html import escape as e
import json
import argparse
import shutil
import subprocess
from copy import deepcopy
from collections import Counter
from bs4 import BeautifulSoup
from build_english_samples import CSS, PAGES, OUT

SAMPLES = [
    dict(region='강남구',key='gangnam',topic='오답 원인과 풀이 점검',headline='틀린 답보다, 처음 어긋난 줄을 찾습니다.',
         lead='강남구 수학과외를 알아볼 때는 문제를 얼마나 풀었는지와 함께 어디에서 풀이가 어긋나는지를 살펴보세요. 개념 부족, 조건 해석, 계산 실수를 나누었던 기존 학습 안내를 바탕으로 풀이 기록을 점검합니다.',
         heading='풀이 방향은 맞는데 답이 다르다면?',problem='3 × (4 + 2)를 계산해 보세요.',wrong='3 × 4 + 2 = 14',right='3 × (4 + 2) = 3 × 6 = 18',
         explain='괄호 안을 먼저 계산하는 방법으로 풀어봅니다. 괄호를 풀어 쓰려면 3 × 4 + 3 × 2처럼 두 수에 모두 3을 곱해야 합니다. 처음 풀이에서는 두 번째 수에 곱할 3이 빠졌습니다.',
         checks=[('결과 확인','정답과 다르다는 사실만 표시하지 않고, 원래 식과 달라진 첫 줄을 찾습니다.'),('이유 설명','왜 두 수에 모두 3을 곱해야 하는지 말로 설명해 봅니다. 이유를 설명하지 못하면 단순 계산 실수로만 분류하지 않습니다.'),('다른 수로 확인','2 × (5 + 3)을 같은 방식으로 풀어 16이 되는지 확인합니다. 앞 문제의 답을 기억하는 것과 계산 규칙을 적용하는 것을 구분합니다.')],
         record=['처음 어긋난 줄에 표시하기','적용한 계산 규칙을 한 문장으로 쓰기','수를 바꾼 문제를 해설 없이 다시 풀기'],
         faq=[('계산 실수는 문제를 많이 풀면 줄어드나요?','연산 자체가 어려운지, 부호나 괄호를 옮기는 과정에서 놓치는지 먼저 구분해 보세요. 같은 오류가 반복된다면 문제 수를 늘리기 전에 풀이를 쓰는 방식과 적용한 규칙을 점검하는 것이 좋습니다.'),('맞힌 문제도 다시 확인해야 하나요?','풀이 이유를 설명할 수 있는지 확인해 보세요. 우연히 맞혔거나 풀이를 외워 해결했다면 조건이 바뀐 문제에서 다시 막힐 수 있습니다.')]),
    dict(region='복대동',key='bokdae',topic='조건 해석과 식 세우기',headline='문장의 조건을, 수학의 관계로 바꿉니다.',
         lead='복대동 수학과외에서는 최근 시험지와 평소 풀이 기록을 함께 살펴 학습 출발점을 정할 수 있습니다. 기본 문제는 풀지만 응용 문제에서 멈춘다면, 계산을 시작하기 전에 주어진 조건과 구할 것을 나누어 보세요.',
         heading='공식은 아는데 어떤 식을 써야 할지 막히나요?',problem='한 권에 1,200원인 공책 3권을 사고 5,000원을 냈습니다. 거스름돈은 얼마일까요?',wrong='5,000 − 1,200 = 3,800원',right='5,000 − (1,200 × 3) = 1,400원',
         explain='공책 한 권의 가격과 세 권의 전체 가격을 구분해야 합니다. 먼저 전체 가격 3,600원을 구하고, 낸 돈에서 전체 가격을 빼면 거스름돈 1,400원을 얻습니다. 단위와 수량을 함께 읽는 것이 핵심입니다.',
         checks=[('조건 나누기','한 권의 가격은 1,200원, 개수는 3권, 낸 돈은 5,000원입니다. 문제에 나온 수마다 무엇을 나타내는지 적어봅니다.'),('관계 말하기','“낸 돈에서 산 물건의 전체 가격을 뺀다”라고 먼저 설명합니다. 설명에 필요한 전체 가격을 곱셈으로 구합니다.'),('답 되돌려 보기','전체 가격 3,600원과 거스름돈 1,400원을 더하면 낸 돈 5,000원이 되는지 확인합니다.')],
         record=['주어진 조건과 구할 것을 따로 적기','계산 전에 관계를 문장으로 설명하기','답에 단위를 쓰고 원래 조건에 맞춰 확인하기'],
         faq=[('문장제가 어려우면 독해부터 해야 하나요?','문장의 뜻을 이해하지 못하는지, 뜻은 알지만 수량 관계를 식으로 바꾸지 못하는지 나누어 보세요. 문제를 자신의 말로 설명하게 하면 어느 단계에서 도움이 필요한지 확인하기 쉽습니다.'),('응용 문제는 언제 시작하는 것이 좋을까요?','기본 문제를 맞히는 것뿐 아니라 풀이 이유를 설명할 수 있는지 살펴보세요. 이후 조건 하나를 바꾼 문제부터 적용해 보고, 막히면 어떤 조건이 달라졌는지 비교해 볼 수 있습니다.')]),
    dict(region='울릉군',key='ulleung',topic='개념 이해와 변형 문제',headline='외운 풀이에서, 설명할 수 있는 개념으로.',
         lead='울릉군 수학과외의 출발점은 알고 있는 내용과 문제에 적용하지 못하는 내용을 구분하는 것입니다. 어려운 문제를 앞세우기보다 간단한 예제로 개념을 설명하고, 조건이 달라졌을 때도 같은 기준을 사용할 수 있는지 살펴봅니다.',
         heading='예제는 풀었는데 조건이 바뀌면 막히나요?',problem='가로 4cm, 세로 3cm인 직사각형의 넓이와 둘레를 각각 구해 보세요.',wrong='넓이: 4 + 3 = 7cm²',right='넓이: 4 × 3 = 12cm² / 둘레: 2 × (4 + 3) = 14cm',
         explain='넓이는 안쪽을 채우는 정도이고, 둘레는 테두리의 길이입니다. 1cm²짜리 정사각형을 4개씩 3줄 놓는 모습을 생각하면 곱셈으로 넓이를 구하는 이유를 설명할 수 있습니다. 둘레는 네 변의 길이를 더합니다.',
         checks=[('구할 것 구분','안쪽의 넓이를 묻는지 테두리의 길이를 묻는지 먼저 확인합니다. 넓이의 단위 cm²와 길이의 단위 cm도 구분합니다.'),('공식의 뜻 설명','곱셈식 4 × 3이 무엇을 세는지 그림이나 말로 설명해 봅니다. 공식을 기억하는 것과 뜻을 이해하는 것을 함께 확인합니다.'),('조건 바꾸어 적용','가로만 8cm로 바꾸면 넓이는 24cm², 둘레는 22cm입니다. 한 변이 두 배가 되었다고 둘레까지 두 배가 되는 것은 아니라는 점을 비교합니다.')],
         record=['문제에서 요구한 개념을 먼저 적기','식과 함께 그림 또는 설명 남기기','조건 하나를 바꿔 결과가 어떻게 달라지는지 비교하기'],
         faq=[('기초가 부족하면 진도를 모두 멈춰야 하나요?','현재 공부하는 문제와 연결되는 기초가 무엇인지 먼저 좁혀보세요. 모든 단원을 한꺼번에 다시 하기보다 필요한 개념을 보완하면서 누적 복습 범위를 별도로 정할 수 있습니다.'),('해설을 보면 이해되는데 혼자 못 풀어요.','해설을 닫고 첫 단계부터 다시 시작해 보세요. 어떤 개념을 써야 하는지 선택하지 못하는지, 계산 과정에서 막히는지에 따라 다시 확인할 부분이 달라집니다.')]),
]

EXTRA = '''
:root{--ink:#3c3028;--blue:#985232;--paper:#fcfaf7;--line:#e5ddd2;--muted:#776b61}.workbook{background:#f3ede3;color:var(--ink);border:1px solid #ded0be}.workbook .eyebrow{color:#985232}.math-row{display:grid;grid-template-columns:140px 1fr;gap:20px;padding:20px 0;border-bottom:1px solid #ddcfbd}.math-row strong{font-size:14px}.math-row code{font:24px/1.6 'Malgun Gothic',sans-serif;white-space:normal}.mistake code{color:#975247}.math-question{font-size:22px;font-weight:bold;margin:20px 0}.route a{background:#f0ebe3}.example-label{color:#776b61}.records{padding:25px 30px;border-left:3px solid #985232;background:white}.records li{padding:8px 0}.source-grid{gap:22px}.source-block p:last-child{margin-bottom:0}@media(max-width:760px){.math-row{grid-template-columns:1fr;gap:8px}.math-row code{font-size:21px}.math-question{font-size:20px}}
'''

ROOT=OUT.parent

def eligible(p):
    return p['page_type']=='수학과외' and not p.get('school_name') and not any(w in p['breadcrumb_label'] for w in ['수학','영어','초등','중등','고등'])

def render(s,p=None):
    production=p is not None
    p=p or next(p for p in PAGES if p['page_type']=='수학과외' and p['breadcrumb_label']==s['region'])
    backup=ROOT/'backup_output_math'/p['slug']/'index.html'
    d=BeautifulSoup((backup if production and backup.exists() else OUT/p['slug']/'index.html').read_text(encoding='utf-8'),'html.parser')
    content=d.select_one('article .content')
    intro=[]; groups=[]; active=None
    for n in content.find_all(recursive=False):
        if n.name=='h2': continue
        if n.name=='h3': active=[n.get_text(' ',strip=True),[]]; groups.append(active)
        elif n.name in ['p','ul']:
            (intro if active is None else active[1]).append(str(n))
    # Keep original intro and substantive sections. Replace keyword link lists with real links.
    kept=[g for g in groups if not any(w in g[0] for w in ['연결 페이지','관련 페이지','지역 안에서 비교'])]
    source=''.join('<article class="source-block"><h3>'+e(h)+'</h3>'+''.join(nodes)+'</article>' for h,nodes in kept)
    intro_html=''.join(intro)
    # Only remove the repetitive title phrase, retaining the explanatory remainder.
    title_phrase=p['title'].removeprefix(p['breadcrumb_label']+'수학과외').strip()
    if title_phrase:
        source=source.replace(title_phrase+'과 연결된 계획은','학습 계획은').replace(title_phrase+'을 준비할 때는','학습을 준비할 때는').replace(title_phrase+'을 위해서는','학습 목표를 정할 때는')
    nav=''.join(f'<a href="/preview-math-{x["key"]}/">{x["region"]} 수학과외</a>' for x in SAMPLES)
    nav+=f'<a href="/{p["slug"]}/">수학과외 원본</a><a href="#math-start">이미지 아래 본문 ↓</a>'
    analysis=''.join(f'<article><h3>{e(h)}</h3><p>{e(t)}</p></article>' for h,t in s['checks'])
    records=''.join(f'<li>{e(t)}</li>' for t in s['record'])
    routes=''
    for kind,desc in [('초등수학과외','수 감각·연산 원리·문장제와 도형의 기초'),('중등수학과외','문자와 식·함수·도형, 학교 시험과 서술형'),('고등수학과외','과목별 개념 연결·내신과 수능형 문제·시간 배분')]:
        target=next((x for x in PAGES if x['page_type']==kind and all(x.get(k)==p.get(k) for k in ['province','city','locality','breadcrumb_label'])),None)
        if target: routes+=f'<a href="/{target["slug"]}/"><strong>{kind} →</strong><p>{desc}</p></a>'
    faq=''.join(f'<details><summary>{e(q)}</summary><p>{e(a)}</p></details>' for q,a in s['faq'])
    title=s.get('title',f'{s["region"]} 수학과외 | {s["topic"]} – 좋은공부')
    html=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{e(title)}</title><meta name="description" content="{e(s['lead'])}"><style>{CSS}{EXTRA}</style></head><body>
<header><div class="bar"><a class="brand" href="/">좋은공부 <small>MATH STUDY</small></a><a href="#consult">수학 학습 상담 ↗</a></div></header><main><nav class="review">{nav}</nav>
<div class="crumb">{e(p['province'])} / {e(s['region'])} / 수학 학습 안내</div><section class="hero"><div class="eyebrow">MATHEMATICS / {e(s['topic'])}</div><h1>{e(s['region'])} 수학과외<span>{e(s['headline'])}</span></h1><figure class="original-image"><img src="/assets/images/content/body-common.webp" alt="좋은공부 과외 학습 안내" width="800" height="8000"></figure><p class="lead">{e(s['lead'])}</p></section>
<section class="section" id="math-start"><div class="section-head"><div class="eyebrow">01 / 풀이의 출발점</div><div><h2>수학은 답에 도달하는 과정도 봅니다</h2>{intro_html}</div></div><div class="diagnosis"><a href="#worked"><b>01</b><strong>조건을 식으로 바꾸기 어렵나요?</strong><span>주어진 것과 구할 것을 구분합니다.</span><em>↗</em></a><a href="#worked"><b>02</b><strong>계산 도중 자꾸 실수가 나나요?</strong><span>처음 어긋난 줄과 적용한 규칙을 확인합니다.</span><em>↗</em></a><a href="#record"><b>03</b><strong>해설 없이 다시 시작하기 어렵나요?</strong><span>개념 선택과 재풀이 과정을 기록합니다.</span><em>↗</em></a></div></section>
<section class="section" id="worked"><div class="section-head"><div class="eyebrow">02 / 풀이 비교</div><div><h2>{e(s['heading'])}</h2><p>같은 문제의 두 풀이를 비교하며 어떤 조건이나 규칙을 놓쳤는지 살펴봅니다. 계산 난도보다 풀이를 설명하는 과정에 초점을 맞췄습니다.</p></div></div><div class="workbook"><div class="eyebrow">함께 풀어보는 짧은 문제</div><p class="math-question">{e(s['problem'])}</p><div class="math-row mistake"><strong>어디가 잘못됐을까요?</strong><code>{e(s['wrong'])}</code></div><div class="math-row"><strong>확인한 풀이</strong><code>{e(s['right'])}</code></div><p style="margin-top:22px">{e(s['explain'])}</p><p class="example-label">학습 방법을 설명하기 위해 만든 기초 예제입니다. 실제 학생의 오답이나 특정 학년의 시험 문항이 아닙니다.</p></div><div class="analysis">{analysis}</div></section>
<section class="section" id="record"><div class="section-head"><div class="eyebrow">03 / 내 풀이 기록</div><div><h2>정답을 고친 뒤, 무엇을 남길까요?</h2><p>해설을 옮기는 것으로 끝내지 말고 다음 문제에서 사용할 기준을 남겨보세요. 아래 항목은 학습 기록 예시이며, 학생이 혼자 설명하고 다시 풀 수 있는 범위에 맞춰 조정합니다.</p><ol class="records">{records}</ol></div></div></section>
<section class="section"><div class="section-head"><div class="eyebrow">04 / 수학 학습 연결</div><div><h2>{e(s['region'])} 수학과외를 준비하며 살펴볼 내용</h2><p>최근 시험지, 교과서 예제와 평소 풀이를 함께 살펴 단원별 이해와 복습의 우선순위를 정해 보세요.</p></div></div><div class="source-grid">{source}</div></section>
<section class="section"><div class="section-head"><div class="eyebrow">05 / 학년별 다음 단계</div><div><h2>학년별 단원과 시험 준비는 나누어 봅니다</h2><p>이 페이지는 개념을 설명하고 조건을 식으로 바꾸며 풀이를 점검하는 공통 과정에 집중합니다. 초등·중등·고등의 구체적인 단원과 평가 준비는 각각의 안내에서 살펴보세요.</p></div></div><div class="route">{routes}</div></section>
<section class="section"><div class="section-head"><div class="eyebrow">06 / 수학 공부 질문</div><div><h2>문제 수를 늘리기 전에 궁금한 점</h2>{faq}</div></div></section>
<section class="contact" id="consult"><div><h2>최근 막혔던 풀이 한 장부터 준비하세요.</h2><p>학교·학년, 교재와 어려웠던 단원, 풀이 기록과 가능한 시간을 알려주세요. 수업 가능 지역·학년, 방식과 비용은 문의 시 확인이 필요합니다.</p></div><div><a class="button" href="tel:01049479030">전화 상담</a><a class="button" href="sms:01049479030">문자 문의</a></div></section></main><footer>좋은공부 · GoodStudy / 수학과외 검토용 미리보기 · 미배포</footer><div class="mobile"><a class="button" href="tel:01049479030">전화 상담</a><a class="button" href="sms:01049479030">문자 문의</a></div></body></html>'''
    doc=BeautifulSoup(html,'html.parser')
    if production:
        doc.select_one('.review').decompose()
        doc.footer.string='좋은공부 · GoodStudy / 지역별 수학 학습 안내'
        head=deepcopy(d.head)
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
        head.append(doc.new_tag('meta',attrs={'name':'goodstudy-template','content':'regional-math-v1'}))
        doc.head.replace_with(head)
        links=doc.new_tag('div',attrs={'class':'links'})
        seen={a['href'] for a in doc.select('.route a[href]')}
        seen.add('/'+p['slug']+'/')
        for a in d.select('.related-section a[href]'):
            if a['href'] in seen: continue
            seen.add(a['href'])
            link=doc.new_tag('a',href=a['href']); label=a.select_one('strong') or a
            link.string=label.get_text(' ',strip=True); links.append(link)
        doc.select_one('.route').insert_after(links)
        assert doc.select_one('link[rel=canonical]')['href']==d.select_one('link[rel=canonical]')['href']
        assert doc.select_one('meta[property="og:image"]')['content']==d.select_one('meta[property="og:image"]')['content']
        assert not doc.select_one('meta[name=robots][content*=noindex]')
        assert not doc.select_one('link[rel=stylesheet]')  # Per-page CSS cannot alter other types.
        assert 'preview-math-' not in str(doc)
        html=str(doc)
    assert len(doc.select('h1'))==1
    for a in doc.select('a[href^="#"]'): assert doc.find(id=a['href'][1:])
    for a in doc.select('a[href^="/"]'):
        if '/preview-math-' not in a['href']: assert (OUT/a['href'].strip('/')).exists(),a['href']
    ids=[n['id'] for n in doc.select('[id]')]
    assert len(ids)==len(set(ids))
    assert doc.h1.find_next('img')['src']=='/assets/images/content/body-common.webp'
    assert len(doc.select('.source-block'))>=3,p['slug']
    target=ROOT/'candidate_output_math'/p['slug'] if production else OUT/f'preview-math-{s["key"]}'
    target.mkdir(parents=True,exist_ok=True)
    (target/'index.html').write_text(html,encoding='utf-8')
    before=[n.get_text(' ',strip=True) for n in content.select('p,li')]
    after=doc.get_text(' ',strip=True)
    expected=BeautifulSoup(intro_html+source,'html.parser')
    assert all(n.get_text(' ',strip=True) in after for n in expected.select('p,li'))
    report={'region':s['region'],'slug':p['slug'],'title':title,'original_items':len(before),'exact_retained_items':sum(t in after for t in before),'url':d.select_one('link[rel=canonical]')['href'] if production else f'http://127.0.0.1:8058/preview-math-{s["key"]}/#math-start'}
    if not production: print(json.dumps(report,ensure_ascii=False))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--apply-output',action='store_true')
    args=parser.parse_args()
    assert not args.apply_output or args.all
    if not args.all:
        for sample in SAMPLES: render(sample)
    else:
        targets=[p for p in PAGES if eligible(p)]
        reports=[]
        print(f'Targets: {len(targets)}',flush=True)
        for p in targets:
            s=next((s for s in SAMPLES if s['region']==p['breadcrumb_label']),None)
            if s is None:
                text=BeautifulSoup(p['body_html'],'html.parser').get_text(' ',strip=True)
                scores=[sum(text.count(w) for w in words) for words in [('계산','실수','오답'),('조건','식','응용'),('개념','기초','변형')]]
                base=SAMPLES[max(range(3),key=lambda i:scores[i])]
                s=deepcopy(base); s['region']=p['breadcrumb_label']
                s['lead']=base['lead'].replace(base['region'],s['region'])
                label=' '.join(dict.fromkeys(filter(None,[p['province'],p['city'],p['locality'],p['breadcrumb_label']])))
                s['title']=label+' 수학과외 | '+s['topic']+' – 좋은공부'
            reports.append(render(s,p))
            if len(reports)%200==0: print(f'Validated {len(reports)}/{len(targets)}',flush=True)
        counts=Counter(r['title'] for r in reports)
        assert all(n==1 for n in counts.values()),{t:n for t,n in counts.items() if n>1}
        if args.apply_output:
            for p in targets:
                backup=ROOT/'backup_output_math'/p['slug']/'index.html'
                backup.parent.mkdir(parents=True,exist_ok=True)
                if not backup.exists(): shutil.copy2(OUT/p['slug']/'index.html',backup)
                shutil.copy2(ROOT/'candidate_output_math'/p['slug']/'index.html',OUT/p['slug']/'index.html')
            allowed={f'output/{p["slug"]}/index.html' for p in targets}
            changed=set(filter(None,subprocess.check_output(['git','diff','HEAD','--name-only','-z','--','output'],cwd=ROOT).decode('utf-8').split('\0')))
            assert changed==allowed,(len(changed),len(allowed),changed-allowed)
        (ROOT/'audit').mkdir(exist_ok=True)
        (ROOT/'audit/math-rollout.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'validated':len(reports),'unique_titles':len(counts),'applied':args.apply_output,'other_page_changes':0 if args.apply_output else None}))
