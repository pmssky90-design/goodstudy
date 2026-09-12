"""Three review-only English pages; never modifies production routes."""
import json
import argparse
import shutil
import subprocess
from copy import deepcopy
from collections import Counter
from pathlib import Path
from html import escape as e
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output'
PAGES = json.loads((ROOT / 'intermediate/normalized-pages.json').read_text(encoding='utf-8'))
SAMPLES = [
    dict(region='강남구',key='gangnam',focus='문법을 아는 것에서, 문장을 읽는 것으로.',topic='문장 구조와 문법 적용',
         lead='문법 문제의 정답은 고르지만 문장을 읽거나 쓸 때 다시 막힌다면, 규칙을 외운 양보다 적용하는 과정을 살펴보세요. 강남구 영어과외를 알아보는 학생을 위해 문법과 어휘를 실제 문장에 연결하는 학습 출발점을 정리했습니다.',
         question='규칙은 기억나는데, 새 문장에서는 왜 헷갈릴까요?',
         explanation='문법 용어를 설명할 수 있어도 실제 문장에서 누가 무엇을 하는지 찾는 과정은 별도로 확인해야 합니다. 익숙한 예문을 반복한 뒤에는 주어나 시간 표현을 바꾸어 같은 규칙을 적용할 수 있는지 살펴보세요.',
         sentence='She reads a book every evening.',translation='그녀는 매일 저녁 책을 읽습니다.',
         steps=[('주어와 동작 찾기','She가 주어이고 reads가 동작을 나타냅니다. every evening은 반복되는 시간을 알려줍니다.'),('한 부분만 바꿔보기','주어를 They로 바꾸면 They read a book every evening.이 됩니다. reads와 read의 차이를 문장 안에서 설명해 보세요.'),('내 문장으로 옮기기','자신이 매일 하는 일을 한 문장으로 적고 주어와 동사의 형태를 확인합니다. 번역문을 외우기보다 바뀐 부분의 이유를 말해보는 연습입니다.')],
         routine=[('수업 전','맞혔지만 이유를 설명하기 어려웠던 문장 두 개를 고릅니다.'),('수업에서 확인','원래 문장과 한 요소를 바꾼 문장을 비교합니다.'),('혼자 다시 적용','처음 보는 짧은 문장에서 같은 규칙을 찾아봅니다.')],
         faq=[('문법책을 처음부터 다시 공부해야 할까요?','모든 단원을 다시 시작하기 전에 최근 틀린 문장에서 반복되는 항목을 찾아보세요. 용어를 모르는지, 규칙은 알지만 문장에 적용하지 못하는지에 따라 복습 범위가 달라집니다.'),('문법 문제를 맞히면 독해도 충분한가요?','문법 정답 선택과 글의 의미 이해는 함께 확인해야 합니다. 문장 구조를 설명한 뒤 문단의 핵심 내용을 자신의 말로 정리할 수 있는지도 살펴보세요.')]),
    dict(region='복대동',key='bokdae',focus='문장을 해석한 뒤, 글의 연결을 읽습니다.',topic='문장 해석과 독해 근거',
         lead='단어와 문장을 해석했는데도 글의 내용이 남지 않는다면, 문장 사이의 관계를 확인할 차례입니다. 복대동 영어과외를 알아볼 때 점검할 연결어·지시어와 해석 기록을 중심으로 독해 과정을 살펴봅니다.',
         question='해석은 했는데, 글이 무슨 말인지 남지 않나요?',
         explanation='한 문장씩 번역하는 데 집중하면 앞 문장과 뒤 문장이 어떤 관계인지 놓칠 수 있습니다. 새 단어를 더 외우기 전에, 같은 대상을 가리키는 말과 흐름이 바뀌는 표현을 표시하고 두 문장을 한 문장으로 요약해 보세요.',
         sentence='Mina wanted to walk to school. However, it began to rain, so she took the bus.',translation='미나는 걸어서 학교에 가고 싶었습니다. 하지만 비가 내리기 시작해서 버스를 탔습니다.',
         steps=[('가리키는 대상 연결','she가 앞 문장의 Mina를 가리킨다는 것을 확인합니다. it began to rain의 it은 날씨를 표현할 때 쓰인 말입니다.'),('흐름이 바뀐 이유 찾기','However는 처음 계획과 달라지는 흐름을, so는 비가 내린 상황과 버스를 탄 결과의 연결을 보여줍니다.'),('답의 근거 남기기','“왜 버스를 탔나요?”에 답한 뒤 it began to rain을 근거로 표시합니다. 해석문 전체를 옮기지 않고 필요한 정보만 찾는 연습입니다.')],
         routine=[('읽기 전','모르는 단어와 뜻은 알지만 해석이 끊기는 부분을 다르게 표시합니다.'),('읽는 중','지시어가 가리키는 대상과 연결어 앞뒤 내용을 짝지어 봅니다.'),('읽은 뒤','핵심 내용을 한 문장으로 요약하고 근거 문장을 남깁니다.')],
         faq=[('독해 속도가 느리면 시간을 재며 풀어야 하나요?','먼저 어휘를 찾느라 멈추는지, 문장 구조 때문에 다시 읽는지 구분해 보세요. 짧은 글에서 정확히 이해하는 과정을 확인한 뒤 시간 제한을 조절하는 편이 학습 원인을 파악하기 쉽습니다.'),('해석이 맞는데 문제를 틀리는 이유는 무엇인가요?','질문이 요구하는 정보와 선택지의 범위를 다르게 이해했을 수 있습니다. 자신의 답을 뒷받침하는 문장이 있는지, 선택지에 원문에 없는 내용이 추가되었는지 비교해 보세요.')]),
    dict(region='울릉군',key='ulleung',focus='외운 단어를, 읽고 쓰는 표현으로.',topic='어휘 활용과 문장 이해',
         lead='단어장에서는 기억나지만 지문에서는 낯설게 느껴지는 표현이 있나요? 울릉군 영어과외를 알아보는 학생을 위해 어휘 재사용과 문장 구조를 점검하고, 배운 단어를 실제 문장에 연결하는 방법을 정리했습니다.',
         question='단어 뜻을 외웠는데, 문장에서는 왜 낯설까요?',
         explanation='한 가지 한국어 뜻만 기억하면 문맥이 달라질 때 뜻을 잘못 적용할 수 있습니다. 새로운 단어를 무작정 늘리기보다 짧은 예문에서 어떤 말과 함께 쓰였는지 확인하고, 다른 문장에서도 같은 뜻인지 비교해 보세요.',
         sentence='Please turn on the light. / This bag is light.',translation='불을 켜 주세요. / 이 가방은 가볍습니다.',
         steps=[('같은 단어, 다른 쓰임','첫 문장의 light는 불이나 조명을 가리키고, 두 번째 문장에서는 가방이 가볍다는 상태를 나타냅니다.'),('주변 표현과 함께 기억','turn on the light와 a light bag처럼 함께 쓰이는 표현을 묶어봅니다. 단어 하나의 뜻만 적었던 기록에 짧은 예문을 더할 수 있습니다.'),('다시 사용할 수 있는지 확인','“상자가 가볍다”를 The box is light.로 써보고, 어떤 뜻으로 썼는지 말해봅니다. 철자를 기억하는 것과 문맥에 맞게 사용하는 것을 나누어 확인합니다.')],
         routine=[('단어 기록','뜻만 적지 않고 단어가 등장한 짧은 문장을 함께 남깁니다.'),('다시 읽기','뜻을 가린 상태에서 문맥에 맞는 의미를 설명해 봅니다.'),('새 문장 쓰기','배운 표현의 대상을 바꾸어 짧게 쓰고 어순·철자를 점검합니다.')],
         faq=[('단어를 하루에 몇 개씩 외워야 하나요?','정해진 숫자보다 이전에 배운 표현을 얼마나 기억하고 활용하는지 먼저 보세요. 새 단어를 배우는 시간과 기존 단어를 문장에서 다시 확인하는 시간을 함께 고려해 분량을 정하는 것이 좋습니다.'),('단어만 더 외우면 해석이 나아질까요?','어휘 부족이 원인일 수도 있지만 단어 사이의 관계를 놓치는 경우도 있습니다. 아는 단어로 이루어진 문장에서도 막힌다면 주어·동사와 수식하는 부분을 함께 살펴보세요.')]),
]

