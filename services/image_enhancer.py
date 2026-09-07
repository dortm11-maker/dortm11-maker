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
# ==============================================================================
# 분야별 프리미엄 4K급 상업용 무료(Unsplash Verified) 스톡 이미지 카탈로그 (100종 이상 다채로운 구성)
# ==============================================================================
PREMIUM_STOCK_IMAGES = {
    # 1. 부동산 (아파트, 주택, 재개발, 분양, 청약, 건축, 인테리어)
    'realestate': [
        'https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1577495508048-b635879837f1?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1515263487990-61b07816b324?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1503387762-592deb58ef4e?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1560518883-ce09059eeffa?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1570129477492-45c003edd2be?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1582407947304-fd86f028f716?auto=format&fit=crop&w=1200&q=85'
    ],

    # 2. 증권 / 주식 (코스피, 코스닥, 트레이딩, 캔들차트, 반도체, 금융 시장)
    'stock': [
        'https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1642543492481-44e81e3914a7?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1559526324-4b87b5e36e44?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1535320903710-d993d3d77d29?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1612178991541-b48cc8e92a4d?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1507679799987-c73779587ccf?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1628348068343-c6a848d2b6dd?auto=format&fit=crop&w=1200&q=85'
    ],

    # 3. 경제 / 금융 (금리, 환율, 통화, 무역, 물가, 은행, 거시경제)
    'economy': [
        'https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1579532537598-459ecdaf39cc?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1563986768609-322da13575f3?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1542744173-8e7e53415bb0?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1450133064473-71024230f91b?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1559526324-593bc073d938?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1551836022-d5d88e9218df?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1520607162513-77705c0f0d4a?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1518458028785-8fbcd101ebb9?auto=format&fit=crop&w=1200&q=85'
    ],

    # 4. IT / 과학 / AI / 디지털 (인공지능, 빅데이터, 클라우드, 로봇)
    'tech': [
        'https://images.unsplash.com/photo-1558494949-ef010cbdcc31?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1531482615713-2afd69097998?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1519389950473-47ba0277781c?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1550751827-4bd374c3f58b?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=1200&q=85'
    ],

    # 5. 법조 / 정책 / 국회 / 공공 (법원, 국회, 정부, 외교, 공공정책)
    'law_policy': [
        'https://images.unsplash.com/photo-1589829545856-d10d557cf95f?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1541872703-74c5e44368f9?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1521791136064-7986c2920216?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1575320181282-9afab399332c?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1540910419892-4a36d2c3266c?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1568992687947-868a62a9f521?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1497215728101-856f4ea42174?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1556761175-5973dc0f32e7?auto=format&fit=crop&w=1200&q=85'
    ],

    # 6. 자동차 / 모빌리티 / 운송 (현대차, 전기차, 모터스, 도로)
    'auto': [
        '/static/img/ai/hyundai_car.jpg',
        'https://images.unsplash.com/photo-1617814076367-b759c7d7e738?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1552519507-da3b142c6e3d?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1605559424843-9e4c228bf1c2?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1563720223185-11003d516935?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1494976388531-d1058494cdd8?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1580273916550-e323be2ae537?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1549399542-7e3f8b79c341?auto=format&fit=crop&w=1200&q=85'
    ],

    # 7. 통신 / 모바일 / 디지털 라이프 (통신사, 5G, 스마트폰, 플랫폼)
    'telecom': [
        'https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1556656793-08538906a9f8?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1519389950473-47ba0277781c?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1563986768609-322da13575f3?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1512941937669-90a1b58e7e9c?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1581291518857-4e27b48ff24e?auto=format&fit=crop&w=1200&q=85'
    ],

    # 8. 유통 / 쇼핑 / 생활 / 명절 (마트, 백화점, 추석선물, 소비, 외식)
    'shopping_life': [
        'https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1513151233558-d860c5398176?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1578916171728-46686eac8d58?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1526178613552-2b45c6c302f0?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1441986300917-64674bd600d8?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1555396273-367ea4eb4db5?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1506617420156-8e4536971650?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1472851294608-062f824d29cc?auto=format&fit=crop&w=1200&q=85'
    ],

    # 9. 사회 / 환경 / 날씨 / 도시 (사회이슈, 날씨, 환경, 복지, 시민생활)
    'society': [
        'https://images.unsplash.com/photo-1480714378408-67cf0d13bc1b?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1517245386807-bb43f82c33c4?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1514565131-fce0801e5785?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1449824913935-59a10b8d2000?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1488521787991-ed7bbaae773c?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1509099836639-18ba1795216d?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1469474968028-56623f02e42e?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1501854140801-50d01698950b?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1532938911079-1b06ac7ceec7?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1516738901171-8eb4fc13bd20?auto=format&fit=crop&w=1200&q=85'
    ],

    # 10. 스포츠 (축구, 야구, 농구, 골프, 올림픽, 월드컵, 훈련, 경기)
    'sports': [
        'https://images.unsplash.com/photo-1579952363873-27f3bade9f55?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1461896836934-ffe607ba8211?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1574629810360-7efbbe195018?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1431324155629-1a6deb1dec8d?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1540747913346-19e32dc3e97e?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1534438327276-14e5300c3a48?auto=format&fit=crop&w=1200&q=85'
    ],

    # 11. 연예 / 문화 / 예술 (공연, 콘서트, 영화, 드라마, 스타, 음악, 전시)
    'entertainment': [
        'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1492684223066-81342ee5ff30?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1501386761578-eac5c94b800a?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1485846234645-a62644f84728?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1460723237483-7a6dc9d0b212?auto=format&fit=crop&w=1200&q=85',
        'https://images.unsplash.com/photo-1518972559570-7cc1309f3229?auto=format&fit=crop&w=1200&q=85'
    ]
}

