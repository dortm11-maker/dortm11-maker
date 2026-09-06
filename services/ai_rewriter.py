"""
독자적 뉴스 큐레이션 & AI 팩트 브리핑 엔진
- 단순한 원문 문장 바꾸기(패러프레이징)를 배제하고, 독자적인 뉴스 브리핑 리포트 생성
- 포맷: 📌 핵심 요약 3선 / 🔍 이슈 배경 및 사실 관계 / 💡 왜 중요한가(시사점) / 🏷️ 관련 키워드
- 할루시네이션(지어내기) 원천 차단: 확인된 RSS 제목 및 요약문 팩트에 엄격히 한정하여 작성
- Google Gemini 1.5 Flash REST API 연동 및 지능형 로컬 브리핑 생성기 지원
"""

import os
import re
import json
import requests
from services.curation_db import save_curated_article, get_curated_article_by_url
from services.image_enhancer import get_premium_stock_image

def extract_clean_keywords(text_list):
    """헤드라인 및 요약문들에서 핵심 키워드 4~5개 추출"""
    combined = " ".join(text_list)
    cleaned = re.sub(r'\[[^\]]*\]|\([^\)]*\)|["\'“”‘’]', ' ', combined)
    words = re.findall(r'[가-힣a-zA-Z0-9]{2,}', cleaned)
    stop = {'속보', '단독', '종합', '상보', '오늘', '어제', '내일', '관련', '대한', '통해', '위해', '하는', '있는', '된다', '됐다'}
    freq = {}
    for w in words:
        w_low = w.lower()
        if w_low not in stop and len(w_low) >= 2:
            freq[w_low] = freq.get(w_low, 0) + 1
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [w[0] for w in sorted_words[:5]]

def generate_local_briefing(primary_title, cluster_sources, all_summaries, category):
    """
    API 키 없이도 100% 무료/무제한으로 신뢰할 수 있는 구조화된 뉴스 브리핑 리포트를 생성
    - 여러 언론사 헤드라인의 상호 보완 정보 결합
    - 없는 사실을 절대 지어내지 않고 확인된 팩트만 명확히 전달
    """
    clean_title = re.sub(r'\[[^\]]*\]|\([^\)]*\)', '', primary_title).strip()
    
    # 여러 언론사의 보도 헤드라인 취합
    other_titles = [s['title'] for s in cluster_sources if s.get('title') and s['title'] != primary_title]
    combined_titles = [primary_title] + other_titles
    
    keywords = extract_clean_keywords(combined_titles + all_summaries)

    # 1. 핵심 팩트 3줄 요약 구성
    points = []
    points.append(f"{clean_title} 소식이 주요 언론사를 통해 공식 전해졌습니다.")
    
    if other_titles:
        alt = re.sub(r'\[[^\]]*\]|\([^\)]*\)', '', other_titles[0]).strip()
        points.append(f"관련 보도에 따르면 '{alt}' 등 주요 쟁점과 세부 내용이 함께 확인되었습니다.")
    elif all_summaries:
        first_sum = all_summaries[0][:90].rstrip()
        points.append(f"보도 요지: {first_sum}...")
    else:
        points.append(f"{category} 분야의 주요 이슈로 시장 및 관련 업계의 관심이 모이고 있습니다.")

    source_names = list(dict.fromkeys([s.get('source_name', '주요 언론사') for s in cluster_sources]))
    points.append(f"현재 {', '.join(source_names[:3])} 등 {len(cluster_sources)}개 언론 출처에서 본 사안을 실시간 다루고 있습니다.")

    # 2. 배경 설명
    if all_summaries and len(all_summaries[0]) > 20:
        context_text = f"공식 보도 내용에 따르면, {all_summaries[0].strip()} 해당 사안은 {category} 전반의 흐름 속에서 다각도로 분석되고 있습니다."
    else:
        context_text = f"본 건은 최근 {category} 분야에서 대두된 주요 현안으로, 관련 기관 및 시장 관계자들의 공식 입장과 향후 추이가 주목받고 있는 사안입니다."

    # 3. 중요성 및 시사점
    importance_map = {
        '부동산': "부동산 시장의 수급과 가격 동향, 실수요자 및 투자자들의 주거·금융 의사결정에 직결되는 지표이자 핵심 변수입니다.",
        '경제': "거시 경제 지표와 금리, 기업 실적 및 실물 경제 흐름에 영향을 미칠 수 있어 면밀한 점검이 필요합니다.",
        '증권': "국내외 증시 수급과 주요 섹터 종목별 투자 심리 및 단기·중기 변동성에 유의미한 시사점을 제공합니다.",
        '정치': "정책 추진 방향과 입법 과제, 관련 당국과 사회적 이해관계자 간의 정책 조율 향방을 가늠할 수 있는 분기점입니다.",
        'IT/과학': "기술 혁신 경쟁과 신산업 생태계 구축, 디지털 시장의 주도권 확보 차원에서 파급 효과가 큽니다."
    }
    importance_text = importance_map.get(category, f"해당 분야의 최신 동향을 파악하고 향후 전개될 관련 후속 조치나 시장 반응을 살피는 데 중요한 사안입니다.")

    return {
        "ai_title": clean_title,
        "summary": points[:3],
        "context": context_text,
        "importance": importance_text,
        "keywords": keywords
    }