CSS = '''
:root{--ink:#182d49;--muted:#66758a;--line:#dbe2ec;--blue:#254e83;--paper:#fafbfd;--gold:#f0dcac}*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.85 'Malgun Gothic',sans-serif}a{color:inherit;text-decoration:none}header{border-bottom:1px solid var(--line);background:white}.bar,main{max-width:1120px;margin:auto;padding:20px 28px}.bar{display:flex;justify-content:space-between;align-items:center}.brand{font-size:23px;font-weight:800}.brand small{font-size:11px;letter-spacing:2px;margin-left:14px;color:var(--muted)}.review{display:flex;gap:18px;flex-wrap:wrap;font-size:13px;border-bottom:1px solid var(--line);padding:10px 0 22px}.crumb{font-size:12px;color:var(--muted);margin-top:30px}.eyebrow{font-size:12px;letter-spacing:2px;font-weight:bold;color:var(--blue)}h1{font-size:58px;line-height:1.2;letter-spacing:-2px;margin:20px 0}h1 span{display:block;font-size:26px;font-weight:400;letter-spacing:-1px;margin-top:18px}h2{font-size:30px;line-height:1.45;letter-spacing:-1px;margin:0 0 18px}h3{font-size:19px;line-height:1.5;margin:0 0 12px}p{margin:0 0 18px}.hero{padding:34px 0}.original-image{max-width:800px;margin:32px auto}.original-image img{width:100%;height:auto;display:block}.lead{max-width:800px;margin:28px auto;font-size:18px}.section{padding:50px 0;border-bottom:1px solid var(--line)}.section-head{display:grid;grid-template-columns:210px 1fr;gap:30px}.section-head .eyebrow{padding-top:8px}.diagnosis{margin-top:28px}.diagnosis a{display:grid;grid-template-columns:46px 1.15fr 1fr 20px;gap:20px;align-items:center;padding:23px 4px;border-top:1px solid var(--line)}.diagnosis a:hover{background:#edf2f9}.diagnosis span{font-size:14px;color:var(--muted)}.workbook{background:var(--ink);color:white;padding:38px;border-radius:4px;margin:26px 0}.workbook .eyebrow{color:var(--gold)}.english{font:26px/1.7 Georgia,serif;margin:20px 0}.translation{color:#c6d5e8;font-size:14px}.example-label{font-size:12px;color:#c6d5e8}.analysis{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}.analysis article{border-top:3px solid #b99752;padding:20px 0}.analysis p{font-size:15px}.source-grid{display:grid;grid-template-columns:1fr 1fr;gap:32px;margin-top:26px}.source-block{padding:26px;background:white;border:1px solid var(--line)}.source-block p,.source-block li{font-size:15px}.source-block ul{padding-left:20px}.quote{border-left:3px solid #b99752;padding:15px 22px;margin:22px 0;background:#f6f0e5}.routine{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin-top:28px;border:1px solid var(--line)}.routine article{padding:26px;border-right:1px solid var(--line)}.routine article:last-child{border:0}.routine b{display:block;color:#9a7634;font-size:13px;margin-bottom:15px}.route{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:26px}.route a{padding:22px;background:#edf2f9}.route strong{display:block;margin-bottom:10px}.route p{font-size:14px;margin:0}.links{display:flex;flex-wrap:wrap;gap:12px;font-size:14px;margin-top:18px}.links a{text-decoration:underline;text-underline-offset:4px}details{padding:20px 0;border-bottom:1px solid var(--line)}summary{font-weight:bold;cursor:pointer}details p{padding-top:15px;max-width:820px}.contact{display:flex;justify-content:space-between;gap:30px;align-items:center;padding:40px 0 60px}.contact p{font-size:14px;max-width:600px}.button{display:inline-block;background:var(--blue);color:white;padding:13px 23px;border-radius:4px;margin:5px 8px 5px 0;font-size:14px;white-space:nowrap}footer{border-top:1px solid var(--line);padding:25px;text-align:center;font-size:12px;color:var(--muted)}.small{font-size:13px;color:var(--muted)}.mobile{display:none}@media(max-width:760px){.bar,main{padding-left:22px;padding-right:22px}.brand small{display:none}h1{font-size:40px}h1 span{font-size:23px}.section-head{grid-template-columns:1fr;gap:10px}.source-grid,.analysis,.routine,.route{grid-template-columns:1fr}.diagnosis a{grid-template-columns:28px 1fr 18px;gap:10px}.diagnosis a span{grid-column:2;grid-row:2}.diagnosis a em{grid-column:3;grid-row:1}.workbook{padding:24px}.english{font-size:23px}.routine article{border-right:0;border-bottom:1px solid var(--line)}.contact{display:block}.section{padding:34px 0}h2{font-size:26px}.mobile{display:flex;position:fixed;bottom:0;background:white;border-top:1px solid var(--line);width:100%;padding:10px 18px;gap:10px;z-index:4}.mobile a{flex:1;text-align:center;margin:0}footer{padding-bottom:100px}}
'''

