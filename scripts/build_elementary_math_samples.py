"""Three local-only elementary mathematics previews, with an independent layout."""
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
dict(region='강남구',key='gangnam',theme='개념을 설명하는 힘',headline='맞힌 다음, 아이의 설명을 들어보세요.',
lead='강남구 초등수학과외를 알아본다면 정답률과 함께 아이가 개념을 어떤 말로 설명하는지 살펴보세요. 학교에서 배우는 내용과 현재 이해 수준을 연결하고, 어려운 문제를 늘리기 전에 개념을 직접 표현할 기회를 만들어 봅니다.',
notice='분수 계산은 따라 하지만, 분수가 무엇을 나타내는지 물으면 설명을 망설이는 모습',
interpret='계산 방법을 기억하는 것과 전체를 같은 크기로 나눈다는 의미를 이해하는 것은 따로 확인할 수 있습니다. 개념이 익숙하지 않다면 계산 속도를 재기보다 직접 나누고 가리키게 해보세요.',
activity='종이 한 장으로 이야기하는 분수',materials='같은 크기의 종이 두 장, 색연필',
actions=[('접어서 나누기','종이 한 장을 같은 크기의 네 부분으로 접고 한 부분을 색칠합니다. 전체 한 장 중 색칠한 부분을 가리켜 보세요.'),('같은 전체끼리 비교하기','다른 종이는 같은 크기의 두 부분으로 접고 한 부분을 색칠합니다. 같은 크기의 전체에서 1/4과 1/2 중 어느 부분이 더 넓은지 비교합니다.'),('기호의 뜻 말하기','1/4의 4는 전체를 똑같이 나눈 부분의 수, 1은 그중 선택한 부분의 수임을 자신의 말로 설명해 봅니다.')],
ask='“분모가 4니까 2보다 더 큰 분수일까? 색칠한 부분으로 설명해 줄래?”',
reply='“네 조각 중 한 조각보다 두 조각 중 한 조각이 더 커요.”처럼 전체와 부분을 연결해 설명하는지 들어보세요. 표현이 서툴러도 종이에서 정확히 가리킬 수 있는지 함께 봅니다.',
support='답을 바로 알려주기보다 “두 종이의 전체 크기는 같니?”라고 질문해 보세요. 이해했다면 같은 전체를 여덟 부분으로 나누는 경우도 비교할 수 있습니다.',
home=[('살펴볼 모습','분모의 숫자만 보지 않고 전체와 나눈 부분을 함께 가리키는가'),('도움을 줄 때','말로 설명하기 어렵다면 색칠한 종이에서 먼저 찾게 하기'),('다음 확인','종이 없이도 간단한 그림으로 같은 생각을 표현하는가')]),
dict(region='복대동',key='bokdae',theme='문제 읽기와 수량 관계',headline='식을 쓰기 전에, 무슨 이야기인지 먼저.',
lead='복대동 초등수학과외에서는 아이가 문제를 읽는 모습과 풀이를 시작하는 지점을 함께 살펴볼 수 있습니다. 숫자만 보고 계산하는지, 무엇을 구해야 하는지 이해했는지를 나누어 보면 필요한 연습이 더 구체적이 됩니다.',
notice='문제에 나온 숫자를 바로 더하거나 빼지만, 무엇을 구했는지 다시 물으면 답하기 어려워하는 모습',
interpret='문장을 소리 내어 읽었다고 상황까지 이해한 것은 아닐 수 있습니다. 문제를 짧은 이야기로 다시 말하거나 물건을 움직여 표현하게 하면 읽기와 계산 중 어느 부분을 도와야 할지 살펴보기 쉽습니다.',
activity='이야기를 물건으로 옮겨보기',materials='연필 다섯 자루 또는 종이에 그린 연필 그림',
actions=[('상황 듣기','“연필 다섯 자루 중 두 자루를 친구에게 주었어. 남은 연필은 몇 자루일까?”라는 짧은 이야기를 읽어줍니다.'),('직접 움직이기','연필 다섯 자루를 놓고 친구에게 준 두 자루를 따로 옮깁니다. 처음 있던 것, 준 것, 남은 것을 각각 가리키게 합니다.'),('말에서 식으로 옮기기','남은 연필이 세 자루임을 확인한 뒤 5 − 2 = 3으로 적어봅니다. 계산 기호를 먼저 정해주지 않고 왜 빼기를 썼는지 들어봅니다.')],
ask='“이 문제는 친구에게 준 연필을 묻는 걸까, 남은 연필을 묻는 걸까?”',
reply='아이가 마지막 질문을 다시 찾아보게 하세요. “남은 연필을 묻고 있어요”라고 말한 뒤 자신의 답이 그 질문에 맞는지 확인하게 합니다.',
support='문제 전체를 반복해서 읽히기보다 처음 상태, 달라진 상황, 구할 것으로 나누어 대화해 보세요. 익숙해지면 실물 대신 그림으로 상황을 표현하게 할 수 있습니다.',
home=[('살펴볼 모습','계산하기 전에 무엇을 구할지 말할 수 있는가'),('도움을 줄 때','숫자에만 밑줄 긋기보다 각 숫자가 나타내는 대상을 짚기'),('다음 확인','상황은 같고 수만 달라져도 필요한 계산을 선택하는가')]),
dict(region='울릉군',key='ulleung',theme='수 감각과 연산의 이해',headline='손으로 묶어보고, 수의 관계를 발견합니다.',
lead='울릉군 초등수학과외를 준비할 때는 연산 속도만으로 아이의 이해를 판단하지 않는 것이 좋습니다. 수를 세고 묶고 나누는 모습을 통해 계산의 바탕을 살펴보고, 해낼 수 있는 활동부터 학교 학습으로 연결해 봅니다.',
notice='덧셈을 할 때 매번 처음부터 하나씩 세거나, 수가 조금 커지면 계산을 시작하기 어려워하는 모습',
interpret='하나씩 세는 방법도 수를 이해하는 출발점입니다. 이를 틀린 방법으로 다루기보다 묶어서 세는 방법을 함께 경험하게 해보세요. 아이가 이미 할 수 있는 방법에서 새로운 방법으로 이어가는 것이 활동의 목적입니다.',
activity='열 개 묶음을 직접 만들어보기',materials='큰 블록이나 종이 표식 13개, 두 개의 구역을 그린 종이',
actions=[('두 무리 놓기','한쪽에 표식 8개, 다른 쪽에 5개를 놓습니다. 아이가 편한 방법으로 전체 개수를 먼저 확인하게 합니다.'),('열 개로 묶기','5개 중 2개를 옮겨 8개와 합치면 10개가 됩니다. 다른 쪽에 3개가 남았는지 함께 확인합니다.'),('수를 나눈 이유 말하기','8 + 5를 10 + 3으로 볼 수 있음을 이야기합니다. 물건을 옮겨도 전체 개수 13은 변하지 않았다는 점을 살펴봅니다.')],
ask='“두 개를 이쪽으로 옮겼는데, 전체 개수도 바뀌었을까?”',
reply='아이가 다시 세어 확인해도 괜찮습니다. “자리만 옮겨서 똑같아요”라는 생각을 표현하는지 들어보고, 5개가 2개와 3개로 나뉘었다는 것도 짚어보세요.',
support='처음부터 암산으로 답하게 하기보다 표식을 옮길 시간을 주세요. 활동이 익숙해지면 물건 대신 점 그림을 사용하고, 이후 숫자만으로 같은 과정을 표현해 볼 수 있습니다.',
home=[('살펴볼 모습','개수를 빠뜨리지 않고 세고, 옮겨도 전체 수가 같음을 아는가'),('도움을 줄 때','속도를 재촉하지 않고 아이가 사용한 방법을 설명하게 하기'),('다음 확인','다른 두 수에서도 열 개 묶음을 만들 수 있는가')]),
]

