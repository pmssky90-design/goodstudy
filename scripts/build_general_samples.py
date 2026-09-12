"""Build three review-only general tutoring pages from existing production text."""
import json
import re
import argparse
import shutil
from collections import Counter
from pathlib import Path
from copy import deepcopy
from difflib import SequenceMatcher
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output'
BASE = (ROOT / 'templates/general-approved.html').read_text(encoding='utf-8')
PAGES = json.loads((ROOT / 'intermediate/normalized-pages.json').read_text(encoding='utf-8'))
SAMPLES = [
    ('강남구과외', 'gangnam', '강남구 과외 | 학년별 학습과 내신 대비 – 좋은공부', '학교 진도와 개인의 약점을 함께 살펴봅니다.', '학교 진도와 개인의 약점, 과제와 피드백을 함께 확인하는 강남구 과외 학습 안내입니다. 초등·중등·고등의 학습 기준과 수학·영어 점검 내용을 살펴보세요.'),
    ('복대동과외', 'bokdae', '청주 복대동 과외 | 오답 점검과 학년별 학습 – 좋은공부', '복습이 막히는 지점부터 살펴봅니다.', '청주 복대동 과외를 알아볼 때 필요한 오답 점검, 수학·영어 학습과 학년별 관리 기준을 정리했습니다. 최근 시험지와 학교 일정을 바탕으로 공부 방향을 확인해 보세요.'),
    ('울릉군과외', 'ulleung', '울릉군 과외 | 학습 점검과 수업 상담 안내 – 좋은공부', '아이의 현재 공부에서 시작합니다.', '울릉군 과외를 알아보는 학생과 학부모를 위한 학습 안내입니다. 질문과 오답, 학년별 공부 방향을 살피고 통학·복습 시간과 수업 조건을 함께 확인해 보세요.'),
]
SUPPLEMENTS = {
    'gangnam': [
        ('수업을 늘리기 전에, 필요한 역할부터 정해 보세요', [
            ('학원 진도와 개인별 보완을 구분하기', '강남구 과외를 알아보면서 기존 학원 수업도 유지할 계획이라면, 먼저 두 수업의 역할을 정리해 보세요. 학원에서 진도를 배우고 있다면 과외에서는 설명을 놓친 부분이나 혼자 풀지 못한 문제를 확인하는 방식으로 상담할 수 있습니다. 같은 교재를 반복하는 것 자체보다, 반복한 뒤 학생이 무엇을 할 수 있게 되는지가 중요합니다.'),
            ('시간이 부족한지, 이해가 막히는지 살피기', '숙제가 밀린다고 해서 바로 수업 시간을 추가하기보다는 일주일 동안 과제에 쓴 시간과 막힌 문제를 적어보세요. 시작할 시간이 없었던 경우와 풀이 방법을 몰라 멈춘 경우는 필요한 도움이 다릅니다. 이 기록을 가져가면 진도 보충, 질문 해결, 학습 일정 조정 중 무엇을 먼저 할지 이야기하기 쉽습니다.')]),
        ('선생님을 선택할 때 물어볼 세 가지', [
            ('“이해했는지는 어떻게 확인하나요?”', '설명 후 고개를 끄덕이는 것과 혼자 해결하는 것은 다를 수 있습니다. 비슷한 문제를 직접 풀어보게 하는지, 학생의 말로 풀이 이유를 설명하게 하는지 확인해 보세요.'),
            ('“과제가 어려웠을 때는 어떻게 진행하나요?”', '과제를 못 한 이유가 분량인지, 개념 이해인지, 일정 문제인지 함께 살피는지 질문해 보세요. 과제 양뿐 아니라 피드백 방법까지 확인하면 학생에게 맞는 수업을 선택하는 데 도움이 됩니다.'),
            ('“수업 후에는 무엇을 공유하나요?”', '진도만 전달하는지, 어려웠던 부분과 다음 복습 범위까지 안내하는지 물어보세요. 연락 방식과 주기는 실제 상담에서 확인하고, 학생이 스스로 정리할 부분도 함께 정하면 좋습니다.')])],
    'bokdae': [
        ('숙제는 했는데 같은 실수가 반복된다면', [
            ('채점 결과보다 틀린 이유를 남기기', '복대동 과외를 알아볼 때 최근 문제집에서 반복해서 틀린 문제 몇 개를 골라보세요. 개념을 몰랐는지, 조건을 놓쳤는지, 풀이를 끝내지 못했는지 학생의 말로 적어보는 것입니다. 정답을 옮겨 적은 오답 노트보다 어디에서 막혔는지 드러나는 기록이 수업 상담에 도움이 됩니다.'),
            ('해설을 닫고 다시 풀어보기', '해설을 읽을 때 이해가 되더라도 스스로 풀이를 시작하기는 어려울 수 있습니다. 다시 풀 때 첫 단계부터 막힌다면 그 부분을 표시해 질문으로 남겨보세요. 재풀이에서도 같은 실수가 나오는 문제는 많은 문제를 추가하기 전에 설명과 연습이 더 필요한 부분으로 볼 수 있습니다.')]),
        ('수업을 시작한 뒤 살펴볼 변화', [
            ('점수와 함께 풀이의 변화를 보기', '시험 점수만으로 매 수업을 판단하기보다 이전에 도움받았던 문제를 혼자 풀 수 있는지 살펴보세요. 답을 맞혔더라도 이유를 설명하지 못한다면 다음 수업에서 확인할 질문으로 남길 수 있습니다. 변화가 더딜 때는 학생을 재촉하기보다 목표와 과제 난도를 함께 점검해 보세요.'),
            ('짧은 복습 기록으로 다음 수업 연결하기', '복습한 날짜, 혼자 해결한 부분, 다시 물어볼 내용을 간단히 남겨보세요. 기록을 길게 꾸미는 것보다 실제로 풀어보고 남기는 것이 중요합니다. 학부모는 정답을 대신 알려주기보다 “어느 부분까지는 혼자 했니?”라고 물어 학생이 막힌 지점을 표현하도록 도울 수 있습니다.')])],
    'ulleung': [
        ('질문을 어려워하는 학생의 첫 수업 준비', [
            ('“모르겠어요”를 구체적인 질문으로 바꾸기', '울릉군 과외 상담을 준비한다면 어려웠던 문제에서 이해한 부분과 막힌 부분을 구분해 표시해 보세요. “문제 뜻은 알겠는데 어떤 방법을 써야 할지 모르겠어요”처럼 말하면 필요한 설명을 찾기 쉽습니다. 처음부터 질문을 잘 정리할 필요는 없으며, 표시한 문제를 함께 살피는 것부터 시작할 수 있습니다.'),
            ('잘 풀린 문제도 함께 가져오기', '틀린 문제만 모으기보다 혼자 해결한 문제와 도움을 받아 푼 문제도 준비해 보세요. 어느 정도까지 스스로 할 수 있는지 비교하면 시작할 학습 범위를 정하는 데 도움이 됩니다. 사용 중인 교재와 학교 과제도 함께 살펴보고 새 교재가 필요한지는 상담에서 논의하면 좋습니다.')]),
        ('수업 시간과 복습 시간을 함께 잡아보세요', [
            ('먼저 움직이기 어려운 일정을 적기', '학교 수업, 통학, 기존 활동, 휴식 시간을 일주일 일정에 먼저 표시해 보세요. 빈 시간이 있다고 모두 수업으로 채우기보다는 수업 내용을 혼자 확인할 여유가 있는지도 살펴보는 것이 좋습니다. 방문 또는 온라인 수업의 운영 여부와 가능한 시간은 별도로 문의해 주세요.'),
            ('다음 수업까지 할 일을 작게 정하기', '배운 내용을 한꺼번에 복습하겠다는 계획보다 다시 풀 문제와 확인할 내용을 구체적으로 정해 보세요. 계획을 지키기 어려웠다면 실제 걸린 시간과 어려웠던 부분을 기록해 다음 수업에서 분량을 조정할 수 있습니다. 일정 변경이나 학교 시험 기간의 수업 조정 기준도 시작 전에 확인하면 좋습니다.')])],
}
parser = argparse.ArgumentParser()
parser.add_argument('--all', action='store_true', help='Build all regional general-tutoring pages as candidates')
parser.add_argument('--apply-output', action='store_true', help='Apply validated candidates to output; requires --all')
args = parser.parse_args()
assert not args.apply_output or args.all
original_samples = list(SAMPLES)
page_by_slug = {p['slug']:p for p in PAGES}
if args.all:
    SAMPLES = []
    for page in PAGES:
        if page['page_type'] != '과외' or page.get('school_name') or any(w in page['breadcrumb_label'] for w in ['수학','영어','초등','중등','고등']):
            continue
        sample = next((s for s in original_samples if s[0] == page['slug']), None)
        if sample:
            SAMPLES.append(sample)
            continue
        region = page['breadcrumb_label']
        body = BeautifulSoup(page['body_html'], 'html.parser').get_text(' ', strip=True)
        short = ('ulleung' if '질문을 정리하지 못' in body else
                 'bokdae' if '복습이 약한' in body or '오답' in body[:250] else 'gangnam')
        source = next(s for s in original_samples if s[1] == short)
        old_region = {'gangnam':'강남구','bokdae':'청주 복대동','ulleung':'울릉군'}[short]
        label = ' '.join(dict.fromkeys(filter(None,[page['province'],page['city'],region])))
        SAMPLES.append((page['slug'], short, source[2].replace(old_region,label), source[3], source[4].replace(old_region,label)))
