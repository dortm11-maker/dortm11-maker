"""
프리미엄 저작권 프리 이미지 매칭 및 원본 이미지 보호(Safeguard) 엔진
- 부동산, 경제, 증권, IT/과학, 정책 분야 고품격 상업적 무료 라이선스(Unsplash) 고화질 이미지 큐레이션
- 기사 제목/본문 키워드 정밀 분석 기반 스마트 매칭
- 원본 보도 사진의 메타데이터(EXIF) 완전 삭제, 미세 색감 보정, 뉴스NOW 워터마크 합성 기능
"""

import os
import re
import hashlib
import requests
from io import BytesIO
from PIL import Image, ImageEnhance, ImageDraw

# ==============================================================================
# 분야별 프리미엄 4K급 상업용 무료(Unsplash Verified) 스톡 이미지 카탈로그
# ==============================================================================
PREMIUM_STOCK_IMAGES = {
    # 1. 부동산 (아파트, 주택, 재개발, 분양, 청약, 펜트하우스, 도심 주거)
    'realestate': [
        # 최고급 현대식 아파트 단지 및 주거 타워
        'https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=1200&q=85',
        # 도심 스카이라인 및 신도시 주거 단지 전경
        'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=85',
        # 모던 럭셔리 아파트 인테리어 & 펜트하우스 조망
        'https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=1200&q=85',
        # 주상복합 하이엔드 건축물
        'https://images.unsplash.com/photo-1577495508048-b635879837f1?auto=format&fit=crop&w=1200&q=85',
        # 세련된 도심 아파트 야경
        'https://images.unsplash.com/photo-1515263487990-61b07816b324?auto=format&fit=crop&w=1200&q=85',
        # 프리미엄 주택 단지 및 건설 현장 조감
        'https://images.unsplash.com/photo-1503387762-592deb58ef4e?auto=format&fit=crop&w=1200&q=85',
        # 부동산 계약 및 건축 모델하우스
        'https://images.unsplash.com/photo-1560518883-ce09059eeffa?auto=format&fit=crop&w=1200&q=85',
        # 한국 도심 스타일의 쾌적한 주거 빌딩
        'https://images.unsplash.com/photo-1524813686514-a57563d77d66?auto=format&fit=crop&w=1200&q=85'
    ],

    # 2. 증권 / 주식 (코스피, 코스닥, 트레이딩, 캔들차트, 반도체, 금융 시장)
    'stock': [
        # 증권가 트레이딩 룸 실시간 주가 분석 화면
        'https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?auto=format&fit=crop&w=1200&q=85',
        # 주식 상승장 캔들 차트 모니터링
        'https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?auto=format&fit=crop&w=1200&q=85',
        # 글로벌 금융가 및 월스트리트 증권 거래소
        'https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?auto=format&fit=crop&w=1200&q=85',
        # 첨단 반도체 웨이퍼 및 마이크로칩 제조
        'https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=85',
        # 미래형 테크 투자 및 디지털 데이터 분석
        'https://images.unsplash.com/photo-1642543492481-44e81e3914a7?auto=format&fit=crop&w=1200&q=85',
        # 스마트폰 모바일 주식 MTS 거래
        'https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?auto=format&fit=crop&w=1200&q=85'
    ],

    # 3. 경제 / 금융 (금리, 환율, 통화, 무역, 물가, 은행, 거시경제)
    'economy': [
        # 글로벌 금융 중심지 대형 은행 본점 빌딩
        'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=85',
        # 골드바 및 금괴 자산 포트폴리오
        'https://images.unsplash.com/photo-1610375461246-83df859d849d?auto=format&fit=crop&w=1200&q=85',
        # 글로벌 무역 항만 및 수출입 컨테이너
        'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?auto=format&fit=crop&w=1200&q=85',
        # 경제 정책 금융 회의 및 비즈니스 브리핑
        'https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=1200&q=85',
        # 화폐 및 경제 지표 분석
        'https://images.unsplash.com/photo-1559526324-4b87b5e36e44?auto=format&fit=crop&w=1200&q=85'
    ],

    # 4. IT / 과학 / AI (인공지능, 빅데이터, 로봇, 모빌리티)
    'tech': [
        # 초고속 데이터센터 서버 랙
        'https://images.unsplash.com/photo-1558494949-ef010cbdcc31?auto=format&fit=crop&w=1200&q=85',
        # 인공지능 신경망 및 딥러닝 비주얼
        'https://images.unsplash.com/photo-1677442136019-21780efad99a?auto=format&fit=crop&w=1200&q=85',
        # 미래형 자율주행 및 스마트 모빌리티
        'https://images.unsplash.com/photo-1508974239320-0a029497e820?auto=format&fit=crop&w=1200&q=85'
    ],

    # 5. 법조 / 정책 / 사회 (법원, 국회, 정의, 정책 결정)
    'law_policy': [
        # 대법원 정의의 여신상 및 법정
        'https://images.unsplash.com/photo-1589829545856-d10d557cf95f?auto=format&fit=crop&w=1200&q=85',
        # 정부 청사 및 국회 스타일 회의장
        'https://images.unsplash.com/photo-1541872703-74c5e44368f9?auto=format&fit=crop&w=1200&q=85'
    ],

    # 6. 자동차 / 모빌리티 / 현대차 (AI 생성 법적 안심 이미지 및 4K 상업용 무료)
    'auto': [
        # 현대차 대표 AI 저작권 안심 생성 이미지 (아이오닉/세단)
        '/static/img/ai/hyundai_car.jpg',
        # 글로벌 모던 럭셔리 세단 및 전기차
        'https://images.unsplash.com/photo-1617814076367-b759c7d7e738?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1552519507-da3b142c6e3d?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1605559424843-9e4c228bf1c2?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=1200&q=85'
    ],

    # 7. 통신 / 모바일 / 스마트 라이프 (LG유플러스, SKT, KT, 모바일, 5G)
    'telecom': [
        # 모바일 스마트폰 라이프스타일
        'https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?auto=format&fit=crop&w=1200&q=85',
        # 세련된 스마트폰 앱 및 디지털 서비스
        'https://images.unsplash.com/photo-1556656793-08538906a9f8?auto=format&fit=crop&w=1200&q=85',
        # 5G 통신망 및 스마트 커넥티비티
        'https://images.unsplash.com/photo-1519389950473-47ba0277781c?auto=format&fit=crop&w=1200&q=85'
    ],

    # 8. 쇼핑 / 유통 / 명절 / 멤버십 (추석, 선물, 장보기, 외식, 나들이)
    'shopping_life': [
        # 모던 라이프스타일 쇼핑 & 멤버십 혜택
        'https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=1200&q=85',
        # 명절 선물 및 프리미엄 패키지
        'https://images.unsplash.com/photo-1513151233558-d860c5398176?auto=format&fit=crop&w=1200&q=85',
        # 활기찬 백화점 및 마트 장보기
        'https://images.unsplash.com/photo-1578916171728-46686eac8d58?auto=format&fit=crop&w=1200&q=85',
        # 외식 및 가족 나들이 라이프
        'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=1200&q=85'
    ]
}