NEWS_STOCK_CATALOG = PREMIUM_STOCK_IMAGES

# 키워드 규칙 매핑 테이블 (확장)
KEYWORD_CATEGORY_RULES = [
    # 사건/사고/경찰/수사/시신 키워드 (사회 최우선)
    (r'시신|살인|피의자|검거|체포|구속|경찰|수사|용의자|사건|참사|범죄|사기|도주|은닉|냉동창고', 'society'),
    # 자동차/현대차/모빌리티 키워드
    (r'현대차|현대자동차|기아|자동차|완성차|제네시스|아이오닉|전기차|팰리세이드|아반떼|투싼|카니발|쏘나타|그랜저|모터스|파업.*생산|차량|모빌리티', 'auto'),
    # 스포츠 키워드 (경기 단독 매칭 금지)
    (r'손흥민|토트넘|축구|야구|프로야구|kbo|월드컵|올림픽|골프|농구|배구|(?:축구|야구|농구|배구|골프|올림픽|월드컵|리그)\s*경기|경기장|출전\s*경기|선수|감독|리그|홈런|득점|챔피언|우승|메달', 'sports'),
    # 연예/문화 키워드
    (r'bts|아이돌|가수|배우|드라마|영화|예능|방송|음원|콘서트|페스티벌|뮤지컬|전시|앨범|컴백|스타|연예|출연|시청률', 'entertainment'),
    # 통신 / 모바일 / 통신사 키워드
    (r'lg유플러스|유플러스|sk텔레콤|skt|kt|통신사|5g|유플투쁠|멤버십|통신|요금제', 'telecom'),
    # 쇼핑 / 명절 / 추석 / 소비 / 유통 키워드
    (r'추석|명절|쇼핑|장보기|선물세트|외식|나들이|화담숲|할인|이마트|백화점|소비자|유통|마트|생필품|치킨|커피|식품', 'shopping_life'),
    # 부동산 키워드
    (r'부동산|아파트|분양|청약|전세|월세|매매|집값|주택|빌라|재개발|재건축|다세대|토지|오피스텔|건설|시행사|시공사|국토부|보증금|공동주택|단지', 'realestate'),
    # 증권 키워드
    (r'코스피|코스닥|증시|주식|주가|상장|공모주|배당|증권|펀드|etf|개미|외인|기관|매수|매도|반도체|하이닉스|삼성전자|엔비디아|나스닥|다우', 'stock'),
    # IT/과학 키워드
    (r'인공지능|ai|챗gpt|클라우드|빅데이터|소프트웨어|스마트폰|로봇|우주|양자|사이버|플랫폼|스타트업|서버|애플|구글', 'tech'),
    # 법조/재판/정치/정책 키워드
    (r'법원|법정|판결|소송|검찰|기소|변호사|대법원|헌법재판소|항소|구속영장|형사재판|민사소송|(?<![가-힣])재판(?![가-힣])|대통령|국회|여당|야당|의원|총선|정당|당대표|정부|청와대|외교|총리|장관|정책', 'law_policy'),
    # 경제/거시금융 키워드
    (r'경제|금리|환율|인플레|물가|한국은행|기준금리|수출|수입|무역|gdp|소비자물가|재정|국채|금융|은행|외환|고용|경기침체|유가|원자재', 'economy'),
    # 사회/환경 키워드
    (r'날씨|기상|태풍|폭우|미세먼지|환경|보건|의료|의사|병원|학교|교육|수능|소방|경찰|사고|교통|시민|복지|노인|청년', 'society')
]


