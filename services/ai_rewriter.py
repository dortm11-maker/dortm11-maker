"""
정통 뉴스 스타일 AI 큐레이션 & 리라이팅 엔진
- 상단 3줄 핵심 요약 + 온전하고 풍성한 실제 신문 기사 본문 문단(4~8문단) 생성
- 언론사 이름, 사진기자 바이라인, 기자 이메일 본문 완전 배제
- 사실(Fact), 수치, 인용구는 보존하면서 신뢰도 높은 저널리즘 문체로 완성
"""

import os
import re
import json
import requests
from services.curation_db import save_curated_article, get_curated_article_by_url
from services.image_enhancer import get_premium_stock_image

# 언론사 바이라인 및 출처 표기 정규식 패턴 (본문에서 완전 삭제)
BYLINE_PATTERNS = [
    r'^\s*\(.*?(?:연합뉴스|뉴스1|뉴시스|매일경제|한국경제|조선일보|동아일보|중앙일보|한겨레|경향신문|헤럴드경제|머니투데이|아시아경제|SBS|MBC|KBS|YTN|데일리안|이데일리|디지털타임스|전자신문|아이뉴스24|파이낸셜뉴스).*?\)\s*',
    r'^\s*\[.*?(?:연합뉴스|뉴스1|뉴시스|매일경제|한국경제|조선일보|동아일보|중앙일보|한겨레|경향신문|헤럴드경제|머니투데이|아시아경제|SBS|MBC|KBS|YTN|데일리안|이데일리|디지털타임스|전자신문).*?\]\s*',
    r'[\s\-_\|]+(?:연합뉴스|뉴스1|뉴시스|매일경제|한국경제|조선일보|동아일보|중앙일보|한겨레|경향신문|헤럴드경제|머니투데이|아시아경제|SBS|MBC|KBS|YTN|데일리안|이데일리|디지털타임스|전자신문|아이뉴스24|파이낸셜뉴스)\s*$',
    r'[가-힣]{2,4}\s*(?:기자|특파원|논설위원|연구위원)\s*=\s*',
    r'[가-힣]{2,4}\s*기자(?:\s|$)',
    r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+',
    r'<저작권자.*?>',
    r'무단\s*전재.*?금지',
    r'재배포\s*금지',
    r'DB\s*금지',
    r'송고'
]

def clean_news_title(title):
    """헤드라인에서 언론사명 꼬리표 (| 연합뉴스, [매일경제] 등) 완전 제거"""
    if not title:
        return ""
    t = title.strip()
    t = re.sub(r'[\s\-_\|]+(?:연합뉴스|뉴스1|뉴시스|매일경제|한국경제|조선일보|동아일보|중앙일보|한겨레|경향신문|헤럴드경제|머니투데이|아시아경제|SBS|MBC|KBS|YTN|데일리안|이데일리|디지털타임스|전자신문|아이뉴스24|파이낸셜뉴스)\s*$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^\[[^\]]*(?:연합뉴스|뉴스1|뉴시스|매일경제|한국경제|조선일보|동아일보|중앙일보|한겨레|경향신문|헤럴드경제|머니투데이|아시아경제|SBS|MBC|KBS|YTN)[^\]]*\]\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\([^\)]*(?:연합뉴스|뉴스1|뉴시스|매일경제|한국경제|조선일보|동아일보|중앙일보|한겨레|경향신문|헤럴드경제|머니투데이|아시아경제|SBS|MBC|KBS|YTN)[^\)]*\)\s*', '', t, flags=re.IGNORECASE)
    return t.strip()

