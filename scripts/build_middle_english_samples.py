"""Three unindexed middle-school English previews; original production pages untouched."""
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
dict(region='강남구',key='gangnam',focus='내신 범위와 복습 우선순위',headline='시험 범위를, 오늘 할 공부로 나눕니다.',
lead='강남구 중등영어과외는 중1·중2·중3의 현재 진도와 어휘·문법·독해 기초를 함께 살펴봅니다. 지필평가와 수행평가 준비가 겹칠 때에는 자료를 더 늘리기 전에 학교가 안내한 범위와 제출 조건을 정리하고, 혼자 해결하지 못한 부분부터 복습 순서를 정합니다.',
heading='범위는 확인했는데, 무엇부터 해야 할까요?',
intro='교과서 두 단원과 수업 자료가 범위라는 상황을 가정해 봅니다. 페이지를 모두 읽은 상태와, 문제를 풀고 근거를 설명할 수 있는 상태는 다릅니다. 완료 표시 하나로 묶지 않고 자료마다 남은 일을 적습니다.',
columns=['확인할 자료','현재 상태 예시','다음 할 일'],rows=[('교과서 본문','해석은 되지만 연결어의 역할을 설명하기 어려움','문단 관계를 적고 연결어가 빠졌을 때 뜻이 이어지는지 확인'),('수업 중 받은 자료','풀기는 했으나 틀린 문항을 아직 다시 풀지 않음','해설을 가린 재풀이로 혼자 해결되는지 구분'),('수행평가 안내','주제는 알지만 분량과 제출일을 확인하지 않음','학교가 준 안내에서 작성 조건과 일정을 먼저 정리')],
case_title='진도 표시와 준비 완료는 다릅니다',case='본문을 세 번 읽었다면 다음에는 같은 본문을 한 번 더 읽기보다, 핵심 표현을 가린 뒤 문장 속에서 사용할 수 있는지 확인해 보세요. 잘된 부분을 반복하는 시간과 막힌 부분을 보완하는 시간을 나눌 수 있습니다.',
conditions=['시험 범위는 학교가 제공한 안내를 기준으로 확인합니다.','수행평가 조건은 교과서 진도와 별도로 기록합니다.','시험일과 복습 가능 시간이 다르면 같은 분량을 배정하지 않습니다.'],
phases=[('범위 확인 후','자료 이름과 범위, 제출일을 한곳에 모읍니다. 빠진 자료부터 확인합니다.'),('적용 연습 중','이해했다고 표시한 문법을 새 문장에 적용합니다. 막힌 이유를 어휘·문법·해석으로 나눕니다.'),('시험이 가까워지면','새 문제집을 추가하기 전에 남아 있는 오답과 작성 조건을 확인합니다. 새 자료가 꼭 필요한지는 빈틈의 종류로 판단합니다.')],
handoff='시험 후에는 점수만 남기지 말고, 준비하지 못한 범위와 준비했지만 틀린 범위를 나누어 다음 계획으로 넘깁니다. 고등 영어 준비도 현재의 어휘·문장 구조 이해를 확인한 뒤 이어갑니다.'),
dict(region='복대동',key='bokdae',focus='서술형 조건과 문장 적용',headline='뜻이 맞는 답에서, 조건을 갖춘 답으로.',
lead='복대동 중등영어과외는 어휘·문법·독해를 바탕으로 지필평가와 수행평가를 함께 준비하는 과정을 다룹니다. 특히 문장을 알고도 서술형에서 놓치는 부분이 있다면, 문법 지식뿐 아니라 문제의 작성 조건을 읽고 자신의 답을 점검하는 과정을 살펴봅니다.',
heading='서술형 답안을 쓰기 전에 정리할 세 가지',
intro='외운 문장을 그대로 적을 수 있어도 주어, 시제, 단어 수 같은 조건이 달라지면 답이 달라집니다. 아래는 학교의 실제 문항이나 채점표가 아닌, 답안 점검 방법을 설명하기 위한 제작 예시입니다.',
columns=['확인 항목','이 예시의 조건','답안에서 확인'],rows=[('전달할 의미','그녀는 매일 영어를 공부한다','주어가 그녀이고 반복되는 행동을 나타내는가'),('필수 표현','study, English, every day 사용·필요시 형태 변경','study를 주어에 맞게 studies로 바꾸었는가'),('작성 형식','한 문장의 현재시제 평서문','주어와 동사가 있는 문장으로 쓰고 끝맺었는가')],
case_title='작성 조건을 반영한 한 문장',case='She studies English every day.',
conditions=['She에 맞춰 현재시제 동사를 studies로 씁니다.','every day는 이 문장에서 매일이라는 빈도를 나타냅니다.','예시 답안은 하나이며, 실제 채점과 인정 답안은 학교의 조건에 따릅니다.'],
phases=[('문제를 받았을 때','물어보는 의미와 반드시 써야 할 표현을 먼저 분리해 적습니다. 조건을 놓친 상태에서 문장을 길게 쓰지 않습니다.'),('문장을 완성한 뒤','주어·동사 관계와 시제를 확인한 다음, 문제의 조건을 다시 대조합니다. 뜻이 통한다는 것만으로 점검을 끝내지 않습니다.'),('다음 연습에서는','같은 문장을 반복해서 옮기기보다 주어를 They로 바꿔 They study English every day.처럼 적용합니다. 왜 형태가 달라지는지 설명합니다.')],
handoff='시험 답안이 돌아오면 교사가 표시한 감점 근거를 먼저 확인합니다. 조건 누락과 문법 오류를 구분하고, 같은 원인의 오류가 다음 답안에도 나타나는지 확인합니다. 점수나 감점 폭을 이 예시만으로 예측하지 않습니다.'),
dict(region='울릉군',key='ulleung',focus='독해 근거와 시험 시간 관리',headline='빨리 고르기보다, 근거를 찾는 읽기.',
lead='울릉군 중등영어과외는 학교 진도와 어휘·문법 기초를 연결하면서 내신 독해와 서술형 준비를 함께 살펴봅니다. 읽는 데 시간이 오래 걸린다면 무조건 속도를 재촉하기보다 단어 확인, 문장 해석, 선택지 판단 중 어디에서 시간이 필요한지 구분합니다.',
heading='독해 시간이 오래 걸리는 이유를 나누어 봅니다',
intro='전체 풀이 시간만 기록하면 무엇을 바꿔야 할지 알기 어렵습니다. 짧은 지문에서도 해석을 못한 것인지, 읽은 내용을 질문과 연결하지 못한 것인지 구분하면 복습 방향을 정하기 쉽습니다.',
columns=['멈춘 지점','기록할 내용','연결할 복습'],rows=[('문장 읽기 전','처음 보는 단어 때문에 자주 멈추었는가','뜻만 외우지 않고 문장 속 쓰임과 함께 다시 확인'),('문장 해석 중','주어·동사나 연결어를 놓쳐 되읽었는가','어느 부분까지 이해했고 어디부터 달라졌는지 표시'),('선택지 비교 중','뜻은 알지만 지문 근거를 찾지 못했는가','선택지의 핵심 표현과 대응하는 문장을 대조')],
case_title='지문에 있는 사실과 추측을 분리하기',case='Jin wanted to play soccer, but it rained. He stayed home and read a book.',
conditions=['실제로 한 일은 집에 머물며 책을 읽은 것입니다. 하고 싶었던 축구와 구분합니다.','but 뒤의 내용이 앞의 계획과 어떻게 달라지는지 확인합니다.','축구를 싫어한다거나 혼자 있었다는 정보는 이 지문만으로 알 수 없습니다.'],
phases=[('연습을 시작할 때','정답뿐 아니라 근거 문장도 찾습니다. 해석이 불안한 단계에서는 시간 제한보다 정확한 이해를 먼저 확인합니다.'),('이해가 안정되면','짧은 범위에서 풀이 시간을 함께 기록합니다. 앞서 멈추었던 이유가 줄었는지 살펴봅니다.'),('시험을 준비할 때','학교의 실제 문항 수와 시험 시간을 확인합니다. 임의의 목표 초를 모든 문제에 적용하지 않고, 어려운 문항에 오래 머무는지도 점검합니다.')],
handoff='시험 후에는 찍어서 맞힌 문항도 검토합니다. 근거를 설명하지 못한다면 아직 보완할 부분이 남은 것입니다. 다음에는 같은 소재를 외우는 대신 처음 보는 짧은 지문에도 같은 기준을 적용해 봅니다.'),
]

