import os
import sys
import io
import time
import socket
import webbrowser
import threading
import feedparser
import requests
import json
import html
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, abort, Response
from bs4 import BeautifulSoup
from datetime import datetime
import re

# Windows 인코딩 강제 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.secret_key = 'news_now_secret_2026_!@#'

# ============================================================
# 관리자 설정 (비밀번호 변경 가능)
# ============================================================
ADMIN_PASSWORD = 'admin1234'

# ============================================================
# RSS 피드 설정 파일
# ============================================================
FEEDS_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'feeds_config.json')
SITE_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'site_config.json')

DEFAULT_SITE_CONFIG = {
    "ticker": {
        "enabled": True,
        "speed": 35,
        "badge": "🔴 실시간 이슈",
        "items": [
            "📢 [속보] 실시간 주요 뉴스 및 증권·연예 속보를 확인하세요",
            "📈 코스피·코스닥 증권 시황 및 오늘의 주요 종목 분석",
            "🎬 연예가 핫이슈 & 방송·스타 단독 보도 실시간 업데이트",
            "⚡ 실시간 국내외 언론사 속보를 가장 빠르고 정확하게 전달합니다"
        ]
    },
    "ads": {
        "left": {
            "enabled": True,
            "mode": "coupang",
            "coupang_id": 1026359,
            "tracking_code": "AF3197388",
            "sub_id": "dortm111",
            "width": 200,
            "height": 600,
            "custom_html": ""
        },
        "right": {
            "enabled": True,
            "mode": "coupang",
            "coupang_id": 1026359,
            "tracking_code": "AF3197388",
            "sub_id": "dortm111",
            "width": 200,
            "height": 600,
            "custom_html": ""
        },
        "center": {
            "enabled": True,
            "mode": "coupang",
            "coupang_id": 1026241,
            "tracking_code": "AF3197388",
            "sub_id": "dortm111",
            "width": 680,
            "height": 140,
            "custom_html": ""
        },
        "popup": {
            "enabled": False,
            "mode": "coupang",
            "coupang_id": 1026359,
            "tracking_code": "AF3197388",
            "sub_id": "dortm111",
            "delay": 2,
            "interval_minutes": 5,
            "close_delay": 3,
            "width": 300,
            "height": 300,
            "custom_html": ""
        }
    }
}