def rewrite_news_title(title, paragraphs=None, category='전체'):
    """
    원문 뉴스의 핵심 키워드(기업명, 인물, 주요 수치, 사건)는 보존하되,
    원문과 동일/유사하지 않게 자연스러운 고유 헤드라인으로 재구성
    """
    if not title:
        return "실시간 주요 뉴스 속보"
        
    t = clean_news_title(title)
    
    # 1. 인용원 / 증권사 / 취재원 접두어 자연스럽게 분리
    t = re.sub(r'^[가-힣a-zA-Z0-9]+(?:증권|투자증권|연구원|연구위원)\s*[\":\']\s*', '', t)
    t = re.sub(r'^[가-힣]{2,4}\s*(?:기자|특파원|대표|장관|총리|위원장|부총리)\s*[\":\']\s*', '', t)
    t = t.strip('\"\' ')

    # 2. 구분 기호(… 또는 ... 또는 - 또는 |)를 기준으로 분절 분석
    parts = re.split(r'…|\.\.\.', t)
    
    if len(parts) >= 2:
        front = parts[0].strip().strip('\"\' ')
        back = parts[1].strip().strip('\"\' ')
        
        # 앞부분 정제 및 문맥 보강
        front = re.sub(r'([가-힣a-zA-Z0-9]+),\s*파업', r'\1 파업 여파로', front)
        front = re.sub(r'([가-힣a-zA-Z0-9]+),\s*', r'\1 ', front)

        # 뒷부분 서술어 재창작
        if any(w in back for w in ['목표가↑', '목표가 ↑', '상향', '목표가상향']):
            back_new = '수익성 개선 기대에 목표가 상향'
        elif any(w in back for w in ['목표가↓', '목표가 ↓', '하향']):
            back_new = '업황 둔화 우려에 목표가 하향 조정'
        elif any(w in back for w in ['차질', '비상', '난항']):
            back_new = '연간 사업 계획 차질 우려'
        elif any(w in back for w in ['급등', '폭등', '랠리']):
            back_new = '가파른 강세 지속에 추가 상승 여력 주목'
        elif any(w in back for w in ['급락', '폭락', '약세', '하락']):
            back_new = '하방 압력 심화에 시장 불안 가중'
        elif any(w in back for w in ['출시', '공개', '선보여']):
            back_new = '공식 공개로 글로벌 시장 공략 시동'
        elif any(w in back for w in ['체결', '협약', '맞손']):
            back_new = '공식 체결로 사업 시너지 본격화'
        elif any(w in back for w in ['착수', '돌입', '시작']):
            back_new = '본격 돌입으로 경쟁력 제고 총력'
        elif any(w in back for w in ['확대', '확장']):
            back_new = '고부가 제품군 확대 본격화'
        elif any(w in back for w in ['돌파', '신고가']):
            back_new = '기록 경신하며 상승 랠리 가속'
        elif any(w in back for w in ['우려', '경고']):
            back_new = '우려 확산에 향후 대응책 분수령'
        else:
            back_new = f'{back} 소식에 이목 집중'
            
        return f"{front}…{back_new}"
        
    else:
        # 단일 문장형 헤드라인 변환
        cand = t
        cand = re.sub(r'([가-힣a-zA-Z0-9]+),\s*', r'\1 ', cand)
        if any(w in cand for w in ['확대', '확장']):
            cand = re.sub(r'(?:확대|확장)$', '확대 본격화', cand)
        elif any(w in cand for w in ['상향', '목표가↑']):
            cand = re.sub(r'(?:상향|목표가↑)$', '목표가 잇단 상향', cand)
        elif any(w in cand for w in ['차질', '난항']):
            cand = f"{cand}…연간 목표 비상"
        elif any(w in cand for w in ['우려', '경고']):
            cand = f"{cand}…시장 긴장감 고조"
        else:
            cand = f"{cand}…세부 동향에 쏠린 눈"
        return cand

# 문장 어미 자연스러운 뉴스체 변환
ENDING_RULES = [
    (r'것으로 알려졌다\.', '것으로 전해졌습니다.'),
    (r'것으로 나타났다\.', '것으로 파악됐습니다.'),
    (r'것으로 보인다\.', '것으로 관측됩니다.'),
    (r'것으로 확인됐다\.', '것으로 공식 확인됐습니다.'),
    (r'밝혔다\.', '설명했습니다.'),
    (r'전했다\.', '보도했습니다.'),
    (r'강조했다\.', '분명히 했습니다.'),
    (r'설명했다\.', '밝혔습니다.'),
    (r'주장했다\.', '의견을 피력했습니다.'),
    (r'지적했다\.', '문제를 짚었습니다.'),
    (r'말했다\.', '밝혔습니다.'),
    (r'전망된다\.', '전망이 우세합니다.'),
    (r'예상된다\.', '예상이 나오고 있습니다.'),
    (r'기록했다\.', '집계됐습니다.'),
    (r'도달했다\.', '이르렀습니다.'),
    (r'보였다\.', '나타났습니다.'),
    (r'확인됐다\.', '파악됐습니다.'),
    (r'발표했다\.', '공식 발표했습니다.'),
    (r'올렸다\.', '상향 조정했습니다.'),
    (r'내렸다\.', '하향 조정했습니다.'),
    (r'상회했다\.', '상회했습니다.'),
    (r'유지했다\.', '유지했습니다.'),
    (r'전망했다\.', '전망했습니다.'),
    (r'산정했다\.', '산정됐습니다.'),
    (r'짚었다\.', '짚었습니다.'),
    (r'판단한다\.', '판단했습니다.'),
    # 일반적인 과거 서술형 변환
    (r'([가-힣]{2,})했다\.', r'\1했습니다.'),
    (r'([가-힣]{2,})됐다\.', r'\1됐습니다.'),
    (r'했습니다했습니다\.', '했습니다.'),
    (r'됐습니다됐습니다\.', '됐습니다.')
]