NEWS_STOCK_CATALOG = PREMIUM_STOCK_IMAGES

# 키워드 규칙 매핑 테이블
KEYWORD_CATEGORY_RULES = [
    # 자동차/현대차/모빌리티 키워드 (최우선 판별)
    (r'현대차|현대자동차|기아|자동차|완성차|제네시스|아이오닉|전기차|팰리세이드|아반떼|투싼|카니발|쏘나타|그랜저|모터스|파업.*생산|차량|모빌리티', 'auto'),
    # 통신 / 모바일 / 통신사 키워드
    (r'lg유플러스|유플러스|sk텔레콤|skt|kt|통신사|5g|유플투쁠|멤버십|통신|요금제', 'telecom'),
    # 쇼핑 / 명절 / 추석 / 소비 / 유통 키워드
    (r'추석|명절|쇼핑|장보기|선물세트|외식|나들이|화담숲|할인|이마트|백화점|소비자|유통|마트|생필품', 'shopping_life'),
    # 부동산 키워드
    (r'부동산|아파트|분양|청약|전세|월세|매매|집값|주택|빌라|재개발|재건축|다세대|토지|오피스텔|건설|시행사|시공사|국토부|보증금|공동주택|단지', 'realestate'),
    # 증권 키워드
    (r'코스피|코스닥|증시|주식|주가|상장|공모주|배당|증권|펀드|etf|개미|외인|기관|매수|매도|반도체|하이닉스|삼성전자|엔비디아|나스닥|다우', 'stock'),
    # 경제 키워드
    (r'경제|금리|환율|인플레|물가|한국은행|기준금리|수출|수입|무역|gdp|소비자물가|재정|국채|금융|은행|외환|고용|경기침체|유가|원자재', 'economy'),
    # IT/과학 키워드
    (r'인공지능|ai|챗gpt|클라우드|빅데이터|소프트웨어|스마트폰|로봇|우주|양자|사이버', 'tech'),
    # 법조/재판/법원 키워드 (재판매 등 오작동 방지: 독립 단어로만 매칭)
    (r'법원|법정|판결|소송|검찰|기소|변호사|대법원|헌법재판소|항소|구속영장|형사재판|민사소송|(?<![가-힣])재판(?![가-힣])', 'law_policy')
]