def load_site_config():
    if os.path.exists(SITE_CONFIG_FILE):
        try:
            with open(SITE_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_SITE_CONFIG

def save_site_config(config):
    with open(SITE_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

DEFAULT_RSS_FEEDS = {
    "전체": [
        {"name": "연합뉴스", "url": "https://www.yna.co.kr/rss/news.xml", "logo": "🔴", "enabled": True},
        {"name": "YTN", "url": "https://www.ytn.co.kr/rss/allnews.xml", "logo": "🟠", "enabled": True},
        {"name": "MBC", "url": "https://imnews.imbc.com/rss/news/news_00.xml", "logo": "🔵", "enabled": True},
        {"name": "KBS", "url": "https://news.kbs.co.kr/rss/news/news_main.xml", "logo": "🟢", "enabled": True},
        {"name": "SBS", "url": "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=00&plink=RSSREADER", "logo": "🟡", "enabled": True},
        {"name": "조선일보", "url": "https://www.chosun.com/arc/outboundfeeds/rss/", "logo": "⚫", "enabled": True},
        {"name": "중앙일보", "url": "https://rss.joins.com/joins_news_list.xml", "logo": "🟤", "enabled": True},
        {"name": "한겨레", "url": "https://www.hani.co.kr/rss/", "logo": "🔷", "enabled": True},
        {"name": "경향신문", "url": "https://www.khan.co.kr/rss/rssdata/total_news.xml", "logo": "🔶", "enabled": True},
        {"name": "동아일보", "url": "https://rss.donga.com/total.xml", "logo": "⭕", "enabled": True},
        {"name": "매일경제", "url": "https://www.mk.co.kr/rss/40300001/", "logo": "💹", "enabled": True},
        {"name": "한국경제", "url": "https://www.hankyung.com/feed/all-news", "logo": "📈", "enabled": True},
    ],
    "정치": [
        {"name": "연합뉴스 정치", "url": "https://www.yna.co.kr/rss/politics.xml", "logo": "🔴", "enabled": True},
        {"name": "조선일보 정치", "url": "https://www.chosun.com/arc/outboundfeeds/rss/category/politics/", "logo": "⚫", "enabled": True},
        {"name": "한겨레 정치", "url": "https://www.hani.co.kr/rss/politics/", "logo": "🔷", "enabled": True},
        {"name": "경향신문 정치", "url": "https://www.khan.co.kr/rss/rssdata/politic_news.xml", "logo": "🔶", "enabled": True},
        {"name": "동아 정치", "url": "https://rss.donga.com/politics.xml", "logo": "⭕", "enabled": True},
    ],
    "경제": [
        {"name": "매일경제", "url": "https://www.mk.co.kr/rss/40300001/", "logo": "💹", "enabled": True},
        {"name": "한국경제", "url": "https://www.hankyung.com/feed/economy", "logo": "📈", "enabled": True},
        {"name": "연합뉴스 경제", "url": "https://www.yna.co.kr/rss/economy.xml", "logo": "🔴", "enabled": True},
        {"name": "머니투데이", "url": "https://news.mt.co.kr/mtview/newsList.rss", "logo": "💰", "enabled": True},
        {"name": "헤럴드경제", "url": "https://biz.heraldcorp.com/rss", "logo": "📊", "enabled": True},
    ],
    "부동산": [
        {"name": "매일경제 부동산", "url": "https://www.mk.co.kr/rss/50300009/", "logo": "🏢", "enabled": True},
        {"name": "동아 부동산", "url": "https://rss.donga.com/economy.xml", "logo": "⭕", "enabled": True},
        {"name": "SBS 부동산/경제", "url": "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=02&plink=RSSREADER", "logo": "🏦", "enabled": True},
        {"name": "경향 부동산/경제", "url": "https://www.khan.co.kr/rss/rssdata/economy_news.xml", "logo": "🔶", "enabled": True},
        {"name": "한겨레 경제/부동산", "url": "https://www.hani.co.kr/rss/economy/", "logo": "🔷", "enabled": True},
    ],
    "증권": [
        {"name": "동아 증권/경제", "url": "https://rss.donga.com/economy.xml", "logo": "📈", "enabled": True},
        {"name": "아시아경제 증권", "url": "https://www.asiae.co.kr/rss/stock.htm", "logo": "💹", "enabled": True},
        {"name": "경향 경제/증권", "url": "https://www.khan.co.kr/rss/rssdata/economy_news.xml", "logo": "🔶", "enabled": True},
        {"name": "한겨레 경제/금융", "url": "https://www.hani.co.kr/rss/economy/", "logo": "🔷", "enabled": True},
        {"name": "SBS 경제/증권", "url": "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=02&plink=RSSREADER", "logo": "🏦", "enabled": True},
    ],
    "연예": [
        {"name": "동아 연예", "url": "https://rss.donga.com/entertainment.xml", "logo": "🎬", "enabled": True},
        {"name": "SBS 연예", "url": "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=08&plink=RSSREADER", "logo": "⭐", "enabled": True},
        {"name": "경향 연예/문화", "url": "https://www.khan.co.kr/rss/rssdata/culture_news.xml", "logo": "🔶", "enabled": True},
        {"name": "한겨레 연예/문화", "url": "https://www.hani.co.kr/rss/culture/", "logo": "🔷", "enabled": True},
    ],
    "사회": [
        {"name": "연합뉴스 사회", "url": "https://www.yna.co.kr/rss/society.xml", "logo": "🔴", "enabled": True},
        {"name": "조선일보 사회", "url": "https://www.chosun.com/arc/outboundfeeds/rss/category/national/", "logo": "⚫", "enabled": True},
        {"name": "한겨레 사회", "url": "https://www.hani.co.kr/rss/society/", "logo": "🔷", "enabled": True},
        {"name": "경향 사회", "url": "https://www.khan.co.kr/rss/rssdata/society_news.xml", "logo": "🔶", "enabled": True},
        {"name": "동아 사회", "url": "https://rss.donga.com/society.xml", "logo": "⭕", "enabled": True},
    ],
    "IT/과학": [
        {"name": "한겨레 과학", "url": "https://www.hani.co.kr/rss/science/", "logo": "🔷", "enabled": True},
        {"name": "경향 과학", "url": "https://www.khan.co.kr/rss/rssdata/science_news.xml", "logo": "🔶", "enabled": True},
        {"name": "동아 과학", "url": "https://rss.donga.com/science.xml", "logo": "⭕", "enabled": True},
        {"name": "조선 IT", "url": "https://www.chosun.com/arc/outboundfeeds/rss/category/technology/", "logo": "⚫", "enabled": True},
        {"name": "매일경제 IT", "url": "https://www.mk.co.kr/rss/30100041/", "logo": "💹", "enabled": True},
    ],
    "스포츠": [
        {"name": "연합뉴스 스포츠", "url": "https://www.yna.co.kr/rss/sports.xml", "logo": "⚽", "enabled": True},
        {"name": "MBC 스포츠", "url": "https://imnews.imbc.com/rss/news/news_01.xml", "logo": "🔵", "enabled": True},
        {"name": "KBS 스포츠", "url": "https://news.kbs.co.kr/rss/sports/news_sports.xml", "logo": "🟢", "enabled": True},
        {"name": "조선 스포츠", "url": "https://www.chosun.com/arc/outboundfeeds/rss/category/sports/", "logo": "⚫", "enabled": True},
    ],
    "세계": [
        {"name": "연합뉴스 국제", "url": "https://www.yna.co.kr/rss/international.xml", "logo": "🔴", "enabled": True},
        {"name": "한겨레 국제", "url": "https://www.hani.co.kr/rss/international/", "logo": "🔷", "enabled": True},
        {"name": "경향 국제", "url": "https://www.khan.co.kr/rss/rssdata/world_news.xml", "logo": "🔶", "enabled": True},
        {"name": "조선 국제", "url": "https://www.chosun.com/arc/outboundfeeds/rss/category/international/", "logo": "⚫", "enabled": True},
    ],
    "문화": [
        {"name": "연합뉴스 문화", "url": "https://www.yna.co.kr/rss/culture.xml", "logo": "🎭", "enabled": True},
        {"name": "한겨레 문화", "url": "https://www.hani.co.kr/rss/culture/", "logo": "🔷", "enabled": True},
        {"name": "조선 문화", "url": "https://www.chosun.com/arc/outboundfeeds/rss/category/culture-life/", "logo": "⚫", "enabled": True},
        {"name": "경향 문화", "url": "https://www.khan.co.kr/rss/rssdata/culture_news.xml", "logo": "🔶", "enabled": True},
        {"name": "동아 문화", "url": "https://rss.donga.com/culture.xml", "logo": "⭕", "enabled": True},
        {"name": "KBS 문화", "url": "https://news.kbs.co.kr/rss/culture/news_culture.xml", "logo": "🟢", "enabled": True},
    ],
}


def load_feeds_config():
    if os.path.exists(FEEDS_CONFIG_FILE):
        try:
            with open(FEEDS_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_RSS_FEEDS

def save_feeds_config(config):
    with open(FEEDS_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# ============================================================
# RSS 수집 유틸
# ============================================================
def clean_html(text):
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', str(text))
    clean = html.unescape(clean)
    clean = clean.replace('&nbsp;', ' ')
    return clean.strip()

IMAGE_CACHE = {}

# 언론사 기본 로고 또는 플레이스홀더 이미지 블랙리스트
BAD_IMG_KEYWORDS = [
    'facebook_mknews', 'mai-property-main-img', 'l_mlogoky', 'ic_mai_w', 'trans_30x13',
    'logo.png', 'logo.jpg', 'default_thumb', 'blank.gif', 'spacer.gif', 'icon'
]

# 사진이 전혀 없는 부동산 단신 기사를 위한 고화질 아파트/주거 단지 테마 이미지 풀
REALESTATE_FALLBACK_IMAGES = [
    'https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?w=600&auto=format&fit=crop&q=80',  # 아파트 단지 전경
    'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=600&auto=format&fit=crop&q=80',  # 현대식 고층 주거/빌딩
    'https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=600&auto=format&fit=crop&q=80',  # 고급 주거 단지
    'https://images.unsplash.com/photo-1560518883-ce09059eeffa?w=600&auto=format&fit=crop&q=80',  # 주택/부동산
    'https://images.unsplash.com/photo-1570129477492-45c003edd2be?w=600&auto=format&fit=crop&q=80',  # 쾌적한 주거 타운
]

def is_invalid_image(img_url):
    """유효하지 않은 이미지(비어있거나 언론사 로고 플레이트)인지 검사"""
    if not img_url or not str(img_url).startswith('http'):
        return True
    low = str(img_url).lower()
    return any(bad in low for bad in BAD_IMG_KEYWORDS)

def get_og_image(url, category=None):
    """기사 웹페이지에서 실제 기사 사진을 정밀 추출 (한국경제, 매일경제, 경향신문 등 특화 파싱)"""
    if not url or url == '#' or not str(url).startswith('http'):
        return ''
    if url in IMAGE_CACHE:
        return IMAGE_CACHE[url]
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=4.0)
        resp_text = resp.text

        img_url = ''

        # 1) 한국경제 (hankyung.com) 본문 이미지 정밀 패턴 검색
        if 'hankyung.com' in url:
            hk_matches = re.findall(r'https?://img\.hankyung\.com/photo/[0-9a-zA-Z_/.]+\.(?:jpg|png|jpeg|webp)', resp_text)
            if hk_matches:
                img_url = hk_matches[0]

        # 2) 매일경제 (mk.co.kr) 실제 기사 사진 정밀 패턴 검색
        elif 'mk.co.kr' in url:
            mk_matches = re.findall(r'https?://(?:pimg|wimg)\.mk\.co\.kr/news/cms/[0-9a-zA-Z_/.]+\.(?:jpg|png|jpeg|webp)', resp_text)
            if mk_matches:
                img_url = mk_matches[0]

        # 3) 일반 og:image 태그 추출
        if not img_url:
            m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', resp_text, re.I)
            if not m:
                m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', resp_text, re.I)
            candidate = m.group(1).strip() if m else ''
            if candidate and not is_invalid_image(candidate):
                img_url = html.unescape(candidate)

        # 4) 본문 컨테이너 이미지 추출 (BeautifulSoup)
        if not img_url:
            soup = BeautifulSoup(resp_text, 'html.parser')
            body = (
                soup.find('div', id='articletxt') or 
                soup.find('div', class_='article-body') or
                soup.find('div', id='article_body') or
                soup.find('div', class_='news_cnt_detail_wrap') or
                soup.find('div', class_='art_txt') or
                soup.find('div', id='articleBody') or
                soup.find('div', class_='article_view')
            )
            if body:
                for im in body.find_all('img'):
                    src = im.get('src') or im.get('data-src') or ''
                    if src and not is_invalid_image(src):
                        img_url = src
                        break

        # 5) 사진이 전혀 없는 부동산 단신(시세) 기사를 위한 고화질 테마 이미지 매칭
        if not img_url and category == '부동산':
            idx = abs(hash(url)) % len(REALESTATE_FALLBACK_IMAGES)
            img_url = REALESTATE_FALLBACK_IMAGES[idx]

        IMAGE_CACHE[url] = img_url
        return img_url
    except Exception:
        # 에러 시 부동산 단신일 경우 폴백 이미지 적용
        if category == '부동산':
            idx = abs(hash(url)) % len(REALESTATE_FALLBACK_IMAGES)
            fallback = REALESTATE_FALLBACK_IMAGES[idx]
            IMAGE_CACHE[url] = fallback
            return fallback
        IMAGE_CACHE[url] = ''
        return ''

def get_image_from_entry(entry):
    img = ''
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            if media.get('url'):
                img = media['url']
                break
    if not img and hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        img = entry.media_thumbnail[0].get('url', '')
    if not img and hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image'):
                img = enc.get('href', '')
                break
    if not img:
        content = ''
        if hasattr(entry, 'content') and entry.content:
            content = entry.content[0].get('value', '')
        elif hasattr(entry, 'summary'):
            content = entry.summary or ''
        if content:
            soup = BeautifulSoup(content, 'html.parser')
            im_tag = soup.find('img')
            if im_tag and im_tag.get('src'):
                img = im_tag['src']

    if is_invalid_image(img):
        return ''
    return img

def parse_date(entry):
    try:
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            dt = datetime(*entry.published_parsed[:6])
            return dt.strftime('%m.%d %H:%M')
    except:
        pass
    try:
        if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            dt = datetime(*entry.updated_parsed[:6])
            return dt.strftime('%m.%d %H:%M')
    except:
        pass
    return datetime.now().strftime('%m.%d %H:%M')

def fetch_rss(feed_url, source_name, logo, max_items=15):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(feed_url, headers=headers, timeout=8)
        resp.encoding = resp.apparent_encoding or 'utf-8'
        feed = feedparser.parse(resp.text)
        items = []
        for entry in feed.entries[:max_items]:
            title = clean_html(getattr(entry, 'title', ''))
            link = getattr(entry, 'link', '#')
            summary = clean_html(getattr(entry, 'summary', '') or getattr(entry, 'description', ''))
            if len(summary) > 150:
                summary = summary[:150] + '...'
            image = get_image_from_entry(entry)
            pub_date = parse_date(entry)
            if title:
                items.append({
                    'title': title,
                    'link': link,
                    'summary': summary,
                    'image': image,
                    'date': pub_date,
                    'source': source_name,
                    'logo': logo,
                })
        return items
    except Exception as e:
        print(f"[RSS Error] {source_name}: {e}")
        return []

# ============================================================
# 관리자 체크
# ============================================================
def is_admin():
    return session.get('is_admin', False)

# ============================================================
# 라우트 - 일반 사용자
# ============================================================
@app.route('/')
def index():
    feeds = load_feeds_config()
    categories = list(feeds.keys())
    site_cfg = load_site_config()
    return render_template('index.html', categories=categories, site_config=site_cfg)

@app.route('/api/site_config')
def api_site_config():
    """클라이언트에서 사이트 설정(광고·티커) 가져오기"""
    cfg = load_site_config()
    return jsonify({'success': True, 'config': cfg})

@app.route('/api/image_proxy')
def api_image_proxy():
    """외부 언론사 CDN의 리퍼러/핫링크 차단 우회 및 안정적 이미지 제공 프록시"""
    img_url = request.args.get('url', '')
    if not img_url or not img_url.startswith('http'):
        return abort(400)
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': img_url
        }
        resp = requests.get(img_url, headers=headers, timeout=6)
        if resp.status_code == 200:
            content_type = resp.headers.get('Content-Type', 'image/jpeg')
            return Response(resp.content, mimetype=content_type, headers={
                'Cache-Control': 'public, max-age=86400'
            })
        return abort(resp.status_code)
    except Exception:
        return abort(404)

@app.route('/api/rss')
def api_rss():
    category = request.args.get('category', '전체')
    max_per_feed = int(request.args.get('max', 15))
    feeds_config = load_feeds_config()
    feeds = [f for f in feeds_config.get(category, feeds_config.get('전체', [])) if f.get('enabled', True)]

    all_news = []
    results = {}

    def fetch_worker(feed_info, key):
        items = fetch_rss(feed_info['url'], feed_info['name'], feed_info['logo'], max_per_feed)
        results[key] = items

    threads = []
    for i, feed_info in enumerate(feeds):
        t = threading.Thread(target=fetch_worker, args=(feed_info, i))
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=12)
    for i in range(len(feeds)):
        all_news.extend(results.get(i, []))

    # 누락되었거나 로고 이미지로 잘못 잡힌 기사(한국경제, 매일경제, 경향신문 등) 정밀 자동 보완
    missing_items = [item for item in all_news if is_invalid_image(item.get('image')) and item.get('link')]
    if missing_items:
        def fill_img(item):
            img = get_og_image(item['link'], category=category)
            if img:
                item['image'] = img

        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(fill_img, missing_items))

    response = jsonify({'success': True, 'category': category, 'count': len(all_news), 'news': all_news})
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