def clean_news_line(text):
    """언론사명, 바이라인, 이메일, 저작권 문구를 말끔하게 제거"""
    if not text:
        return ""
    t = text.strip()
    for pat in BYLINE_PATTERNS:
        t = re.sub(pat, '', t, flags=re.IGNORECASE).strip()
    # 기타 언론사 언급 단어 정제
    t = re.sub(r'\(사진=.*?\)', '', t)
    t = re.sub(r'\[사진=.*?\]', '', t)
    return t.strip()

def local_rewrite_paragraphs(paragraphs):
    """본문 각 문단을 매끄럽고 신뢰도 높은 실제 신문 기사 문체로 재가공"""
    cleaned_paras = []
    for p in paragraphs:
        cp = clean_news_line(p)
        if len(cp) >= 15:
            # 어미 변환
            for pat, repl in ENDING_RULES:
                cp = re.sub(pat, repl, cp)
            cleaned_paras.append(cp)
    return cleaned_paras

def generate_3line_summary(title, paragraphs):
    """기사 핵심 팩트에서 깔끔하고 절제된 3줄 요약 추출"""
    clean_title = title.strip()
    
    candidates = []
    for p in paragraphs:
        cleaned = clean_news_line(p)
        if len(cleaned) < 20:
            continue
        # 문장 단위 분리
        sentences = [s.strip() for s in cleaned.split('.') if len(s.strip()) > 15]
        for s in sentences:
            # 핵심 수치나 키워드가 포함된 문장 우선 선별
            if any(c in s for c in ['%', '억원', '달러', '상향', '하향', '발표', '전망', '증가', '감소', '기록', '유지', '출시', '생산', '차질']):
                clean_s = clean_news_line(s)
                if clean_s not in candidates and clean_s != clean_title:
                    candidates.append(clean_s)
                    if len(candidates) >= 3:
                        break
        if len(candidates) >= 3:
            break

    points = [clean_title]
    for c in candidates:
        if len(points) < 3 and c not in points:
            points.append(c)

    # 부족할 경우 다른 문단에서 보강
    if len(points) < 3:
        for p in paragraphs[1:]:
            cleaned = clean_news_line(p).split('.')[0].strip()
            if len(cleaned) > 20 and cleaned not in points:
                points.append(cleaned)
                if len(points) >= 3:
                    break

    while len(points) < 3:
        points.append("관련 세부 동향 및 후속 조치에 업계와 시장의 관심이 모이고 있습니다.")

    return points[:3]