CSS='''*{box-sizing:border-box}body{margin:0;background:#f5f6fa;color:#22304a;font:16px/1.85 "Malgun Gothic",sans-serif}html{scroll-padding-top:25px}a{color:inherit}header{background:#203354;color:white;padding:18px max(22px,calc((100vw - 1120px)/2));display:flex;justify-content:space-between}header a{text-decoration:none}.brand{font-size:24px;font-weight:bold}main{max-width:1120px;margin:auto;padding:25px 28px}.review{display:flex;gap:20px;flex-wrap:wrap;font-size:13px}h1{font-size:46px;margin:35px 0 10px;line-height:1.4;letter-spacing:-2px}.subtitle{font-size:24px}h2{font-size:29px;line-height:1.5;letter-spacing:-1px}h3{font-size:19px;line-height:1.5}p{margin:0 0 20px}.image{max-width:800px;margin:30px auto}.image img{display:block;width:100%;height:auto}.label{font-size:12px;font-weight:bold;letter-spacing:1.6px;color:#556886}.lead{font-size:18px;max-width:860px}.brief{padding:38px;background:white;border-top:6px solid #33568a;margin:40px 0}.layout{display:grid;grid-template-columns:185px minmax(0,1fr);gap:35px}.index{padding-top:28px}.index a{display:block;padding:14px 0;border-bottom:1px solid #c6d0df;font-size:14px;text-decoration:none}.panel{padding:30px;background:white;margin-bottom:28px}.panel h2{margin-top:8px}.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px;margin:24px 0}th{text-align:left;background:#203354;color:white}th,td{padding:16px;vertical-align:top;border-bottom:1px solid #ccd3df}th:first-child{width:20%}th:nth-child(2){width:38%}.answer{padding:25px;border:1px solid #9aaecb;background:#edf2f9;margin:25px 0}.answer .english{font:25px/1.7 Georgia,serif;color:#203354}.answer ul{padding-left:20px}.small{font-size:13px;color:#5a6b82}.timeline{border-left:3px solid #c3d0e4;margin:25px 0 0 10px;padding-left:25px}.timeline article{position:relative;margin-bottom:28px}.timeline article:before{content:"";width:13px;height:13px;border-radius:50%;background:#426391;position:absolute;left:-33px;top:8px}.timeline h3{margin:0 0 10px}.handoff{background:#fff2d9;border-left:5px solid #b78230;padding:25px;margin:25px 0}.source h3{padding-top:22px;border-top:1px solid #ccd3df}.source ul{padding-left:20px}.contact{padding:32px;background:#203354;color:white}.contact a{display:inline-block;padding:10px 20px;border:1px solid white;margin:5px 12px 5px 0}.related{display:flex;gap:20px;flex-wrap:wrap;padding:25px 0;font-size:14px}footer{text-align:center;padding:25px;font-size:12px;color:#5a6b82}@media(max-width:760px){main{padding:20px}h1{font-size:33px}.subtitle{font-size:21px}.brief,.panel{padding:22px}.layout{grid-template-columns:1fr;gap:20px}.index{display:flex;gap:18px;flex-wrap:wrap;padding-top:0}.index a{padding:8px 0}h2{font-size:24px}table,tbody,tr,td{display:block}thead{display:none}td{padding:12px 0;border:0}td:before{content:attr(data-label);display:block;font-weight:bold;color:#526581;font-size:12px}tr{border-bottom:1px solid #bbc9dc;padding:10px 0}td:first-child{font-size:17px;font-weight:bold}.answer{padding:18px}.answer .english{font-size:23px}}'''