def get_live_ticker_items(limit=8):
    """실제 RSS 뉴스에서 실시간 주요 이슈/속보 헤드라인과 원문 링크를 자동으로 추출"""
    feeds_config = load_feeds_config()
    candidate_feeds = []
    for cat in ['전체', '부동산', '증권', '연예', '정치', '경제', '사회']:
        for f in feeds_config.get(cat, []):
            if f.get('enabled', True):
                candidate_feeds.append((f, cat))
                if len(candidate_feeds) >= 12:
                    break
        if len(candidate_feeds) >= 12:
            break

    collected_items = []
    for f, cat in candidate_feeds:
        try:
            items = fetch_rss(f['url'], f['name'], f.get('logo', '📰'), max_items=2)
            for it in items:
                title = it.get('title', '').strip()
                link = it.get('link', '#')
                if title and len(title) > 6 and title not in [c['title'] for c in collected_items]:
                    collected_items.append({'title': title, 'link': link, 'cat': cat, 'source': it.get('source', '')})
        except:
            continue

    if not collected_items:
        return [
            {"title": "📢 [속보] 실시간 주요 언론사 종합 뉴스 속보를 전달합니다", "link": "#"},
            {"title": "📈 [경제] 코스피·코스닥 증권 시황 및 주요 종목 실시간 동향", "link": "#"},
            {"title": "🎬 [연예] 오늘의 핫이슈 & 방송·스타 소식 실시간 업데이트", "link": "#"}
        ]

    cat_emoji = {
        '전체': '🔥 [속보]',
        '부동산': '🏢 [부동산]',
        '증권': '📈 [증권]',
        '연예': '🎬 [연예]',
        '정치': '⚡ [정치]',
        '경제': '📊 [경제]',
        '사회': '🌊 [사회]'
    }

    ticker_results = []
    for item in collected_items[:limit]:
        title = item['title']
        link = item.get('link', '#')
        prefix = cat_emoji.get(item['cat'], '📢 [이슈]')
        if title.startswith('[') or title.startswith('('):
            display_title = f"🔥 {title}"
        else:
            display_title = f"{prefix} {title}"
        ticker_results.append({'title': display_title, 'link': link})

    return ticker_results

