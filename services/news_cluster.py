import re
import urllib.parse
from datetime import datetime

# 한국어 불용어 및 무의미한 수식어 목록
STOPWORDS = {
    '속보', '단독', '종합', '상보', '포토', '기사', '뉴스', '오늘', '내일', '어제',
    '이유', '어쩌나', '알고보니', '눈길', '충격', '발칵', '이 시각', '영상', '현장',
    '관련', '대한', '통해', '위해', '하는', '있는', '된다', '됐다', '한다', '했다',
    '것으로', '있다고', '밝혔다', '전했다', '주장', '논란'
}

def canonicalize_url(url):
    """URL에서 추적용 쿼리스트링(utm, ref 등)을 제거하여 정규화"""
    if not url or not isinstance(url, str):
        return ''
    try:
        parsed = urllib.parse.urlparse(url.strip())
        qs = urllib.parse.parse_qs(parsed.query)
        # 추적 파라미터 필터링
        clean_qs = {k: v for k, v in qs.items() if not k.lower().startswith(('utm_', 'ref', 'source', 'n_media', 'sid_'))}
        clean_query = urllib.parse.urlencode(clean_qs, doseq=True)
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, clean_query, ''))
    except Exception:
        return url.strip()

def extract_keywords(text):
    """제목 및 요약문에서 유의미한 한국어 키워드/명사 토큰 추출"""
    if not text:
        return set()
    # 대괄호/소괄호 내 태그 제거 (예: [속보], (상보))
    cleaned = re.sub(r'\[[^\]]*\]|\([^\)]*\)', ' ', text)
    # 한글, 영문, 숫자 단어 추출
    words = re.findall(r'[가-힣a-zA-Z0-9]{2,}', cleaned)
    tokens = set()
    for w in words:
        w_low = w.lower()
        if w_low not in STOPWORDS and len(w_low) >= 2:
            tokens.add(w_low)
    return tokens

def calculate_similarity(tokens_a, tokens_b):
    """Jaccard 유사도 계산 (0.0 ~ 1.0)"""
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a.intersection(tokens_b)
    union = tokens_a.union(tokens_b)
    if not union:
        return 0.0
    return len(intersection) / len(union)

def is_same_event(item_a, item_b):
    """
    두 기사가 같은 사건/이슈인지 엄밀하게 판별:
    1) URL 정규화 동일 여부
    2) 제목 키워드 Jaccard 유사도 0.40 이상
    3) 3개 이상의 핵심 고유 단어가 완전히 일치하는 경우
    """
    url_a = canonicalize_url(item_a.get('link') or item_a.get('original_url', ''))
    url_b = canonicalize_url(item_b.get('link') or item_b.get('original_url', ''))
    if url_a and url_b and url_a == url_b:
        return True

    title_a = item_a.get('title') or item_a.get('original_title', '')
    title_b = item_b.get('title') or item_b.get('original_title', '')
    if title_a == title_b:
        return True

    tokens_a = extract_keywords(title_a)
    tokens_b = extract_keywords(title_b)
    
    overlap = tokens_a.intersection(tokens_b)
    # 핵심 명사가 3개 이상 겹치면 같은 사건으로 판별
    if len(overlap) >= 3:
        return True

    # 2개 이상 겹치고 Jaccard 유사도가 0.38 이상인 경우
    if len(overlap) >= 2 and calculate_similarity(tokens_a, tokens_b) >= 0.38:
        return True

    return False

def cluster_news_items(items):
    """
    수집된 수십 개의 RSS 기사를 사건/이슈별로 클러스터링(중복 통합).
    결과: 각 클러스터는 대표 기사 1개 + 같은 사건을 보도한 다른 언론사 출처 목록으로 구성됨.
    """
    clusters = []
    seen_urls = set()

    for item in items:
        url = canonicalize_url(item.get('link') or item.get('original_url', ''))
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        matched_cluster = None
        for cl in clusters:
            if is_same_event(cl['primary'], item):
                matched_cluster = cl
                break

        if matched_cluster:
            # 같은 이슈를 보도한 언론사 추가 (중복 방지)
            source_info = {
                'source_name': item.get('source') or item.get('source_name', '언론사'),
                'title': item.get('title') or item.get('original_title', ''),
                'url': item.get('link') or item.get('original_url', ''),
                'date': item.get('date') or item.get('published_at', '')
            }
            if not any(s['url'] == source_info['url'] for s in matched_cluster['cluster_sources']):
                matched_cluster['cluster_sources'].append(source_info)
                # 요약문/스니펫 보강
                summary = item.get('summary', '').strip()
                if summary and summary not in matched_cluster['all_summaries']:
                    matched_cluster['all_summaries'].append(summary)
        else:
            # 새로운 사건 클러스터 생성
            clusters.append({
                'primary': item,
                'category': item.get('category', '전체'),
                'cluster_sources': [{
                    'source_name': item.get('source') or item.get('source_name', '언론사'),
                    'title': item.get('title') or item.get('original_title', ''),
                    'url': url,
                    'date': item.get('date') or item.get('published_at', '')
                }],
                'all_summaries': [item.get('summary', '').strip()] if item.get('summary') else []
            })

    return clusters