def render(s,p=None):
    production=p is not None
    p=p or next(p for p in PAGES if p['page_type']=='중등영어과외' and p['breadcrumb_label']==s['region'])
    backup=ROOT/'backup_output_middle_english'/p['slug']/'index.html'
    old=BeautifulSoup((backup if backup.exists() else OUT/p['slug']/'index.html').read_text(encoding='utf-8'),'html.parser')
    content=old.select_one('article .content')
    nodes=[]; active=False
    for n in content.find_all(recursive=False):
        if n.name=='h3': active=True
        if active and n.name in ['h3','p','ul']: nodes.append(str(n))
    source=''.join(nodes)
    table='<div class="tablewrap"><table><thead><tr>'+''.join(f'<th scope="col">{e(c)}</th>' for c in s['columns'])+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td data-label="{e(c)}">{e(v)}</td>' for c,v in zip(s['columns'],row))+'</tr>' for row in s['rows'])+'</tbody></table></div>'
    example=f'<div class="answer"><h3>{e(s["case_title"])}</h3><p'+(' class="english" lang="en"' if s['key']!='gangnam' else '')+'>'+e(s['case'])+'</p><ul>'+''.join(f'<li>{e(t)}</li>' for t in s['conditions'])+'</ul></div>'
    timeline=''.join(f'<article><h3>{e(h)}</h3><p>{e(t)}</p></article>' for h,t in s['phases'])
    links=''
    for kind in ['영어과외','초등영어과외','고등영어과외']:
        t=next((x for x in PAGES if x['page_type']==kind and all(x.get(k)==p.get(k) for k in ['province','city','locality','breadcrumb_label'])),None)
        if t: links+=f'<a href="/{t["slug"]}/">{e(s["region"])} {kind}</a>'
    nav=''.join(f'<a href="/preview-middle-english-{x["key"]}/#start">{x["region"]} 예시</a>' for x in SAMPLES)
    title=s.get('title',f'{s["region"]} 중등영어과외 | {s["focus"]} – 좋은공부')
    html=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{e(title)}</title><meta name="description" content="{e(s['lead'])}"><style>{CSS}</style></head><body><header><a class="brand" href="/">좋은공부</a><a href="#consult">중등영어 상담</a></header><main><nav class="review">{nav}<a href="/{p['slug']}/">기존 페이지</a></nav><h1>{e(s['region'])} 중등영어과외</h1><p class="subtitle">{e(s['headline'])}</p><figure class="image"><img src="/assets/images/content/body-common.webp" width="800" height="8000" alt="좋은공부 과외 학습 안내"></figure><section class="brief" id="start"><div class="label">MIDDLE SCHOOL ENGLISH / 학습 준비 문서</div><h2>학교 자료와 내 답안에서 시작합니다</h2><p class="lead">{e(s['lead'])}</p><p class="small">확인되지 않은 학교별 시험 난도·출제 비중은 단정하지 않습니다. 아래 내용은 지도 방법 예시이며 실제 학교 문항이나 성적 향상 사례가 아닙니다.</p></section><div class="layout"><nav class="index"><a href="#scope">준비 항목 정리</a><a href="#sequence">준비 시점별 점검</a><a href="#original">기존 학습 설명</a><a href="#consult">상담 준비</a></nav><div><section class="panel" id="scope"><div class="label">01 / CHECK SHEET</div><h2>{e(s['heading'])}</h2><p>{e(s['intro'])}</p>{table}{example}</section><section class="panel" id="sequence"><div class="label">02 / BEFORE &amp; AFTER</div><h2>준비하는 시점에 따라 확인할 일이 달라집니다</h2><div class="timeline">{timeline}</div><div class="handoff"><h3>시험 이후 다음 계획으로 넘길 것</h3><p>{e(s['handoff'])}</p></div></section><section class="panel source" id="original"><div class="label">03 / STUDY DETAIL</div><h2>{e(s['region'])} 중등영어 학습의 바탕</h2><p>내신 준비와 함께 누적된 어휘·문법·독해 기초를 살펴봅니다. 아래 학습 설명은 현재 학년과 자료, 실제 복습 가능 시간에 맞춰 적용해야 합니다.</p>{source}</section><section class="contact" id="consult"><h2>학교 안내와 최근 답안을 함께 준비해 주세요.</h2><p>학교·학년, 교과서, 시험 범위 또는 과제 안내, 최근 어려웠던 답안을 알려주세요. 수업 가능 여부·방식·일정·비용은 문의 시 확인합니다.</p><a href="tel:01049479030">전화 상담</a><a href="sms:01049479030">문자 문의</a></section><nav class="related">{links}</nav></div></div></main><footer>중등영어과외 검토용 미리보기 · 미배포</footer></body></html>'''
    doc=BeautifulSoup(html,'html.parser')
    if production:
        doc.select_one('.review').decompose()
        doc.footer.string='좋은공부 · 중등영어 학습 안내'
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
        head.append(doc.new_tag('meta',attrs={'name':'goodstudy-template','content':'middle-english-v1'}))
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
    before=[n.get_text(' ',strip=True) for n in content.select('p,li')]
    after=doc.get_text(' ',strip=True)
    assert all(n.get_text(' ',strip=True) in after for n in BeautifulSoup(source,'html.parser').select('p,li'))
    folder=ROOT/'candidate_output_middle_english'/p['slug'] if production else OUT/f'preview-middle-english-{s["key"]}'
    folder.mkdir(parents=True,exist_ok=True); (folder/'index.html').write_text(str(doc),encoding='utf-8')
    return {'region':s['region'],'slug':p['slug'],'title':title,'description':s['lead'],'variant':s['key'],'original_items':len(before),'retained_items':sum(t in after for t in before)}

def rollout(apply_output):
    targets=[p for p in PAGES if p['page_type']=='중등영어과외']
    reports=[]
    print(f'Targets: {len(targets)}',flush=True)
    for p in targets:
        text=BeautifulSoup(p['body_html'],'html.parser').get_text(' ',strip=True)
        scores=[sum(text.count(w) for w in words) for words in [('범위','계획','자료'),('서술형','문법','조건'),('독해','근거','해석')]]
        base=next((s for s in SAMPLES if s['region']==p['breadcrumb_label']),SAMPLES[max(range(3),key=lambda i:scores[i])])
        s=deepcopy(base); s['region']=p['breadcrumb_label']
        label=' '.join(dict.fromkeys(filter(None,[p['province'],p['city'],p['locality'],p['breadcrumb_label']])))
        s['title']=label+' 중등영어과외 | '+s['focus']+' – 좋은공부'
        s['lead']=base['lead'].replace(base['region'],label,1)
        reports.append(render(s,p))
        if len(reports)%200==0: print(f'Validated {len(reports)}',flush=True)
    assert len({r['title'] for r in reports})==len(reports)
    assert len({r['description'] for r in reports})==len(reports)
    assert all(r['retained_items']>=r['original_items']-1 for r in reports)
    if apply_output:
        for p in targets:
            backup=ROOT/'backup_output_middle_english'/p['slug']/'index.html'
            backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists(): shutil.copy2(OUT/p['slug']/'index.html',backup)
            shutil.copy2(ROOT/'candidate_output_middle_english'/p['slug']/'index.html',OUT/p['slug']/'index.html')
        changed=set(filter(None,subprocess.check_output(['git','diff','HEAD','--name-only','-z','--','output'],cwd=ROOT).decode('utf-8').split('\0')))
        assert changed=={f'output/{p["slug"]}/index.html' for p in targets}
    (ROOT/'audit/middle-english-rollout.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'validated':len(reports),'applied':apply_output,'variants':dict(Counter(r['variant'] for r in reports)),'retention':dict(Counter(f"{r['retained_items']}/{r['original_items']}" for r in reports))}))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--apply-output',action='store_true')
    args=parser.parse_args()
    assert not args.apply_output or args.all
    if args.all: rollout(args.apply_output)
    else: print(json.dumps([render(s) for s in SAMPLES],ensure_ascii=False))