def eligible(p):
    return p['page_type']=='영어과외' and not p.get('school_name') and not any(w in p['breadcrumb_label'] for w in ['수학','영어','초등','중등','고등'])

def render(s, page=None):
    production = page is not None
    page = page or next(p for p in PAGES if p['page_type']=='영어과외' and p['breadcrumb_label']==s['region'])
    backup=ROOT/'backup_output_english'/page['slug']/'index.html'
    original = BeautifulSoup((backup if production and backup.exists() else OUT/page['slug']/'index.html').read_text(encoding='utf-8'),'html.parser')
    content = original.select_one('article .content')
    # Keep original explanatory paragraphs and lists, omit only duplicate headings/navigation.
    blocks, current = [], None
    intro = []
    for node in content.find_all(recursive=False):
        if node.name == 'h2': continue
        if node.name == 'h3':
            current = [node.get_text(' ',strip=True),[]]; blocks.append(current)
        elif node.name in ['p','ul','blockquote']:
            if current is None: intro.append(str(node))
            elif node.name == 'blockquote': pass
            else: current[1].append(str(node))
    source = ''.join('<article class="source-block"><h3>'+e(h)+'</h3>'+''.join(nodes)+'</article>' for h,nodes in blocks if nodes and not any(x in h for x in ['학교 영어과외','관련 페이지']))
    titles = {'gangnam':'강남구 영어과외 | 문장 구조와 문법 적용 – 좋은공부','bokdae':'청주 복대동 영어과외 | 해석과 독해 근거 – 좋은공부','ulleung':'울릉군 영어과외 | 어휘 활용과 문장 이해 – 좋은공부'}
    nav = ''.join(f'<a href="/preview-english-{x["key"]}/">{x["region"]} 영어과외</a>' for x in SAMPLES)
    nav += f'<a href="/{page["slug"]}/">영어과외 원본</a><a href="/{s["region"]}과외/">일반 과외와 비교</a><a href="#english-start">이미지 아래 본문 ↓</a>'
    steps=''.join(f'<article><h3>{e(h)}</h3><p>{e(p)}</p></article>' for h,p in s['steps'])
    routine=''.join(f'<article><b>0{i+1}</b><h3>{e(h)}</h3><p>{e(p)}</p></article>' for i,(h,p) in enumerate(s['routine']))
    route=''
    for kind, desc in [('초등영어과외','소리와 철자, 읽기 시작과 짧은 표현 사용'),('중등영어과외','학교 교과서, 기본 문법과 서술형·수행평가'),('고등영어과외','내신 지문, 모의고사 독해와 학습 시간 배분')]:
        target=next((p for p in PAGES if p['page_type']==kind and all(p.get(k)==page.get(k) for k in ['province','city','locality','breadcrumb_label'])),None)
        if target: route+=f'<a href="/{target["slug"]}/"><strong>{kind} →</strong><p>{desc}</p></a>'
    related=''
    for a in original.select('.related-section a[href]'):
        label=a.select_one('strong') or a
        if a['href']=='/'+page['slug']+'/' or any(k in label.get_text() for k in ['초등','중등','고등']): continue
        if '영어' in label.get_text() and (OUT/a['href'].strip('/')/'index.html').exists():
            related+=f'<a href="{e(a["href"])}">{e(label.get_text(" ",strip=True))}</a>'
    faq=''.join(f'<details><summary>{e(q)}</summary><p>{e(a)}</p></details>' for q,a in s['faq'])
    location=' '.join(dict.fromkeys(filter(None,[page['province'],page['city'],page['locality']])))
    html=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{e(titles[s['key']])}</title><meta name="description" content="{e(s['lead'])}"><style>{CSS}</style></head><body>