# ============================================================
# 라우트 - 관리자
# ============================================================
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if is_admin():
        return redirect(url_for('admin_dashboard'))
    error = None
    if request.method == 'POST':
        pw = request.form.get('password', '')
        if pw == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            error = '비밀번호가 틀렸습니다.'
    return render_template('admin_login.html', error=error)

@app.route('/admin/dashboard')
def admin_dashboard():
    if not is_admin():
        return redirect(url_for('admin_login'))
    feeds_config = load_feeds_config()
    return render_template('admin_dashboard.html', feeds=feeds_config)

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))

@app.route('/admin/api/feeds', methods=['GET'])
def admin_get_feeds():
    if not is_admin():
        abort(403)
    return jsonify({'success': True, 'feeds': load_feeds_config()})

@app.route('/admin/api/feeds', methods=['POST'])
def admin_save_feeds():
    if not is_admin():
        abort(403)
    data = request.get_json()
    if data:
        save_feeds_config(data)
        return jsonify({'success': True, 'message': '저장되었습니다.'})
    return jsonify({'success': False, 'message': '데이터 오류'})

@app.route('/admin/api/feeds/add', methods=['POST'])
def admin_add_feed():
    if not is_admin():
        abort(403)
    data = request.get_json()
    category = data.get('category')
    feed = data.get('feed')
    if not category or not feed:
        return jsonify({'success': False, 'message': '필수값 없음'})
    config = load_feeds_config()
    if category not in config:
        config[category] = []
    config[category].append(feed)
    save_feeds_config(config)
    return jsonify({'success': True})