CSS='''
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}body{margin:0;background:#fffdf9;color:#373345;font:16px/1.9 'Malgun Gothic',sans-serif}a{color:inherit;text-decoration:none}header{border-bottom:1px solid #e5dfed;background:white}.top,main{max-width:1080px;margin:auto;padding:22px 28px}.top{display:flex;justify-content:space-between;align-items:center}.brand{font-size:24px;font-weight:800}.tag{color:#776289;font-size:12px;letter-spacing:2px}.review{display:flex;gap:18px;flex-wrap:wrap;border-bottom:1px solid #e5dfed;padding:5px 0 20px;font-size:13px}.crumb{font-size:12px;color:#80758c;margin-top:28px}.hero{padding:35px 0}h1{font-size:50px;letter-spacing:-2px;line-height:1.3;margin:15px 0}h1 span{display:block;font-size:25px;font-weight:400;letter-spacing:-.6px;margin-top:18px}.image{max-width:800px;margin:34px auto}.image img{display:block;width:100%;height:auto}.lead{max-width:770px;margin:25px auto;font-size:18px}h2{font-size:30px;line-height:1.5;letter-spacing:-1px;margin:0 0 20px}h3{font-size:19px;margin:0 0 10px}p{margin:0 0 18px}.intro{padding:40px;background:#eee7f4;border-radius:28px 28px 4px 28px;margin:28px 0 45px}.intro strong{font-size:23px;display:block;margin:12px 0 20px;line-height:1.65}.intro p:last-child{margin-bottom:0}.jump{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}.jump a{border:1px solid #d6cae0;border-radius:24px;padding:8px 18px;font-size:14px}.activity{display:grid;grid-template-columns:260px 1fr;gap:42px;padding:35px 0 50px;border-bottom:1px solid #e5dfed}.materials{padding:25px;background:#f5eee1;border-radius:14px;align-self:start}.materials p{font-size:14px}.activity ol{list-style:none;padding:0;margin:25px 0;counter-reset:activity}.activity li{position:relative;padding:0 0 25px 50px;counter-increment:activity}.activity li:before{content:counter(activity);position:absolute;left:0;top:0;background:#79568e;color:white;border-radius:50%;width:31px;height:31px;text-align:center;line-height:31px}.small{font-size:13px;color:#7b7084}.dialogue{padding:50px 0;max-width:820px;margin:auto}.say{margin:25px 0;padding:25px 30px;border-radius:5px 24px 24px 24px;background:#e8eff0;font-size:22px;line-height:1.65}.listen{margin-left:45px;border-left:3px solid #b2a0bd;padding-left:25px}.home{padding:35px;background:#f5f0e8;border-radius:18px}.home dl{margin:0}.home dl div{display:grid;grid-template-columns:150px 1fr;gap:20px;padding:17px 0;border-top:1px solid #ddd2c2}.home dt{font-weight:bold}.home dd{margin:0}.reading{padding:55px 0}.chapter{display:grid;grid-template-columns:230px 1fr;gap:35px;padding:28px 0;border-top:1px solid #e5dfed}.chapter p,.chapter li{font-size:15px}.chapter ul{padding-left:20px}.closing{padding:35px;border:1px solid #d8cde1;border-radius:18px;margin:15px 0 35px}.button{display:inline-block;padding:12px 24px;background:#725182;color:white;border-radius:8px;font-size:14px;margin:5px 8px 0 0}.related{font-size:14px;margin-top:22px}.related a{text-decoration:underline;text-underline-offset:4px;margin-right:18px}footer{text-align:center;padding:28px;color:#80758c;font-size:12px}.mobile{display:none}@media(max-width:760px){.top,main{padding-left:20px;padding-right:20px}.top .tag{display:none}h1{font-size:35px}h1 span{font-size:23px}h2{font-size:25px}.intro{padding:25px}.intro strong{font-size:21px}.activity,.chapter{grid-template-columns:1fr;gap:20px}.materials{padding:20px}.activity{padding-top:20px}.say{padding:22px;font-size:20px}.listen{margin-left:15px;padding-left:20px}.home{padding:24px}.home dl div{grid-template-columns:1fr;gap:5px}.closing{padding:24px}.mobile{display:flex;position:fixed;bottom:0;left:0;right:0;background:white;border-top:1px solid #e5dfed;padding:10px 18px;gap:10px;z-index:4}.mobile a{flex:1;text-align:center;margin:0}footer{padding-bottom:100px}}
'''