reports = []
texts = []
for slug, short, title, subtitle, lead in SAMPLES:
    page = page_by_slug[slug]
    region = page['breadcrumb_label']
    source_path = OUT / slug / 'index.html'
    backup = ROOT / 'backup_output_general' / slug / 'index.html'
    if args.all and backup.exists():
        source_path = backup
    original = BeautifulSoup(source_path.read_text(encoding='utf-8'), 'html.parser')
    content = original.select_one('article .content')
    old_title = original.title.get_text(strip=True)
    doc = BeautifulSoup(BASE.replace('경상북도 울릉군', '__REGION_PATH__').replace('울릉군', region).replace('__REGION_PATH__', ' '.join(dict.fromkeys(filter(None, [page['province'], page['city'], page['locality']])))), 'html.parser')
    if args.all:
        styles = [deepcopy(s) for s in doc.head.find_all('style')]
        head = deepcopy(original.head)
        for s in head.select('link[rel=stylesheet]'):
            s.decompose()
        for s in head.select('meta[name=robots]'):
            s.decompose()
        head.extend(styles)
        doc.head.replace_with(head)
    doc.title.string = title
    doc.select_one('meta[name=description]')['content'] = lead
    if args.all:
        for selector,value in [('meta[property="og:title"]',title),('meta[name="twitter:title"]',title),('meta[property="og:description"]',lead),('meta[name="twitter:description"]',lead)]:
            if doc.select_one(selector): doc.select_one(selector)['content'] = value
        for script in doc.select('script[type="application/ld+json"]'):
            data = json.loads(script.string)
            for node in data.get('@graph',[]):
                if node.get('@type') == 'WebPage': node.update(name=title,description=lead)
            script.string = json.dumps(data,ensure_ascii=False,separators=(',',':'))
    doc.h1.clear()
    doc.h1.append(region + ' 과외')
    span = doc.new_tag('span'); span.string = subtitle; doc.h1.append(span)
    doc.select_one('.lead').string = lead
    crumb = doc.select_one('.crumb'); crumb.clear()
    for label, href in [('홈', '/'), (page['province'], '/' + page['province'] + '과외/')]:
        a = doc.new_tag('a', href=href); a.string = label; crumb.append(a); crumb.append(' / ')
    crumb.append(region)
    # Group original paragraphs without rewriting their order within each section.
    groups = [('intro', [])]
    for element in content.find_all(recursive=False):
        if element.name == 'h2':
            continue
        if element.name == 'h3':
            groups.append((element.get_text(strip=True), []))
        else:
            groups[-1][1].append(deepcopy(element))
    article = doc.select_one('.layout > article')
    for section in list(article.find_all('section', recursive=False))[:4]:
        section.decompose()
    inserted = []
    removed = []
    used_ids = set()
    for heading, nodes in groups:
        if any(term in heading for term in ['연결', '나누어 보기', '지역 안에서', '다음 단계로 살펴볼 과외 유형']):
            removed.append(heading)
            quotes = [n for n in nodes if n.name == 'blockquote']
            if quotes and inserted:
                inserted[-1].extend(quotes)
            continue
        if not nodes:
            continue
        identifier = 'start' if heading == 'intro' else ('learning' if any(k in heading for k in ['학년', '학생 단계']) else ('subjects' if any(k in heading for k in ['과목', '수학', '영어']) else 'study-' + str(len(inserted))))
        if identifier in used_ids: identifier += '-more'
        used_ids.add(identifier)
        section = doc.new_tag('section', attrs={'class':'section', 'id':identifier})
        h = doc.new_tag('h2'); h.string = region + '에서 과외를 선택할 때' if heading == 'intro' else heading; section.append(h)
        for node in nodes:
            for text in list(node.find_all(string=True)):
                value = str(text)
                value = value.replace(old_title + '를 기준으로 보면', '현재 학습 상태를 기준으로 보면')
                value = value.replace('개별 맞춤 과외 목표 달성 준비를 실제 수업으로 연결하려면', '실제 수업 계획을 세우려면')
                value = value.replace('개별 맞춤 과외 목표 달성 준비는', '학습 목표는')
                text.replace_with(value)
            if node.name == 'ul' and identifier in ['learning', 'subjects']:
                cards = doc.new_tag('div', attrs={'class':'cards' + (' two' if identifier == 'subjects' else '')})
                for i, li in enumerate(node.find_all('li', recursive=False)):
                    card = doc.new_tag('div', attrs={'class':'card'})
                    title_node = doc.new_tag('h3'); title_node.string = (['초등 학습', '중등 학습', '고등 학습'] if identifier == 'learning' else ['수학 학습', '영어 학습'])[min(i, 2 if identifier == 'learning' else 1)]
                    p = doc.new_tag('p'); p.string = li.get_text(' ',strip=True)
                    card.extend([title_node,p]); cards.append(card)
                section.append(cards)
            else: section.append(node)
        inserted.append(section)
    for section in reversed(inserted): article.insert(0, section)
    # Add practical, non-subject-specific guidance without claiming local facts.
    for index, (heading, paragraphs) in enumerate(SUPPLEMENTS[short]):
        section = doc.new_tag('section', attrs={'class':'section', 'id':f'guide-{index + 1}'})
        h = doc.new_tag('h2'); h.string = heading; section.append(h)
        for subheading, body in paragraphs:
            h3 = doc.new_tag('h3'); h3.string = subheading
            p = doc.new_tag('p'); p.string = body.replace({'gangnam':'강남구','bokdae':'복대동','ulleung':'울릉군'}[short],region)
            section.extend([h3, p])
        article.select_one('#conditions').insert_before(section)
    a = doc.new_tag('a', href='#guide-1'); a.string = '수업 선택·준비 안내'
    doc.select_one('.toc').append(a)
    # Use real existing related-page paths, not substituted slugs.
    related = doc.select_one('.links'); related.clear()
    links = []
    for a in original.select('.related-section a[href]'):
        href = a['href']
        if href == '/' + slug + '/' or href in [x[0] for x in links]: continue
        target = OUT / href.strip('/') / 'index.html'
        if target.exists(): links.append((href, a.select_one('strong').get_text(strip=True) if a.select_one('strong') else a.get_text(' ',strip=True)))
        if len(links) == 8 and not args.all: break
    for href, label in links:
        a = doc.new_tag('a', href=href); a.string = label + ' →'; related.append(a)
    for marker in doc.select('.num'): marker.decompose()
    for a in list(doc.select('.toc a')):
        if not doc.select_one(a['href']): a.decompose()
    sample_nav = doc.new_tag('nav', attrs={'class':'toc', 'aria-label':'미리보기 비교'})
    for other_slug, other_short, *_ in original_samples:
        a = doc.new_tag('a', href='/preview-general-' + other_short + '/'); a.string = other_slug.removesuffix('과외') + ' 수정본'; sample_nav.append(a)
    a = doc.new_tag('a', href='/' + slug + '/'); a.string = '이 지역 원본 보기'; sample_nav.append(a)
    a = doc.new_tag('a', href='#guide-1'); a.string = '추가한 콘텐츠 바로 보기 ↓'; sample_nav.append(a)
    if not args.all: doc.main.insert(0, sample_nav)
    extra = doc.new_tag('style'); extra.string = '.section>ul{padding-left:22px}.section blockquote{margin:24px 0;padding:16px 20px;border-left:3px solid #98ad84;background:#eef2e7}.cards p{line-height:1.9}@media(max-width:760px){nav[aria-label="미리보기 비교"] a{display:inline!important}}'
    doc.head.append(extra)
    target = ROOT / 'candidate_output_general' / slug if args.all else OUT / ('preview-general-' + short)
    target.mkdir(parents=True,exist_ok=True)
    if args.all:
        marker = doc.new_tag('meta', attrs={'name':'goodstudy-template','content':'regional-general-v1'})
        doc.head.append(marker)
        for a in list(doc.select('a[href^="#"]')):
            if not doc.find(id=a['href'][1:]): a.decompose()
        assert doc.select_one('link[rel=canonical]')['href'] == original.select_one('link[rel=canonical]')['href']
        assert not doc.select_one('meta[name=robots][content*="noindex"]')
        assert 'preview-' not in str(doc)
        assert len(doc.select('#guide-1, #guide-2')) == 2
        for a in doc.select('a[href^="/"]'):
            from urllib.parse import unquote
            path = unquote(a['href'].split('#')[0]).strip('/')
            assert not path or (OUT / path).exists(), (slug,a['href'])
    (target / 'index.html').write_text(str(doc), encoding='utf-8')
    before = [x.get_text(' ', strip=True) for x in content.find_all(['p','li'])]
    after = article.get_text(' ',strip=True)
    kept = sum(t in after for t in before)
    text = ' '.join(s.get_text(' ',strip=True) for s in inserted)
    if not args.all: texts.append((region, text.replace(region,'[지역]')))
    assert len(doc.find_all('h1')) == 1
    assert doc.select_one('.content-fixed-image img')['src'] == '/assets/images/content/body-common.webp'
    assert (OUT / 'assets/images/content/body-common.webp').exists()
    reports.append({'region':region,'slug':slug,'original_paragraphs_and_items':len(before),'exactly_retained':kept,'removed_navigation_sections':removed,'url':original.select_one('link[rel=canonical]')['href'] if args.all else 'http://127.0.0.1:8058/preview-general-' + short + '/'})
    if args.all and len(reports) % 200 == 0: print(f'Validated {len(reports)}/{len(SAMPLES)}',flush=True)
for i, (region, text) in enumerate(texts):
    for other, other_text in texts[i+1:]:
        reports.append({'pair':[region,other],'core_sequence_similarity':round(SequenceMatcher(None,text,other_text,autojunk=False).ratio(),3)})
if args.all:
    if args.apply_output:
        for slug,*_ in SAMPLES:
            backup = ROOT / 'backup_output_general' / slug / 'index.html'
            backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists(): shutil.copy2(OUT / slug / 'index.html',backup)
            shutil.copy2(ROOT / 'candidate_output_general' / slug / 'index.html',OUT / slug / 'index.html')
    report_path = ROOT / 'audit/general-rollout.json'
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'validated':len(reports),'applied':args.apply_output,'supplement_groups':dict(Counter(s[1] for s in SAMPLES))},ensure_ascii=False))
else:
    print(json.dumps(reports, ensure_ascii=False, indent=2))