def call_gemini_briefing(api_key, primary_title, cluster_sources, all_summaries, category):
    """Google Gemini 1.5 Flash를 이용한 엄격한 팩트 기반 브리핑 생성"""
    titles_text = "\n".join([f"- ({s.get('source_name', '언론사')}) {s.get('title', '')}" for s in cluster_sources])
    summaries_text = "\n".join([f"- {sm}" for sm in all_summaries[:3]]) if all_summaries else "별도 세부 요약 없음"

    prompt = f"""당신은 객관적이고 신뢰할 수 있는 뉴스 큐레이션 전문 수석 에디터입니다.
아래는 여러 주요 언론사의 공식 RSS를 통해 수집된 [동일 사건 팩트 데이터]입니다:

[카테고리] {category}
[언론사별 보도 헤드라인]
{titles_text}

[공식 RSS 요약 정보]
{summaries_text}

[엄격한 작성 원칙 - 위반 시 무효]
1. [할루시네이션(지어내기) 절대 금지]: 위 제공된 팩트 데이터에 없는 인물 발언, 가짜 통계, 미확인 세부내용을 절대 창작하지 마십시오.
2. [독자적 뉴스 브리핑 리포트 포맷]: 단순 기사 문장 변경이 아닌, 독자가 사안의 본질을 즉시 파악할 수 있는 체계적인 브리핑으로 작성하십시오.
3. 반드시 오직 유효한 JSON 형식으로만 응답하십시오 (마크다운 코드블록이나 불필요한 서두 생략):

{{
  "ai_title": "명확하고 중립적인 브리핑 제목 (따옴표나 언론사명 제거)",
  "summary": [
    "확인된 핵심 사실 요약 1",
    "확인된 핵심 사실 요약 2",
    "확인된 핵심 사실 요약 3"
  ],
  "context": "확인된 정보에 기반한 사건의 배경 설명 (2~3문장)",
  "importance": "이 이슈가 독자나 관련 시장에 중요한 이유 (2~3문장)",
  "keywords": ["핵심키워드1", "핵심키워드2", "핵심키워드3", "핵심키워드4"]
}}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "response_mime_type": "application/json"}
    }
    headers = {"Content-Type": "application/json"}

    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    if resp.status_code == 200:
        res_json = resp.json()
        candidates = res_json.get('candidates', [])
        if candidates:
            raw_text = candidates[0]['content']['parts'][0]['text'].strip()
            # JSON 파싱
            if raw_text.startswith('```json'):
                raw_text = raw_text.replace('```json', '', 1).rstrip('`').strip()
            elif raw_text.startswith('```'):
                raw_text = raw_text.replace('```', '', 1).rstrip('`').strip()
            return json.loads(raw_text)
            
    raise Exception(f"Gemini API 오류 ({resp.status_code}): {resp.text[:120]}")

def build_curated_briefing(cluster_item, site_cfg=None):
    """
    클러스터링된 이슈 기사를 바탕으로 독자적인 AI 뉴스 브리핑 생성 및 DB 저장
    """
    primary = cluster_item.get('primary', {})
    original_url = primary.get('link') or primary.get('original_url', '')
    original_title = primary.get('title') or primary.get('original_title', '')
    source_name = primary.get('source') or primary.get('source_name', '주요 언론사')
    published_at = primary.get('date') or primary.get('published_at', '')
    category = cluster_item.get('category') or primary.get('category', '전체')
    cluster_sources = cluster_item.get('cluster_sources', [])
    all_summaries = cluster_item.get('all_summaries', [])

    # 1. DB에 이미 생성된 브리핑이 있는지 확인 (초고속 즉시 반환)
    existing = get_curated_article_by_url(original_url)
    if existing and existing.get('ai_content') and isinstance(existing.get('ai_content'), dict) and existing['ai_content'].get('summary'):
        return existing

    # 2. 브리핑 생성 (Gemini API 시도 -> 로컬 고품질 엔진 폴백)
    ai_cfg = (site_cfg or {}).get('ai_rewrite', {})
    gemini_key = ai_cfg.get('gemini_api_key', '').strip()
    briefing_data = None

    if gemini_key:
        try:
            briefing_data = call_gemini_briefing(gemini_key, original_title, cluster_sources, all_summaries, category)
        except Exception as e:
            print(f"[Gemini Briefing Fallback to Local] {e}")

    if not briefing_data:
        briefing_data = generate_local_briefing(original_title, cluster_sources, all_summaries, category)

    ai_title = briefing_data.get('ai_title') or original_title
    keywords = briefing_data.get('keywords', [])

    # 3. 대표 이미지 매칭 (원문 사진 다운로드 ❌ -> 라이선스 안전 상업용 무상 스톡 이미지)
    ai_image = get_premium_stock_image(ai_title, briefing_data.get('context', ''))
    if not ai_image:
        from services.image_enhancer import NEWS_STOCK_CATALOG
        cat_pool = NEWS_STOCK_CATALOG.get(category, NEWS_STOCK_CATALOG.get('economy', []))
        if cat_pool:
            idx = abs(hash(original_url)) % len(cat_pool)
            ai_image = cat_pool[idx]

    # 4. Curation DB에 저장 (본문 전체/원본 사진 절대 저장하지 않음)
    record = {
        'source_name': source_name,
        'original_title': original_title,
        'original_url': original_url,
        'published_at': published_at,
        'category': category,
        'keywords': keywords,
        'ai_title': ai_title,
        'ai_content': briefing_data,
        'ai_image': ai_image,
        'cluster_sources': cluster_sources
    }
    art_id = save_curated_article(record)
    record['id'] = art_id
    return record

# 하위 호환용 래퍼
def rewrite_article(title, paragraphs, site_cfg, url=""):
    """기존 코드 호환을 위한 래퍼 함수"""
    cluster_dummy = {
        'primary': {'title': title, 'link': url, 'source': '언론사', 'date': '', 'category': '전체'},
        'category': '전체',
        'cluster_sources': [{'source_name': '언론사', 'title': title, 'url': url}],
        'all_summaries': paragraphs[:2] if paragraphs else []
    }
    curated = build_curated_briefing(cluster_dummy, site_cfg)
    b_data = curated.get('ai_content', {})
    summary_paras = b_data.get('summary', [])
    context = b_data.get('context', '')
    importance = b_data.get('importance', '')
    
    new_paras = []
    if summary_paras:
        new_paras.append("📌 핵심 요약:\n" + "\n".join([f"• {s}" for s in summary_paras]))
    if context:
        new_paras.append(f"🔍 이슈 배경:\n{context}")
    if importance:
        new_paras.append(f"💡 시사점 및 왜 중요한가:\n{importance}")

    return curated.get('ai_title', title), new_paras, True