def render(s,page=None):
    production=page is not None
    page=page or next(p for p in PAGES if p['page_type']=='초등수학과외' and p['breadcrumb_label']==s['region'])
    backup=ROOT/'backup_output_elementary_math'/page['slug']/'index.html'
    old=BeautifulSoup((backup if production and backup.exists() else OUT/page['slug']/'index.html').read_text(encoding='utf-8'),'html.parser')
    s=deepcopy(s)
    s['lead']=f'{s["region"]} 초등수학과외는 현재 학년과 이해 수준에 맞춰 수와 연산, 도형, 측정 등 학교에서 배우는 내용을 살펴봅니다. '+s['lead']+' 아래 활동은 초등수학 전반의 학습 방법을 보여주는 한 가지 예시이며, 특정 단원만 지도한다는 뜻은 아닙니다.'
    content=old.select_one('article .content')
    groups=[]; active=None
    for n in content.find_all(recursive=False):
        if n.name=='h3': active=[n.get_text(' ',strip=True),[]]; groups.append(active)
        elif active is not None and n.name in ['p','ul']: active[1].append(str(n))
    chapters=''.join(f'<section class="chapter"><h3>{e(h)}</h3><div>{"".join(nodes)}</div></section>' for h,nodes in groups)
    nav=''.join(f'<a href="/preview-elementary-math-{x["key"]}/">{x["region"]} 초등수학</a>' for x in SAMPLES)
    nav+=f'<a href="/{page["slug"]}/">원본 보기</a><a href="#child">이미지 아래 본문 ↓</a>'
    actions=''.join(f'<li><h3>{e(h)}</h3><p>{e(t)}</p></li>' for h,t in s['actions'])
    home=''.join(f'<div><dt>{e(h)}</dt><dd>{e(t)}</dd></div>' for h,t in s['home'])
    related=''
    for kind in ['수학과외','중등수학과외']:
        p=next((p for p in PAGES if p['page_type']==kind and all(p.get(k)==page.get(k) for k in ['province','city','locality','breadcrumb_label'])),None)
        if p: related+=f'<a href="/{p["slug"]}/">{e(s["region"])} {kind} 안내 →</a>'
    label=' '.join(dict.fromkeys(filter(None,[page['province'],page['city'],page['locality'],page['breadcrumb_label']]))) if production else s['region']
    title=f'{label} 초등수학과외 | 교과 개념과 학습 습관 – 좋은공부'
    html=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{e(title)}</title><meta name="description" content="{e(s['lead'])}"><style>{CSS}</style></head><body>