def local_generate_issue_briefing(title, category="전체"):
    """
    원문 본문 스크래핑 및 인용 없이, 공개된 헤드라인 이슈의 핵심 키워드를 기반으로
    배경, 시장 영향, 산업적 의미, 향후 전망을 담은 독자적 뉴스 브리핑 문단(4문단) 생성
    """
    clean_t = rewrite_news_title(title, category=category)
    
    # 카테고리별 전문적인 분석 관점 정의
    cat_focus = {
        '증권': ('증권가 및 금융 투자 시장', '기업 실적 추정치와 밸류에이션, 외국인·기관 수급 동향', '시장 눈높이 변화와 단기 변동성'),
        '경제': ('거시 경제 및 실물 산업계', '공급망 안정성 및 경기 지표, 주요 경영 환경', '금리·환율 등 대외 불확실성 대응'),
        '부동산': ('부동산 시장 및 분양·매매 동향', '대출 규제 및 금리 환경, 거래량 추이', '실수요자 관망세 및 향후 시장 가격 흐름'),
        'IT/과학': ('첨단 테크 생태계 및 IT 산업계', '글로벌 기술 표준 경쟁, 차세대 로드맵 및 특허 영향력', '연구개발(R&D) 성과 및 시장 선점 속도'),
        '정치': ('정치권 및 정책 당국', '제도 정비 및 입법 과제, 주요 이해관계자 여론', '후속 정책 발표 및 향후 국정 대응 추이'),
        '사회': ('사회 각계 및 관련 현장', '제도적 보완책 및 공론화 논의, 시민 생활 영향', '재발 방지 대책 및 제도 개선 동향'),
        '전체': ('시장 및 관련 산업계 전반', '주요 실적 지표와 공급망, 업계 전반의 경영 환경', '향후 전개될 정책 및 시장 반응')
    }
    target_area, impact_area, outlook_area = cat_focus.get(category, cat_focus['전체'])

    p1 = (
        f"{clean_t} 관련 소식이 전해지며 {target_area}의 이목이 집중되고 있습니다. "
        f"이번 사안은 최근 {category} 분야의 흐름과 맞물려 관련 업계 및 이해관계자들 사이에서 주요 현안으로 떠올랐습니다."
    )

    p2 = (
        f"전문가들은 이번 이슈가 단순한 일회성 현상에 그치지 않고, 향후 {impact_area}에 "
        f"실질적인 변수로 작용할 가능성에 주목하고 있습니다. 특히 관련 생태계의 거래 동향과 정책적 가이드라인의 변화가 중요한 분수령이 될 것으로 분석됩니다."
    )

    p3 = (
        f"시장 참여자들 사이에서는 이번 사안을 둘러싸고 다각도의 분석과 신중론이 교차하는 분위기입니다. "
        f"대내외 경제 환경의 불확실성이 지속되는 상황에서, 단기적인 리스크 관리와 함께 중장기적인 기회 요인을 면밀히 짚어보아야 한다는 의견이 힘을 얻고 있습니다."
    )

    p4 = (
        f"향후 전개될 세부 후속 조치와 관련 업계의 대응 방향에 따라 구체적인 영향의 윤곽이 드러날 전망입니다. "
        f"관계자들은 {outlook_area}을 주시하며, 시장의 안정적인 대응과 발전적 해법을 모색하는 데 집중하고 있습니다."
    )

    summary = [
        f"{clean_t} 관련 현황 대두",
        f"{category} 분야 및 {target_area} 파급 영향 집중 분석",
        "향후 세부 후속 조치 및 주요 변수에 업계 관심 고조"
    ]

    return {
        "ai_title": clean_t,
        "summary_points": summary,
        "paragraphs": [p1, p2, p3, p4]
    }