def detect_article_topic(title, text="", category=""):
    """
    기사 제목, 본문, 카테고리를 종합 분석하여 가장 적합한 이미지 테마를 정밀 판별
    """
    full_text = f"{title} {category} {text[:300]}".lower()

    # 1-1. 사건 / 사고 / 경찰 / 수사 / 범죄 키워드 최우선 검출 (사회/법조)
    if re.search(r'시신|살인|피의자|검거|체포|구속|경찰|수사|용의자|사건|참사|범죄|사기|도주|은닉|냉동창고', full_text):
        return 'society'

    # 1. 현대차/완성차/자동차 키워드 최우선 검출
    if re.search(r'현대차|현대자동차|기아|자동차|완성차|제네시스|아이오닉|전기차|팰리세이드|아반떼|투싼|카니발|쏘나타|그랜저|파업.*생산', full_text):
        return 'auto'

    # 2. 스포츠 키워드 정밀 검출 ('경기' 단독 매칭 금지 -> 경기도, 경기침체 등 오인 방지)
    if re.search(r'손흥민|토트넘|축구|야구|프로야구|kbo|월드컵|올림픽|골프|농구|배구|(?:축구|야구|농구|배구|골프|올림픽|월드컵|리그)\s*경기|경기장|출전\s*경기|선수|감독|리그|홈런|득점|챔피언|우승|메달', full_text):
        return 'sports'

    # 3. 연예 / 문화 / 방송 키워드
    if re.search(r'bts|아이돌|가수|배우|드라마|영화|예능|방송|음원|콘서트|페스티벌|뮤지컬|전시|앨범|컴백|스타|연예|출연|시청률', full_text):
        return 'entertainment'

    # 4. 통신 / 모바일 우선 검출
    if re.search(r'lg유플러스|유플러스|sk텔레콤|skt|kt|통신사|유플투쁠|5g|요금제', full_text):
        return 'telecom'

    # 5. 명절 / 쇼핑 / 외식 우선 검출
    if re.search(r'추석|명절|쇼핑|장보기|선물세트|외식|나들이|화담숲|멤버십|할인|이마트|백화점|마트|치킨', full_text):
        return 'shopping_life'

    # 6. 명시적 카테고리 매핑
    category_map = {
        '부동산': 'realestate',
        '증권': 'stock',
        '경제': 'economy',
        'IT/과학': 'tech',
        'IT·과학': 'tech',
        '정치': 'law_policy',
        '사회': 'society',
        '스포츠': 'sports',
        '연예': 'entertainment',
        '문화': 'entertainment',
        '생활': 'shopping_life'
    }
    if category in category_map:
        return category_map[category]

    # 7. 키워드 규칙 정밀 탐색
    for pattern, topic in KEYWORD_CATEGORY_RULES:
        if re.search(pattern, full_text):
            return topic

    # 8. 기본 분산 풀 (제목 해시 기반으로 4대 대표 카테고리에 고르게 분산하여 중복 완화)
    h = int(hashlib.md5(title.encode('utf-8')).hexdigest(), 16)
    fallback_topics = ['economy', 'society', 'tech', 'stock', 'shopping_life']
    return fallback_topics[h % len(fallback_topics)]


def get_premium_stock_image(title, text="", category="", used_images=None):
    """
    기사 내용에 맞는 초고화질 저작권 프리 스톡 이미지를 선별 반환.
    - 현대차 관련 기사일 경우 고화질 AI 현대차 이미지 우선 매칭
    - used_images 세트를 활용하여 동일 페이지 내 이미지 중복을 원천 차단
    """
    full_text = f"{title} {category} {text[:300]}".lower()
    
    # 현대차 직접 연관 기사면 AI 생성 법적 안심 현대차 이미지 직결
    if '현대차' in full_text or '현대자동차' in full_text:
        return '/static/img/ai/hyundai_car.jpg'

    topic = detect_article_topic(title, text, category)
    if not topic or topic not in PREMIUM_STOCK_IMAGES:
        topic = 'economy'

    images = PREMIUM_STOCK_IMAGES[topic]
    h = int(hashlib.md5(title.encode('utf-8')).hexdigest(), 16)
    
    # used_images가 주어진 경우 (중복 방지 모드)
    if used_images is not None:
        # 1차: 해당 주제 내에서 아직 안 쓰인 이미지 찾기
        for offset in range(len(images)):
            cand = images[(h + offset) % len(images)]
            if cand not in used_images:
                used_images.add(cand)
                return cand
        
        # 2차: 전체 카탈로그 중 아직 안 쓰인 이미지 찾기
        for other_topic, other_imgs in PREMIUM_STOCK_IMAGES.items():
            for offset in range(len(other_imgs)):
                cand = other_imgs[(h + offset) % len(other_imgs)]
                if cand not in used_images:
                    used_images.add(cand)
                    return cand

    # 기본 해시 인덱싱
    idx = h % len(images)
    if used_images is not None:
        used_images.add(images[idx])
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