def detect_article_topic(title, text="", category=""):
    """
    기사 제목, 본문, 카테고리를 종합 분석하여 가장 적합한 이미지 테마를 판별
    """
    full_text = f"{title} {category} {text[:300]}".lower()

    # 현대차/완성차/자동차 키워드 최우선 검출
    if re.search(r'현대차|현대자동차|기아|자동차|완성차|제네시스|아이오닉|전기차|팰리세이드|아반떼|투싼|카니발|쏘나타|그랜저|파업.*생산', full_text):
        return 'auto'

    # 통신 / 모바일 우선 검출
    if re.search(r'lg유플러스|유플러스|sk텔레콤|skt|kt|통신사|유플투쁠', full_text):
        return 'telecom'

    # 명절 / 쇼핑 / 외식 우선 검출
    if re.search(r'추석|명절|쇼핑|장보기|선물세트|외식|나들이|화담숲|멤버십', full_text):
        return 'shopping_life'

    if category in ['부동산']:
        return 'realestate'
    elif category in ['증권']:
        return 'stock'
    elif category in ['경제']:
        return 'economy'
    elif category in ['IT/과학']:
        return 'tech'

    for pattern, topic in KEYWORD_CATEGORY_RULES:
        if re.search(pattern, full_text):
            return topic

    return 'economy'  # 기본값: 신뢰도 높은 금융/경제 테마


def get_premium_stock_image(title, text="", category=""):
    """
    기사 내용에 맞는 초고화질 저작권 프리 스톡 이미지를 선별 반환.
    - 현대차 관련 기사일 경우 고화질 AI 현대차 이미지 우선 매칭
    - 동일 기사에는 항상 일관된 이미지가 선택되도록 제목 해시값 활용
    """
    full_text = f"{title} {category} {text[:300]}".lower()
    
    # 현대차 직접 연관 기사면 AI 생성 법적 안심 현대차 이미지 직결
    if '현대차' in full_text or '현대자동차' in full_text:
        return '/static/img/ai/hyundai_car.jpg'

    topic = detect_article_topic(title, text, category)
    if not topic or topic not in PREMIUM_STOCK_IMAGES:
        topic = 'economy'

    images = PREMIUM_STOCK_IMAGES[topic]
    # 기사 제목 기반 해시 인덱싱 -> 동일 기사는 항상 동일한 고급 이미지 유지
    idx = int(hashlib.md5(title.encode('utf-8')).hexdigest(), 16) % len(images)
    return images[idx]


def process_image_safeguard(image_url, base_dir="static/cache_img"):
    """
    원본 보도 사진을 다운로드하여 저작권 디지털 지문(EXIF)을 제거하고
    미세 보정 및 브랜드 워터마크를 합성하여 완전히 새로운 파일로 로컬 저장
    """
    if not image_url or not image_url.startswith('http'):
        return image_url

    try:
        os.makedirs(base_dir, exist_ok=True)
        img_hash = hashlib.md5(image_url.encode('utf-8')).hexdigest()
        out_filename = f"safe_{img_hash[:16]}.jpg"
        out_path = os.path.join(base_dir, out_filename)

        # 이미 가공된 파일이 있으면 즉시 캐시 반환
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            return f"/{base_dir}/{out_filename}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Referer': image_url
        }
        resp = requests.get(image_url, headers=headers, timeout=4)
        if resp.status_code != 200 or len(resp.content) < 500:
            return image_url

        # Pillow로 이미지 로드 (EXIF는 메모리 로드 시 자동 분리됨)
        img = Image.open(BytesIO(resp.content))
        if img.mode != 'RGB':
            img = img.convert('RGB')

        w, h = img.size
        # 1. 미세 크롭 (상하좌우 1% 잘라내어 구도 해시 변경)
        crop_x = int(w * 0.01)
        crop_y = int(h * 0.01)
        if crop_x > 0 and crop_y > 0 and w > 100 and h > 100:
            img = img.crop((crop_x, crop_y, w - crop_x, h - crop_y))
            w, h = img.size

        # 2. 미세 색조 및 선명도 보정 (+3% Contrast, +2% Color)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.03)
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.02)

        # 3. 우측 하단 세련된 뉴스NOW 브랜드 워터마크 오버레이
        draw = ImageDraw.Draw(img)
        badge_text = "뉴스NOW AI"
        badge_w, badge_h = 80, 22
        pad_r, pad_b = 12, 12
        x1 = w - badge_w - pad_r
        y1 = h - badge_h - pad_b
        x2 = w - pad_r
        y2 = h - pad_b

        # 반투명 다크 뱃지 박스
        draw.rounded_rectangle([x1, y1, x2, y2], radius=4, fill=(15, 23, 42, 180))
        draw.text((x1 + 8, y1 + 3), badge_text, fill=(255, 255, 255))

        # EXIF 없이 깨끗한 JPEG로 압축 저장
        img.save(out_path, 'JPEG', quality=88, optimize=True)
        return f"/{base_dir}/{out_filename}"

    except Exception as e:
        # 가공 중 에러 발생 시 원본 이미지 유지
        return image_url