@app.route('/admin/api/feeds/delete', methods=['POST'])
def admin_delete_feed():
    if not is_admin():
        abort(403)
    data = request.get_json()
    category = data.get('category')
    idx = data.get('index')
    config = load_feeds_config()
    if category in config and 0 <= idx < len(config[category]):
        config[category].pop(idx)
        save_feeds_config(config)
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': '해당 피드 없음'})

@app.route('/admin/api/feeds/toggle', methods=['POST'])
def admin_toggle_feed():
    if not is_admin():
        abort(403)
    data = request.get_json()
    category = data.get('category')
    idx = data.get('index')
    config = load_feeds_config()
    if category in config and 0 <= idx < len(config[category]):
        config[category][idx]['enabled'] = not config[category][idx].get('enabled', True)
        save_feeds_config(config)
        return jsonify({'success': True, 'enabled': config[category][idx]['enabled']})
    return jsonify({'success': False})

@app.route('/admin/api/test_rss', methods=['POST'])
def admin_test_rss():
    if not is_admin():
        abort(403)
    data = request.get_json()
    url = data.get('url', '')
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=8)
        feed = feedparser.parse(resp.text)
        count = len(feed.entries)
        title = feed.feed.get('title', '알 수 없음')
        return jsonify({'success': True, 'feed_title': title, 'item_count': count})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# ---- 사이트 설정 (광고·티커) ----