def call_gemini_news_writer(api_key, title, category):
    """
    Google Gemini를 활용하여 원문 복제 없이 공개 헤드라인 기반 독자적 이슈 분석 브리핑 리포트 생성
    (※ 원문 본문은 일절 전달하지 않음 - 저작권 완벽 준수)
    """
    prompt = f"""당신은 한국 경제/시사 전문 리서치 에디터입니다.
오직 공개된 [이슈 헤드라인]과 [카테고리] 정보만을 바탕으로, 독자들을 위한 독자적이고 전문적인 [시사·경제 이슈 분석 브리핑 리포트]를 작성하십시오.

[이슈 헤드라인] {title}
[카테고리] {category}

[작성 수칙 - 저작권 완벽 준수]
1. [원문 복제/다시쓰기 절대 금지]: 외부 언론사의 기사 원문이나 문장을 복제하거나 흉내 내지 마십시오. 오직 헤드라인의 핵심 사건/주제를 바탕으로, 독자적인 배경 설명, 시장 영향 분석, 산업적 시사점, 향후 관전 포인트를 신문사 분석 기사 형식의 4~5개 문단으로 작성하십시오.
2. [헤드라인 독자적 재작성]: 원안 헤드라인의 핵심 키워드(기업/인물/주제/수치)는 정확히 유지하되, 원문과 동일하거나 유사하지 않게 정통 신문 기사 헤드라인으로 완전히 새롭게 재구성하십시오.
3. [언론사명 및 기자명 절대 배제]: '연합뉴스', '뉴스1' 등 특정 언론사나 기자 이름, 이메일은 절대 언급하지 마십시오.
4. [풍성한 분석 문단 (4~5개)]: 실제 전문지의 심층 분석 기사처럼 자연스러운 문맥으로 4~5개의 온전하고 풍성한 문단(paragraphs)으로 작성하십시오.
5. [3줄 핵심 요약]: 리포트 첫머리에 들어갈 간결하고 명쾌한 3줄 요약(summary_points)을 작성하십시오.
6. [문체]: 단정하고 신뢰할 수 있는 저널리즘 해설 보도체(~했습니다, ~설명됩니다, ~전망입니다)로 서술하십시오.
7. 반드시 오직 유효한 JSON 형식으로만 응답하십시오:

{{
  "ai_title": "독자적이고 완성도 높은 정통 신문 기사 헤드라인",
  "summary_points": [
    "핵심 요약 1",
    "핵심 요약 2",
    "핵심 요약 3"
  ],
  "paragraphs": [
    "문단 1 (이슈의 개요 및 발생 배경)",
    "문단 2 (시장 및 산업 생태계에 미치는 파급 효과)",
    "문단 3 (업계 반응 및 주요 변수 분석)",
    "문단 4 (향후 전망 및 관전 포인트)"
  ]
}}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.25, "response_mime_type": "application/json"}
    }
    headers = {"Content-Type": "application/json"}

    resp = requests.post(url, headers=headers, json=payload, timeout=12)
    if resp.status_code == 200:
        res_json = resp.json()
        candidates = res_json.get('candidates', [])
        if candidates:
            raw_text = candidates[0]['content']['parts'][0]['text'].strip()
            if raw_text.startswith('```json'):
                raw_text = raw_text.replace('```json', '', 1).rstrip('`').strip()
            elif raw_text.startswith('```'):
                raw_text = raw_text.replace('```', '', 1).rstrip('`').strip()
            return json.loads(raw_text)

    raise Exception(f"Gemini API 오류 ({resp.status_code})")

def build_full_news_article(title, site_cfg=None, url="", category="전체", publisher_name="주요 언론사", raw_paragraphs=None):
    """
    저작권 안심 독자적 뉴스 브리핑 리포트 생성 엔진:
    - 원문 본문 스크래핑/인용/DB저장 ❌
    - 공개된 헤드라인과 카테고리만을 바탕으로 배경·시장영향·전망을 담은 4문단 분석 리포트 생성 ✅
    """
    ai_cfg = (site_cfg or {}).get('ai_rewrite', {})
    gemini_key = ai_cfg.get('gemini_api_key', '').strip()

    clean_raw_title = clean_news_title(title)
    article_result = None

    # 1. Gemini 초거대 AI 연동 시도 (오직 헤드라인과 카테고리만 전달)
    if gemini_key:
        try:
            article_result = call_gemini_news_writer(gemini_key, clean_raw_title, category)
        except Exception as e:
            print(f"[Gemini Briefing Fallback to Local Engine] {e}")

    # 2. 로컬 지능형 이슈 분석 브리핑 엔진 폴백
    if not article_result or not article_result.get('paragraphs'):
        article_result = local_generate_issue_briefing(clean_raw_title, category=category)

    final_title = article_result.get('ai_title') or rewrite_news_title(clean_raw_title, category=category)

    # 대표 이미지 매칭 (상업적 무상 고화질 스톡)
    safe_img = get_premium_stock_image(final_title, " ".join(article_result.get('paragraphs', [])[:2]))

    # Curation DB에 저장 (원문 본문은 일절 저장하지 않음)
    record = {
        'source_name': publisher_name,
        'original_title': title,
        'original_url': url,
        'published_at': '',
        'category': category,
        'keywords': [],
        'ai_title': final_title,
        'ai_content': {
            'summary_points': article_result.get('summary_points', []),
            'paragraphs': article_result.get('paragraphs', [])
        },
        'ai_image': safe_img,
        'cluster_sources': []
    }
    if url:
        save_curated_article(record)

    return {
        'title': final_title,
        'summary_points': article_result.get('summary_points', []),
        'paragraphs': article_result.get('paragraphs', []),
        'main_img': safe_img
    }

# 기존 코드 호환 래퍼
def build_curated_briefing(cluster_item, site_cfg=None):
    primary = cluster_item.get('primary', {})
    url = primary.get('link') or primary.get('original_url', '')
    title = primary.get('title') or primary.get('original_title', '')
    category = cluster_item.get('category', '전체')
    publisher = primary.get('source', '주요 언론사')
    
    art = build_full_news_article(title, site_cfg, url, category, publisher)
    return {
        'id': '',
        'source_name': publisher,
        'original_title': title,
        'original_url': url,
        'published_at': primary.get('date', ''),
        'category': category,
        'keywords': [],
        'ai_title': art['title'],
        'ai_content': {
            'summary_points': art['summary_points'],
            'paragraphs': art['paragraphs']
        },
        'ai_image': art['main_img'],
        'cluster_sources': cluster_item.get('cluster_sources', [])
    }