<header><div class="bar"><a class="brand" href="/">좋은공부 <small>ENGLISH STUDY</small></a><a href="#consult">영어 학습 상담 ↗</a></div></header><main>
<nav class="review" aria-label="미리보기 비교">{nav}</nav><div class="crumb">{e(location)} / 영어 학습 안내</div>
<section class="hero"><div class="eyebrow">ENGLISH / {e(s['topic'])}</div><h1>{e(s['region'])} 영어과외<span>{e(s['focus'])}</span></h1>
<figure class="original-image"><img src="/assets/images/content/body-common.webp" alt="좋은공부 과외 학습 안내" width="800" height="8000"></figure>
<p class="lead">{e(s['lead'])}</p></section>
<section class="section" id="english-start"><div class="section-head"><div class="eyebrow">01 / LEARNING CHECK</div><div><h2>영어에서 막히는 지점부터 찾습니다</h2><p>같은 오답이라도 필요한 연습은 다릅니다. 최근 공부한 문장 한두 개로 어휘, 문장 구조, 글의 연결 중 무엇이 어려운지 구분해 보세요.</p></div></div>
<div class="diagnosis"><a href="#practice"><b>A</b><strong>단어는 아는데 문장이 안 읽혀요</strong><span>주어·동사와 수식 관계를 확인합니다.</span><em>↗</em></a><a href="#practice"><b>B</b><strong>해석했지만 답의 근거를 못 찾겠어요</strong><span>연결어와 질문이 요구하는 정보를 봅니다.</span><em>↗</em></a><a href="#routine"><b>C</b><strong>외웠던 표현을 다시 잊어요</strong><span>새 문장에 재사용하는 과정을 남깁니다.</span><em>↗</em></a></div></section>
<section class="section" id="practice"><div class="section-head"><div class="eyebrow">02 / ENGLISH NOTE</div><div><h2>{e(s['question'])}</h2><p>{e(s['explanation'])}</p></div></div><div class="workbook"><div class="eyebrow">직접 살펴보는 짧은 영어</div><p class="english" lang="en">{e(s['sentence'])}</p><p class="translation">{e(s['translation'])}</p><div class="example-label">학습 방법을 설명하기 위한 제작 예문입니다. 실제 학생 사례나 특정 학년의 시험 문항이 아닙니다.</div></div><div class="analysis">{steps}</div></section>
<section class="section" id="original"><div class="section-head"><div class="eyebrow">03 / STUDY DETAIL</div><div><h2>{e(s['region'])} 영어 학습, 이렇게 연결해 보세요</h2><p>어휘를 문장에서 사용하고, 문법을 해석에 적용하고, 답의 근거를 남기는 과정을 함께 살펴봅니다. 시험 자료와 학습 분량은 학생의 현재 수준에 맞춰 조정해야 합니다.</p></div></div><div class="source-grid">{source}</div></section>
<section class="section" id="routine"><div class="section-head"><div class="eyebrow">04 / PRACTICE RECORD</div><div><h2>배운 영어를 혼자 사용할 수 있도록</h2><p>완료한 문제 수뿐 아니라, 다시 읽고 설명하고 써본 내용을 남겨보세요. 아래는 학습 기록 예시이며 실제 수업 운영 방식은 상담에서 확인해 주세요.</p></div></div><div class="routine">{routine}</div></section>
<section class="section" id="levels"><div class="section-head"><div class="eyebrow">05 / NEXT COURSE</div><div><h2>학년별 목표는 별도로 살펴봅니다</h2><p>이 페이지에서는 영어 영역 사이의 연결을 다룹니다. 학년별 교과 내용과 시험 준비는 아래 안내에서 구체적으로 확인할 수 있습니다.</p></div></div><div class="route">{route}</div><div class="links">{related}</div></section>
<section class="section"><div class="section-head"><div class="eyebrow">06 / QUESTIONS</div><div><h2>영어 공부에서 자주 생기는 질문</h2>{faq}</div></div></section>
<section class="contact" id="consult"><div><h2>어려웠던 영어 문장부터 알려주세요.</h2><p>학교·학년, 사용 중인 영어 교재와 최근 막혔던 문장, 가능한 시간을 정리해 주세요. 지도 가능 학년·지역, 수업 방식과 비용은 문의 시 확인이 필요합니다.</p></div><div><a class="button" href="tel:01049479030">전화 상담</a><a class="button" href="sms:01049479030">문자로 문의</a></div></section>
</main><footer>좋은공부 · GoodStudy / 영어과외 구성 검토용 미리보기 · 미배포</footer><div class="mobile"><a class="button" href="tel:01049479030">전화 상담</a><a class="button" href="sms:01049479030">문자 문의</a></div></body></html>'''
    doc=BeautifulSoup(html,'html.parser')
    if production:
        doc.select_one('.review').decompose()
        doc.footer.string='좋은공부 · GoodStudy / 지역별 영어 학습 안내'
        title=s.get('title',titles[s['key']])
        head=deepcopy(original.head)
        for n in head.select('link[rel=stylesheet], style, meta[name=robots]'): n.decompose()
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
        head.append(doc.new_tag('meta',attrs={'name':'goodstudy-template','content':'regional-english-v1'}))
        doc.head.replace_with(head)
        assert doc.select_one('link[rel=canonical]')['href']==original.select_one('link[rel=canonical]')['href']
        assert doc.select_one('meta[property="og:image"]')['content']==original.select_one('meta[property="og:image"]')['content']
        assert not doc.select_one('meta[name=robots][content*=noindex]')
        assert not doc.select_one('.review')
        assert '미배포' not in doc.get_text()
        html=str(doc)
    assert len(doc.select('h1'))==1
    for a in doc.select('a[href^="#"]'): assert doc.find(id=a['href'][1:])
    for a in doc.select('a[href^="/"]'):
        if 'preview-english-' not in a['href']: assert (OUT/a['href'].strip('/')).exists(),a['href']
    target=ROOT/'candidate_output_english'/page['slug'] if production else OUT/f'preview-english-{s["key"]}'
    target.mkdir(parents=True,exist_ok=True)
    (target/'index.html').write_text(html,encoding='utf-8')
    before=[n.get_text(' ',strip=True) for n in content.select('p,li')]
    after=doc.get_text(' ',strip=True)
    report={'region':s['region'],'slug':page['slug'],'title':doc.title.text,'original_items':len(before),'retained_items':sum(t in after for t in before),'url':original.select_one('link[rel=canonical]')['href'] if production else f'http://127.0.0.1:8058/preview-english-{s["key"]}/#english-start'}
    # All non-intro explanation paragraphs and list items selected for reuse survive unchanged.
    expected=BeautifulSoup(source,'html.parser')
    assert all(n.get_text(' ',strip=True) in after for n in expected.select('p,li'))
    assert len(doc.select('.source-block')) >= 3, page['slug']
    assert doc.h1.find_next('img')['src']=='/assets/images/content/body-common.webp'
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
        for page in targets:
            sample=next((s for s in SAMPLES if s['region']==page['breadcrumb_label']),None)
            if sample is None:
                body=BeautifulSoup(page['body_html'],'html.parser').get_text(' ',strip=True)
                scores=[sum(body.count(t) for t in terms) for terms in [('문법','주어','동사'),('독해','근거','지시어','연결어'),('어휘','단어')]]
                base=SAMPLES[max(range(3),key=lambda i:scores[i])]
                sample=deepcopy(base)
                sample['region']=page['breadcrumb_label']
                sample['lead']=base['lead'].replace(base['region'],sample['region'])
                label=' '.join(dict.fromkeys(filter(None,[page['province'],page['city'],page['locality'],page['breadcrumb_label']])))
                sample['title']=label+' 영어과외 | '+base['topic']+' – 좋은공부'
            reports.append(render(sample,page))
            if len(reports)%200==0: print(f'Validated {len(reports)}/{len(targets)}',flush=True)
        titles=Counter(r['title'] for r in reports)
        assert all(n==1 for n in titles.values()),{t:n for t,n in titles.items() if n>1}
        if args.apply_output:
            for page in targets:
                backup=ROOT/'backup_output_english'/page['slug']/'index.html'
                backup.parent.mkdir(parents=True,exist_ok=True)
                if not backup.exists(): shutil.copy2(OUT/page['slug']/'index.html',backup)
                shutil.copy2(ROOT/'candidate_output_english'/page['slug']/'index.html',OUT/page['slug']/'index.html')
            allowed={f'output/{p["slug"]}/index.html' for p in targets}
            changed=set(filter(None,subprocess.check_output(['git','diff','HEAD','--name-only','-z','--','output'],cwd=ROOT).decode('utf-8').split('\0')))
            assert changed==allowed,(len(changed),len(allowed),changed-allowed)
        (ROOT/'audit').mkdir(exist_ok=True)
        (ROOT/'audit/english-rollout.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'validated':len(reports),'unique_titles':len(titles),'applied':args.apply_output,'other_page_changes':0 if args.apply_output else None}))