<header><div class="top"><a class="brand" href="/">좋은공부</a><span class="tag">아이의 생각을 듣는 초등 수학</span><a href="#consult">상담 안내 ↗</a></div></header><main><nav class="review">{nav}</nav><div class="crumb">{e(page['province'])} / {e(s['region'])} / 초등 수학</div>
<section class="hero"><div class="tag">ELEMENTARY MATH · {e(s['theme'])}</div><h1>{e(s['region'])} 초등수학과외<span>{e(s['headline'])}</span></h1><figure class="image"><img src="/assets/images/content/body-common.webp" alt="좋은공부 과외 학습 안내" width="800" height="8000"></figure><p class="lead">{e(s['lead'])}</p></section>
<section class="intro" id="child"><div class="tag">아이에게 이런 모습이 보인다면</div><strong>{e(s['notice'])}</strong><p>{e(s['interpret'])}</p><p class="small">하나의 모습만으로 학습 수준을 단정하지 않습니다. 아래 내용은 이해를 살펴보기 위한 안내이며, 활동은 아이가 현재 배우는 내용에 맞춰 선택해 주세요.</p></section>
<nav class="jump"><a href="#activity">함께 해볼 활동</a><a href="#talk">어떻게 물어볼까요?</a><a href="#home">집에서 살펴볼 것</a><a href="#reading">초등수학 학습 안내</a></nav>
<section class="activity" id="activity"><aside class="materials"><div class="tag">시작하기 전에</div><h3>이것만 준비해 주세요</h3><p>{e(s['materials'])}</p><p class="small">어린아이는 작은 물건을 입에 넣지 않도록 보호자가 함께 살펴주세요. 편한 크기의 종이 그림으로 대체해도 됩니다.</p></aside><div><h2>{e(s['activity'])}</h2><p>답을 빨리 내는 활동이 아니라, 아이가 생각을 손과 말로 표현해 보는 활동입니다.</p><ol>{actions}</ol><p class="small">설명을 위해 만든 활동 예시입니다. 실제 학생 사례나 특정 학년의 필수 진도를 뜻하지 않습니다.</p></div></section>
<section class="dialogue" id="talk"><div class="tag">정답을 알려주기 전, 한마디</div><h2>이렇게 물어보고 기다려 보세요</h2><div class="say">{e(s['ask'])}</div><div class="listen"><h3>아이의 말에서 들어볼 부분</h3><p>{e(s['reply'])}</p><h3>설명이 막힐 때 도와주는 방법</h3><p>{e(s['support'])}</p></div></section>
<section class="home" id="home"><h2>문제집을 덮은 뒤에도 볼 수 있는 변화</h2><p>다른 아이와 속도를 비교하기보다, 이전에 도움받던 일을 지금은 어디까지 혼자 하는지 살펴보세요.</p><dl>{home}</dl></section>
<section class="reading" id="reading"><div class="tag">학교 학습과 연결하기</div><h2>{e(s['region'])} 초등수학, 학습의 기준을 세웁니다</h2><p>놀이와 활동에서 확인한 이해를 학교 교과서와 실제 풀이로 연결합니다. 진도와 복습량은 아이가 사용 중인 자료와 최근 기록을 기준으로 조정해 보세요.</p>{chapters}</section>
<section class="closing" id="consult"><h2>아이의 학년과 어려웠던 장면을 알려주세요.</h2><p>학교·학년, 현재 단원, 풀던 교재와 아이가 어려워했던 부분을 준비해 주세요. 선행 정도만 이야기하기보다 읽기·계산·설명 중 어떤 과정에서 도움이 필요한지 함께 정리하면 좋습니다.</p><p class="small">수업 가능 지역·학년, 방문 또는 온라인 운영 여부, 일정과 비용은 상담에서 확인해 주세요.</p><a class="button" href="tel:01049479030">전화 상담</a><a class="button" href="sms:01049479030">문자 문의</a><div class="related">{related}</div></section></main><footer>좋은공부 · 초등수학과외 구성 검토용 미리보기 / 미배포</footer><div class="mobile"><a class="button" href="tel:01049479030">전화 상담</a><a class="button" href="sms:01049479030">문자 문의</a></div></body></html>'''
    doc=BeautifulSoup(html,'html.parser')
    if production:
        doc.select_one('.review').decompose()
        doc.footer.string='좋은공부 · 지역별 초등수학 학습 안내'
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
        head.append(doc.new_tag('meta',attrs={'name':'goodstudy-template','content':'regional-elementary-math-v1'}))
        doc.head.replace_with(head)
        seen={a['href'] for a in doc.select('.related a[href]')}|{'/'+page['slug']+'/'}
        for a in old.select('.related-section a[href]'):
            if a['href'] in seen: continue
            seen.add(a['href'])
            link=doc.new_tag('a',href=a['href']); link.string=(a.select_one('strong') or a).get_text(' ',strip=True)
            doc.select_one('.related').append(link)
        assert doc.select_one('link[rel=canonical]')['href']==old.select_one('link[rel=canonical]')['href']
        assert doc.select_one('meta[property="og:image"]')['content']==old.select_one('meta[property="og:image"]')['content']
        assert not doc.select_one('meta[name=robots][content*=noindex]')
        assert 'preview-' not in str(doc)
    ids=[n['id'] for n in doc.select('[id]')]
    assert len(ids)==len(set(ids))
    assert doc.h1.find_next('img')['src']=='/assets/images/content/body-common.webp'
    assert len(doc.select('h1'))==1
    for a in doc.select('a[href^="#"]'): assert doc.find(id=a['href'][1:])
    for a in doc.select('a[href^="/"]'):
        if not a['href'].startswith('/preview-elementary-math-'): assert (OUT/a['href'].strip('/')).exists(),a['href']
    before=[n.get_text(' ',strip=True) for n in content.select('p,li')]
    after=doc.get_text(' ',strip=True)
    assert all(n.get_text(' ',strip=True) in after for n in BeautifulSoup(chapters,'html.parser').select('p,li'))
    target=ROOT/'candidate_output_elementary_math'/page['slug'] if production else OUT/f'preview-elementary-math-{s["key"]}'
    target.mkdir(parents=True,exist_ok=True)
    (target/'index.html').write_text(str(doc),encoding='utf-8')
    return {'region':s['region'],'slug':page['slug'],'title':title,'original_items':len(before),'retained_items':sum(t in after for t in before)}

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--apply-output',action='store_true')
    args=parser.parse_args()
    assert not args.apply_output or args.all
    if not args.all:
        for sample in SAMPLES: print(render(sample))
    else:
        targets=[p for p in PAGES if p['page_type']=='초등수학과외' and not p.get('school_name') and not any(w in p['breadcrumb_label'] for w in ['수학','영어','초등','중등','고등'])]
        reports=[]
        print(f'Targets: {len(targets)}',flush=True)
        for p in targets:
            original=BeautifulSoup(p['body_html'],'html.parser').get_text(' ',strip=True)
            scores=[sum(original.count(w) for w in words) for words in [('개념','설명','분수'),('문장','읽기','문제'),('연산','수 감각','계산')]]
            base=next((s for s in SAMPLES if s['region']==p['breadcrumb_label']),SAMPLES[max(range(3),key=lambda i:scores[i])])
            s=deepcopy(base); s['region']=p['breadcrumb_label']; s['lead']=base['lead'].replace(base['region'],s['region'])
            reports.append(render(s,p))
            if len(reports)%200==0: print(f'Validated {len(reports)}',flush=True)
        assert len({r['title'] for r in reports})==len(reports)
        if args.apply_output:
            for p in targets:
                backup=ROOT/'backup_output_elementary_math'/p['slug']/'index.html'
                backup.parent.mkdir(parents=True,exist_ok=True)
                if not backup.exists(): shutil.copy2(OUT/p['slug']/'index.html',backup)
                shutil.copy2(ROOT/'candidate_output_elementary_math'/p['slug']/'index.html',OUT/p['slug']/'index.html')
            changed=set(filter(None,subprocess.check_output(['git','diff','HEAD','--name-only','-z','--','output'],cwd=ROOT).decode('utf-8').split('\0')))
            assert changed=={f'output/{p["slug"]}/index.html' for p in targets}
        (ROOT/'audit/elementary-math-rollout.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'validated':len(reports),'applied':args.apply_output,'retention':dict(Counter(f"{r['retained_items']}/{r['original_items']}" for r in reports))}))