@app.route('/admin/api/site_config', methods=['GET'])
def admin_get_site_config():
    if not is_admin(): abort(403)
    return jsonify({'success': True, 'config': load_site_config()})

@app.route('/admin/api/site_config', methods=['POST'])
def admin_save_site_config():
    if not is_admin(): abort(403)
    data = request.get_json()
    if data:
        save_site_config(data)
        return jsonify({'success': True, 'message': '설정이 저장되었습니다.'})
    return jsonify({'success': False, 'message': '데이터 오류'})

@app.route('/admin/api/ticker/fetch_live', methods=['GET'])
def admin_fetch_live_ticker():
    if not is_admin(): abort(403)
    try:
        items = get_live_ticker_items(limit=8)
        return jsonify({'success': True, 'items': items})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'items': []})

# ============================================================
# 포트 / 실행
# ============================================================
def find_free_port(start=5100):
    for port in range(start, start + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    return start

def open_browser(port):
    time.sleep(1.5)
    webbrowser.open(f'http://127.0.0.1:{port}')

if __name__ == '__main__':
    env_port = os.environ.get('PORT')
    if env_port:
        port = int(env_port)
        host = '0.0.0.0'
        is_cloud = True
    else:
        port = find_free_port(5100)
        host = '0.0.0.0'
        is_cloud = False

    print('\n' + '='*60)
    print('  [NEWS NOW] RSS 뷰어 실행 중...')
    print(f'  접속 주소: http://127.0.0.1:{port}')
    print(f'  관리자: http://127.0.0.1:{port}/admin')
    print('  종료하려면 이 창을 닫으세요.')
    print('='*60 + '\n')

    if not is_cloud:
        threading.Thread(target=open_browser, args=(port,), daemon=True).start()

    app.run(host=host, port=port, debug=False)
