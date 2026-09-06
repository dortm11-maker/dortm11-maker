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
from datetime import datetime, timedelta, timezone
import hashlib
import re
import urllib.parse

# Windows 인코딩 안전 설정
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.secret_key = 'news_now_secret_2026_!@#'

# ============================================================
# 관리자 설정 (비밀번호 변경 가능)
# ============================================================
ADMIN_PASSWORD = 'thfWlrgl12!@'

# ============================================================
# 실시간 방문자 & 투데이/토탈 통계 추적 엔진
# ============================================================
VISITOR_STATS_FILE = os.path.join(os.path.dirname(__file__), 'visitor_stats.json')
KST = timezone(timedelta(hours=9))

def get_kst_today_str():
    return datetime.now(KST).strftime('%Y-%m-%d')

class VisitorTracker:
    def __init__(self):
        self.lock = threading.Lock()
        self.active_users = {}   # {ip: last_active_timestamp}
        self.today_vids = set()  # 당일 고유 IP 집합
        self.visitor_logs = {}   # {ip: dict(ip, device, visit_count, first_seen, last_seen, last_seen_ts, last_page)}
        self.current_date = get_kst_today_str()
        self.total_uv = 0
        self.total_pv = 0
        self.daily = {}          # {date_str: {"uv": int, "pv": int}}
        self.ad_clicks = {
            'by_type_total': {'left': 0, 'right': 0, 'center': 0, 'popup': 0, 'link': 0, 'auto_redirect': 0},
            'by_type_today': {'left': 0, 'right': 0, 'center': 0, 'popup': 0, 'link': 0, 'auto_redirect': 0},
            'recent_logs': []
        }
        self.last_saved = time.time()
        self.load()

    def load(self):
        if os.path.exists(VISITOR_STATS_FILE):
            try:
                with open(VISITOR_STATS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.total_uv = data.get('total_uv', 0)
                    self.total_pv = data.get('total_pv', 0)
                    self.daily = data.get('daily', {})
                    self.visitor_logs = data.get('visitor_logs', {})
                    if 'ad_clicks' in data:
                        ac = data['ad_clicks']
                        if 'by_type_total' in ac:
                            self.ad_clicks = ac
                        else:
                            # 구버전 구조 마이그레이션
                            old_bt = ac.get('by_type', {})
                            self.ad_clicks = {
                                'by_type_total': dict(old_bt),
                                'by_type_today': dict(old_bt),
                                'recent_logs': ac.get('recent_logs', [])
                            }
            except Exception as e:
                print(f"[Stats] Load error: {e}")
        
        today = get_kst_today_str()
        self.current_date = today
        if today not in self.daily:
            self.daily[today] = {"uv": 0, "pv": 0}

    def save(self):
        try:
            saved_logs = dict(list(self.visitor_logs.items())[-100:])
            saved_ad_logs = self.ad_clicks.get('recent_logs', [])[-100:]
            data = {
                'total_uv': self.total_uv,
                'total_pv': self.total_pv,
                'daily': self.daily,
                'visitor_logs': saved_logs,
                'ad_clicks': {
                    'by_type_total': self.ad_clicks.get('by_type_total', {}),
                    'by_type_today': self.ad_clicks.get('by_type_today', {}),
                    'recent_logs': saved_ad_logs
                }
            }
            with open(VISITOR_STATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.last_saved = time.time()
        except Exception as e:
            print(f"[Stats] Save error: {e}")

    def _check_date_rollover(self):
        today = get_kst_today_str()
        if today != self.current_date:
            self.current_date = today
            self.today_vids.clear()
            for v in self.visitor_logs.values():
                v['visit_count'] = 0
            if today not in self.daily:
                self.daily[today] = {"uv": 0, "pv": 0}
            if 'by_type_today' in self.ad_clicks:
                self.ad_clicks['by_type_today'] = {k: 0 for k in self.ad_clicks['by_type_today']}
            self.save()

    def record_ad_click(self, ip, device, ad_type, page_name):
        now = time.time()
        now_str = datetime.now(KST).strftime('%H:%M:%S')
        label_map = {
            'left': '좌측 날개 배너',
            'right': '우측 날개 배너',
            'center': '정면 본문 배너',
            'popup': '중앙 팝업 배너',
            'link': '쿠팡 파트너스 링크',
            'auto_redirect': '자동 자리이동'
        }
        ad_label = label_map.get(ad_type, f'광고 배너 ({ad_type})')
        with self.lock:
            self._check_date_rollover()
            if 'by_type_total' not in self.ad_clicks:
                self.ad_clicks['by_type_total'] = {'left': 0, 'right': 0, 'center': 0, 'popup': 0, 'link': 0, 'auto_redirect': 0}
            if 'by_type_today' not in self.ad_clicks:
                self.ad_clicks['by_type_today'] = {'left': 0, 'right': 0, 'center': 0, 'popup': 0, 'link': 0, 'auto_redirect': 0}
            if 'recent_logs' not in self.ad_clicks:
                self.ad_clicks['recent_logs'] = []

            bt_tot = self.ad_clicks['by_type_total']
            bt_today = self.ad_clicks['by_type_today']

            bt_tot[ad_type] = bt_tot.get(ad_type, 0) + 1
            bt_today[ad_type] = bt_today.get(ad_type, 0) + 1

            self.ad_clicks['recent_logs'].append({
                'time': now_str,
                'ip': ip,
                'device': device,
                'ad_type': ad_type,
                'label': ad_label,
                'page': page_name or '메인 홈',
                'ts': now
            })
            if len(self.ad_clicks['recent_logs']) > 150:
                self.ad_clicks['recent_logs'] = self.ad_clicks['recent_logs'][-100:]
            self.save()

    def record_visit(self, ip, device, page_name, is_pageview=True):
        now = time.time()
        now_str = datetime.now(KST).strftime('%H:%M:%S')
        with self.lock:
            self._check_date_rollover()
            today = self.current_date
            
            # 실시간 활성 사용자 갱신
            self.active_users[ip] = now
            
            # 당일 고유 방문자(UV) 여부
            if ip not in self.today_vids:
                self.today_vids.add(ip)
                self.daily[today]['uv'] = self.daily[today].get('uv', 0) + 1
                self.total_uv += 1

            # 페이지뷰(PV)
            if is_pageview:
                self.daily[today]['pv'] = self.daily[today].get('pv', 0) + 1
                self.total_pv += 1

            # IP별 상세 접속 로그 갱신
            if ip not in self.visitor_logs:
                self.visitor_logs[ip] = {
                    'ip': ip,
                    'device': device,
                    'visit_count': 1 if is_pageview else 0,
                    'first_seen': now_str,
                    'last_seen': now_str,
                    'last_seen_ts': now,
                    'last_page': page_name
                }
            else:
                log = self.visitor_logs[ip]
                if is_pageview:
                    log['visit_count'] = log.get('visit_count', 0) + 1
                log['last_seen'] = now_str
                log['last_seen_ts'] = now
                log['device'] = device
                if page_name:
                    log['last_page'] = page_name

            # 15초마다 자동 파일 저장
            if now - self.last_saved > 15:
                self.save()

    def update_ping(self, ip, page_name=''):
        now = time.time()
        now_str = datetime.now(KST).strftime('%H:%M:%S')
        with self.lock:
            self.active_users[ip] = now
            if ip in self.visitor_logs:
                self.visitor_logs[ip]['last_seen_ts'] = now
                self.visitor_logs[ip]['last_seen'] = now_str
                if page_name:
                    self.visitor_logs[ip]['last_page'] = page_name

    def get_stats(self):
        now = time.time()
        with self.lock:
            self._check_date_rollover()
            today = self.current_date

            cutoff_5m = now - 300
            cutoff_10m = now - 600

            expired = [vid for vid, ts in self.active_users.items() if ts < cutoff_10m]
            for vid in expired:
                del self.active_users[vid]

            realtime_count = sum(1 for ts in self.active_users.values() if ts >= cutoff_5m)
            today_stat = self.daily.get(today, {"uv": 0, "pv": 0})
            
            sorted_dates = sorted(self.daily.keys(), reverse=True)[:7]
            recent_daily = [{"date": d, "uv": self.daily[d].get('uv', 0), "pv": self.daily[d].get('pv', 0)} for d in sorted_dates]

            # 최근 방문자 IP 리스트 생성 (실시간 라이브 우선, 그 다음 최신 접속시간 순)
            v_list = []
            for ip, info in self.visitor_logs.items():
                last_ts = info.get('last_seen_ts', 0)
                is_live = (now - last_ts < 300)
                v_list.append({
                    'ip': ip,
                    'device': info.get('device', '💻 PC'),
                    'visit_count': info.get('visit_count', 1),
                    'first_seen': info.get('first_seen', '-'),
                    'last_seen': info.get('last_seen', '-'),
                    'last_page': info.get('last_page', '메인 홈'),
                    'is_live': is_live,
                    'last_ts': last_ts
                })
            
            v_list.sort(key=lambda x: (1 if x['is_live'] else 0, x['last_ts']), reverse=True)

            # 쿠팡 광고 클릭 통계 (자리이동 auto_redirect 제외하여 순수 광고 배너 클릭만 집계!)
            PURE_AD_KEYS = ['center', 'left', 'right', 'popup', 'link']
            bt_tot = self.ad_clicks.get('by_type_total', {})
            bt_today = self.ad_clicks.get('by_type_today', {})

            # 1. 순수 쿠팡 광고 배너 클릭수 (정면, 좌측, 우측, 팝업, 직링크)
            pure_today = sum(bt_today.get(k, 0) for k in PURE_AD_KEYS)
            pure_total = sum(bt_tot.get(k, 0) for k in PURE_AD_KEYS)
            today_uv = today_stat.get('uv', 0)
            pure_ctr = round((pure_today / max(1, today_uv)) * 100, 1) if today_uv > 0 else 0.0

            # 2. 자리이동 (자동 리다이렉트 이동) 별도 분리 집계
            redirect_today = bt_today.get('auto_redirect', 0)
            redirect_total = bt_tot.get('auto_redirect', 0)

            recent_ad_logs = list(reversed(self.ad_clicks.get('recent_logs', [])))[:50]

            return {
                'realtime_now': realtime_count,
                'today_uv': today_stat.get('uv', 0),
                'today_pv': today_stat.get('pv', 0),
                'total_uv': self.total_uv,
                'total_pv': self.total_pv,
                'recent_daily': recent_daily,
                'visitor_list': v_list[:50],
                'ad_stats': {
                    'pure_today': pure_today,
                    'pure_total': pure_total,
                    'pure_ctr': pure_ctr,
                    'today': pure_today,       # 하위 호환
                    'total': pure_total,       # 하위 호환
                    'ctr': pure_ctr,           # 하위 호환
                    'by_type_total': bt_tot,   # 위치별 누적 클릭수
                    'by_type_today': bt_today, # 위치별 오늘 클릭수
                    'redirect': {              # 자리이동(자동 리다이렉트) 별도 통계
                        'today': redirect_today,
                        'total': redirect_total
                    },
                    'recent_logs': recent_ad_logs
                }
            }

visitor_tracker = VisitorTracker()

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
    },
    "auto_redirect": {
        "enabled": False,
        "target_url": "https://link.coupang.com/",
        "target_window": "_self",
        "apply_target": "article",
        "trigger_mode": "either",
        "time_seconds": 5,
        "scroll_percent": 50,
        "prevent_repeat": True
    },
    "share": {
        "title": "뉴스NOW - 오늘의 실시간 주요 속보 종합",
        "description": "국내 주요 언론사 실시간 속보 및 오늘의 주요 헤드라인을 신속하고 정확하게 전달합니다.",
        "image_url": "https://news-now-82jg.onrender.com/static/img/og_image.jpg",
        "site_name": "뉴스NOW"
    }
}

def load_site_config():
    if os.path.exists(SITE_CONFIG_FILE):
        try:
            with open(SITE_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'auto_redirect' not in data:
                    data['auto_redirect'] = DEFAULT_SITE_CONFIG['auto_redirect']
                if 'share' not in data:
                    data['share'] = DEFAULT_SITE_CONFIG['share']
                return data
        except:
            pass
    return DEFAULT_SITE_CONFIG

def save_site_config(config):
    with open(SITE_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def get_admin_password():
    try:
        cfg = load_site_config()
        return cfg.get('admin_password') or 'thfWlrgl12!@'
    except Exception:
        return 'thfWlrgl12!@'

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
# 인코딩 자동 보정 & 텍스트 정제 엔진 (한글 깨짐 완전 방지)
# ============================================================
def decode_html_bytes(content, headers=None):
    """HTML 바이너리 데이터를 안전하게 디코딩 (UTF-8, CP949/EUC-KR, BOM, 메타태그 자동 판별)"""
    if not content:
        return ''
        
    # 1. UTF-8 BOM 서명 확인
    if content.startswith(b'\xef\xbb\xbf'):
        try:
            return content.decode('utf-8-sig')
        except Exception:
            pass

    # 2. HTML 내부 메타태그 인코딩 선언 확인 (<meta charset="..."> 또는 <meta http-equiv="...">)
    meta_charset = None
    m = re.search(rb'<meta[^>]+charset=["\']?([a-zA-Z0-9_-]+)', content[:4096], re.I)
    if not m:
        m = re.search(rb'charset=["\']?([a-zA-Z0-9_-]+)', content[:4096], re.I)
    if m:
        c_cand = m.group(1).decode('ascii', 'ignore').lower().strip()
        if c_cand in ['utf-8', 'utf8']:
            meta_charset = 'utf-8'
        elif c_cand in ['euc-kr', 'euckr', 'cp949', 'ks_c_5601-1987', 'korean']:
            meta_charset = 'cp949'

    # 3. HTTP 응답 헤더 Content-Type 확인
    header_charset = None
    if headers and 'content-type' in headers:
        ct = headers['content-type'].lower()
        m = re.search(r'charset=["\']?([a-zA-Z0-9_-]+)', ct)
        if m:
            c_cand = m.group(1).strip()
            if c_cand in ['utf-8', 'utf8']:
                header_charset = 'utf-8'
            elif c_cand in ['euc-kr', 'euckr', 'cp949', 'ks_c_5601-1987', 'korean']:
                header_charset = 'cp949'

    # 메타태그 또는 헤더에 선언된 우선 인코딩 시도
    preferred = meta_charset or header_charset
    if preferred:
        try:
            text = content.decode(preferred)
            if re.search(r'[\uac00-\ud7a3]', text):
                return text
        except Exception:
            pass

    # 4. 국내 웹 99%인 UTF-8 우선 검증
    try:
        text = content.decode('utf-8')
        if re.search(r'[\uac00-\ud7a3]', text):
            return text
    except UnicodeDecodeError:
        pass

    # 5. 레거시 언론사 EUC-KR / CP949 검증
    try:
        text = content.decode('cp949')
        if re.search(r'[\uac00-\ud7a3]', text):
            return text
    except UnicodeDecodeError:
        pass

    # 6. BeautifulSoup UnicodeDammit 폴백
    try:
        from bs4 import UnicodeDammit
        dammit = UnicodeDammit(content, is_html=True)
        if dammit.unicode_markup:
            return dammit.unicode_markup
    except Exception:
        pass

    # 7. 최종 오류 대체 디코딩
    return content.decode('utf-8', errors='replace')

def repair_text(text):
    """모지바케(깨진 문자), 특수 공백, HTML 엔티티를 완벽하게 정상 한글 텍스트로 복원"""
    if not text or not isinstance(text, str):
        return ""
        
    # UTF-8 바이트가 Latin-1/CP1252로 잘못 디코딩된 모지바케 복원 (예: Ã«Â³Â´ -> 한글)
    if re.search(r'[ÃÂ][\x80-\xbf]', text):
        try:
            fixed = text.encode('latin1').decode('utf-8')
            if re.search(r'[\uac00-\ud7a3]', fixed):
                text = fixed
        except Exception:
            pass

    # 제로너비 공백 및 특수 공백 제거
    text = (text.replace('\xa0', ' ')
                .replace('\u200b', '')
                .replace('\ufeff', '')
                .replace('\u3000', ' ')
                .replace('\u200c', '')
                .replace('\u200d', ''))

    # HTML 엔티티(&quot;, &#39;, &amp;, &lt;, &gt; 등) 디코딩
    text = html.unescape(text)
    if '&' in text and re.search(r'&[a-zA-Z]+;|&#\d+;', text):
        text = html.unescape(text)

    return text.strip()

def clean_html(text):
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', str(text))
    clean = repair_text(clean)
    return clean.strip()

IMAGE_CACHE = {}

# 언론사 기본 로고 또는 플레이스홀더 이미지 블랙리스트
BAD_IMG_KEYWORDS = [
    'facebook_mknews', 'mai-property-main-img', 'l_mlogoky', 'ic_mai_w', 'trans_30x13',
    'logo.png', 'logo.jpg', 'default_thumb', 'blank.gif', 'spacer.gif', 'icon'
]

# 사진이 전혀 없는 단신 기사를 위한 고화질 테마 이미지 풀
REALESTATE_FALLBACK_IMAGES = [
    'https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?w=600&auto=format&fit=crop&q=80',
    'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=600&auto=format&fit=crop&q=80',
    'https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=600&auto=format&fit=crop&q=80',
    'https://images.unsplash.com/photo-1560518883-ce09059eeffa?w=600&auto=format&fit=crop&q=80',
    'https://images.unsplash.com/photo-1570129477492-45c003edd2be?w=600&auto=format&fit=crop&q=80',
]

NEWS_THEME_FALLBACKS = {
    '전체': [
        'https://images.unsplash.com/photo-1585829365295-ab7cd400c167?w=600&auto=format&fit=crop&q=80',
        'https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=600&auto=format&fit=crop&q=80',
        'https://images.unsplash.com/photo-1495020689067-958852a7765e?w=600&auto=format&fit=crop&q=80',
        'https://images.unsplash.com/photo-1526470608268-f674ce90ebd4?w=600&auto=format&fit=crop&q=80',
    ],
    '정치': [
        'https://images.unsplash.com/photo-1541872703-74c5e44368f9?w=600&auto=format&fit=crop&q=80',
        'https://images.unsplash.com/photo-1575320181282-9afab399332c?w=600&auto=format&fit=crop&q=80',
        'https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?w=600&auto=format&fit=crop&q=80',
    ],
    '경제': [
        'https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=600&auto=format&fit=crop&q=80',
        'https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?w=600&auto=format&fit=crop&q=80',
        'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=600&auto=format&fit=crop&q=80',
    ],
    '부동산': REALESTATE_FALLBACK_IMAGES,
    '증권': [
        'https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=600&auto=format&fit=crop&q=80',
        'https://images.unsplash.com/photo-1642543492481-44e81e3914a7?w=600&auto=format&fit=crop&q=80',
    ],
    '사회': [
        'https://images.unsplash.com/photo-1477959858617-67f30bc75b82?w=600&auto=format&fit=crop&q=80',
        'https://images.unsplash.com/photo-1517245386807-bb43f82c33c4?w=600&auto=format&fit=crop&q=80',
    ],
    'IT/과학': [
        'https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&auto=format&fit=crop&q=80',
        'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&auto=format&fit=crop&q=80',
    ],
    '스포츠': [
        'https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=600&auto=format&fit=crop&q=80',
        'https://images.unsplash.com/photo-1461896836934-ffe607ba8211?w=600&auto=format&fit=crop&q=80',
    ],
    '연예': [
        'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=600&auto=format&fit=crop&q=80',
        'https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=600&auto=format&fit=crop&q=80',
    ]
}

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
    if url in IMAGE_CACHE and IMAGE_CACHE[url]:
        return IMAGE_CACHE[url]
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=3.0)
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

        # 5) 사진이 전혀 없는 단신 기사를 위한 고화질 카테고리 테마 이미지 100% 매칭
        if not img_url:
            pool = NEWS_THEME_FALLBACKS.get(category, NEWS_THEME_FALLBACKS.get('전체', []))
            if pool:
                idx = abs(hash(url)) % len(pool)
                img_url = pool[idx]

        IMAGE_CACHE[url] = img_url
        return img_url
    except Exception:
        pool = NEWS_THEME_FALLBACKS.get(category, NEWS_THEME_FALLBACKS.get('전체', []))
        if pool:
            idx = abs(hash(url)) % len(pool)
            fallback = pool[idx]
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
        resp = requests.get(feed_url, headers=headers, timeout=5)
        feed = feedparser.parse(resp.content)
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
# 기사 본문 자체 파싱 & 뷰어 엔진
# ============================================================
ARTICLE_CACHE = {}

def get_publisher_info(url, soup=None):
    domain_map = {
        'yna.co.kr': ('연합뉴스', '🔴'),
        'ytn.co.kr': ('YTN', '🟠'),
        'imbc.com': ('MBC', '🔵'),
        'kbs.co.kr': ('KBS', '🟢'),
        'sbs.co.kr': ('SBS', '🟡'),
        'chosun.com': ('조선일보', '⚫'),
        'joins.com': ('중앙일보', '🟤'),
        'joongang.co.kr': ('중앙일보', '🟤'),
        'donga.com': ('동아일보', '⭕'),
        'hani.co.kr': ('한겨레', '🔷'),
        'khan.co.kr': ('경향신문', '🔶'),
        'mk.co.kr': ('매일경제', '💹'),
        'hankyung.com': ('한국경제', '📈'),
        'mt.co.kr': ('머니투데이', '💰'),
        'asiae.co.kr': ('아시아경제', '🌐'),
        'heraldcorp.com': ('헤럴드경제', '🗞️'),
        'etnews.com': ('전자신문', '💻')
    }
    for dom, (name, logo) in domain_map.items():
        if dom in url:
            return name, logo
    if soup:
        og_site = soup.find('meta', property='og:site_name')
        if og_site and og_site.get('content'):
            return og_site['content'].strip(), '📰'
    return '주요 언론사', '📰'

def fetch_article_detail(url):
    """기사 웹페이지를 분석하여 본문 문단, 메인 사진, 기자명, 발행시간 등을 추출 (한글 인코딩 깨짐 100% 방지)"""
    if not url or not url.startswith('http'):
        return None
        
    now_ts = time.time()
    if url in ARTICLE_CACHE:
        cached_time, cached_data = ARTICLE_CACHE[url]
        if now_ts - cached_time < 3600:
            return cached_data

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
    }

    try:
        resp = requests.get(url, headers=headers, timeout=5)
        html_text = decode_html_bytes(resp.content, resp.headers)
        soup = BeautifulSoup(html_text, 'html.parser')

        # 1. 언론사 정보
        publisher, pub_logo = get_publisher_info(url, soup)
        publisher = repair_text(publisher)

        # 2. 제목 추출
        og_title = soup.find('meta', attrs={'property': 'og:title'})
        title = og_title['content'].strip() if og_title and og_title.get('content') else ''
        if not title and soup.find('h1'):
            title = soup.find('h1').get_text(strip=True)
        title = re.sub(r'\s*[-|:]\s*(?:연합뉴스|매일경제|한국경제|경향신문|동아일보|조선일보|한겨레|SBS|MBC|KBS|YTN|머니투데이|아시아경제).*$', '', title).strip()
        title = repair_text(title)

        # 3. 작성일시 추출
        pub_date = ''
        og_date = soup.find('meta', attrs={'property': 'article:published_time'}) or soup.find('meta', attrs={'property': 'og:pubdate'})
        if og_date and og_date.get('content'):
            raw_d = og_date['content']
            m = re.search(r'(\d{4})[-/.](\d{2})[-/.](\d{2})[T\s](\d{2}:\d{2})', raw_d)
            if m:
                pub_date = f"{m.group(1)}.{m.group(2)}.{m.group(3)} {m.group(4)}"
        if not pub_date:
            date_candidates = soup.select('.update-time, .news-date, .date, .txt-date, .author-box span, .byline, .article_date, .input_date, .media_end_head_info_datestamp_time')
            for el in date_candidates:
                txt = el.get_text(strip=True)
                m = re.search(r'(\d{4})[.-](\d{2})[.-](\d{2})(?:\s+(\d{2}:\d{2}))?', txt)
                if m:
                    pub_date = txt
                    break
        if not pub_date:
            pub_date = datetime.now().strftime('%Y.%m.%d %H:%M')
        pub_date = repair_text(pub_date)

        # 4. 기자명 / 작성자
        author = ''
        og_author = soup.find('meta', attrs={'property': 'dable:author'}) or soup.find('meta', attrs={'name': 'author'}) or soup.find('meta', attrs={'property': 'article:author'})
        if og_author and og_author.get('content'):
            author = og_author['content'].strip()
        if not author:
            for selector in ['.byline', '.reporter', '.author', '.writer', '.news-reporter', '.reporter_name']:
                el = soup.select_one(selector)
                if el:
                    txt = el.get_text(strip=True)
                    m = re.search(r'([가-힣]{2,4}\s*기자)', txt)
                    if m:
                        author = m.group(1)
                        break
                    elif len(txt) <= 15:
                        author = txt
                        break
        author = repair_text(author)

        # 5. 메인 이미지 (이미 파싱된 soup에서 즉시 추출하여 중복 HTTP 요청 제거)
        main_img = ''
        og_img = soup.find('meta', attrs={'property': 'og:image'}) or soup.find('meta', attrs={'name': 'twitter:image'})
        if og_img and og_img.get('content'):
            main_img = og_img['content'].strip()
        if not main_img or is_invalid_image(main_img):
            first_img = soup.find('img')
            if first_img and first_img.get('src') and not is_invalid_image(first_img['src']):
                main_img = first_img['src']
            else:
                main_img = ''

        # 6. 본문 컨테이너 탐색 (국내 주요 언론사 전수 대응)
        candidates = [
            soup.find('article', class_='story-news'),
            soup.find('div', class_='story-news'),
            soup.find(class_='news_view'),
            soup.find('section', class_='news_view'),
            soup.find(id='news_view'),
            soup.find(id='article-view-content-div'),
            soup.find(id='articletxt'),
            soup.find(id='articleBody'),
            soup.find(class_='news_cnt_detail_wrap'),
            soup.find(class_='art_txt'),
            soup.find(class_='article-body'),
            soup.find('section', class_='article-body'),
            soup.find(class_='article_txt'),
            soup.find(id='article_body'),
            soup.find(class_='article_body'),
            soup.find(class_='article_text'),
            soup.find(class_='content_text'),
            soup.find(class_='art_body'),
            soup.find(class_='main_text'),
            soup.find(id='dic_area'),
            soup.find(id='textBody'),
            soup.find(id='txt_area'),
            soup.find(id='articleText'),
            soup.find('article'),
        ]
        body_elem = next((c for c in candidates if c), None)

        paragraphs = []
        lead_img_caption = ''

        if body_elem:
            # 이미지 캡션 탐색
            fig_cap = body_elem.find(['figcaption', '.caption', '.img-desc', '.desc-con'])
            if fig_cap:
                lead_img_caption = repair_text('\n'.join([line.strip() for line in fig_cap.get_text('\n').splitlines() if line.strip()]))
                fig_cap.decompose()

            # 불필요한 태그/광고/스크립트/버튼/댓글/송고 제거
            for tag in body_elem(['script', 'style', 'aside', 'button', 'iframe', 'form', 'noscript', 
                                  '.ad', '.ad-box', '.share-box', '.sns_area', '.reporter_area', 
                                  '.relation_news', '.article_sns', '.txt-copyright', '.adrs', 
                                  '.writer-zone01', '.image-zone01', '.comp-box', '.byline-zone', 
                                  '.article-copyright', '.btn_zoom', '.caption_area']):
                tag.decompose()

            # 테이블 표 및 구분 태그 간격/개행 처리 (프로야구 순위표, 경기전적 등 깨짐 방지)
            for td in body_elem.find_all(['td', 'th']):
                td.append(' ')
            for tr in body_elem.find_all('tr'):
                tr.append('\n')
            for div in body_elem.find_all(['div', 'p', 'li']):
                div.append('\n')
            for br in body_elem.find_all('br'):
                br.replace_with('\n')

            raw_lines = [repair_text(line) for line in body_elem.get_text().split('\n')]
            bad_keywords = ['저작권자', '무단전재', '무단 전재', '카카오톡', '제보하기', '구독신청', '기자의 다른 기사', 
                            'All rights reserved', 'DB 금지', '재판매 및 DB', '송고', 'okjebo', 'AI 학습 및 활용', 'AI 학습', '크게보기']

            for p in raw_lines:
                p = repair_text(p)
                if len(p) > 15 and not any(k in p for k in bad_keywords) and not re.search(r'\d{4}[/.-]\d{2}[/.-]\d{2}.*송고', p):
                    if not re.match(r'^\s*\[.*(?:제공|사진|출처|그래픽).*\]\s*$', p):
                        if p not in paragraphs:
                            paragraphs.append(p)

        # 단신/속보 사진 기사 등 본문이 없는 경우 캡션(사진 설명) 또는 og:description으로 보완
        if not paragraphs:
            if lead_img_caption:
                paragraphs.append(lead_img_caption)
            else:
                og_desc = soup.find('meta', attrs={'property': 'og:description'})
                if og_desc and og_desc.get('content') and not any(k in og_desc['content'] for k in ['송고', '저작권자']):
                    paragraphs.append(repair_text(og_desc['content'].strip()))
                else:
                    paragraphs.append("기사의 본문 내용을 불러오는 중입니다. 전문은 아래 언론사 원문 보기를 통해 확인하실 수 있습니다.")

        result = {
            'title': title or '최신 뉴스',
            'publisher': publisher,
            'pub_logo': pub_logo,
            'pub_date': pub_date,
            'author': author,
            'main_img': main_img,
            'caption': lead_img_caption,
            'paragraphs': paragraphs,
            'url': url
        }

        ARTICLE_CACHE[url] = (now_ts, result)
        return result

    except Exception as e:
        print(f"[Article Parse Error] {url}: {e}")
        return {
            'title': '뉴스 기사 안내',
            'publisher': '언론사 뉴스',
            'pub_logo': '📰',
            'pub_date': datetime.now().strftime('%Y.%m.%d %H:%M'),
            'author': '',
            'main_img': '',
            'caption': '',
            'paragraphs': ['기사 본문을 불러오는 과정에서 오류가 발생했습니다. 아래 공식 언론사 원문 기사 보기를 클릭하여 확인해주세요.'],
            'url': url
        }

# ============================================================
# 방문자 트래킹 미들웨어 & 실시간 핑
# ============================================================
BOT_USER_AGENTS = ['bot', 'spider', 'crawler', 'curl', 'wget', 'python', 'render', 'uptime', 'pingdom']

def is_bot_or_crawler():
    ua = request.headers.get('User-Agent', '').lower()
    return any(b in ua for b in BOT_USER_AGENTS)

def get_client_real_ip():
    """Cloudflare / Render 리버스 프록시 실제 클라이언트 IP 추출"""
    cf_ip = request.headers.get('CF-Connecting-IP')
    if cf_ip and cf_ip.strip():
        return cf_ip.strip()
    xff = request.headers.get('X-Forwarded-For')
    if xff and xff.strip():
        return xff.split(',')[0].strip()
    x_real = request.headers.get('X-Real-IP')
    if x_real and x_real.strip():
        return x_real.strip()
    return request.remote_addr or '127.0.0.1'

def detect_device(ua=None):
    if ua is None:
        ua = request.headers.get('User-Agent', '')
    ua = ua.lower()
    if any(k in ua for k in ['iphone', 'ipad', 'android', 'mobile', 'blackberry', 'webos']):
        return '📱 모바일'
    return '💻 PC'

@app.before_request
def track_visitor_middleware():
    path = request.path

    # 비밀 URL 파라미터 감지 (예: ?admin=1, ?admin=true, ?key=admin)
    if request.args.get('admin') in ['1', 'true', 'key', 'login', 'yes'] or request.args.get('key') in ['admin', 'secret', 'now']:
        return redirect(url_for('admin_login'))

    # 정적 리소스, 헬스체크, 관리자 페이지, API 등 제외
    if path.startswith('/static') or path.startswith('/admin') or path.startswith('/api') or path in ['/favicon.ico', '/robots.txt', '/health']:
        return

    # 봇/크롤러 제외
    if is_bot_or_crawler():
        return

    client_ip = get_client_real_ip()
    device = detect_device()

    if path == '/':
        page_name = '🌐 메인 뉴스 홈'
    elif path == '/article':
        page_name = '📰 기사 상세 읽는 중'
    else:
        page_name = path

    # 방문 기록 (IP별 방문 횟수, 실시간 활성, UV, PV)
    visitor_tracker.record_visit(client_ip, device, page_name, is_pageview=True)

@app.route('/api/ping', methods=['POST', 'GET'])
def api_ping():
    """체류 중 실시간 접속자 상태 유지용 가벼운 핑"""
    client_ip = get_client_real_ip()
    page = request.args.get('page', '')
    visitor_tracker.update_ping(client_ip, page_name=page)
    return jsonify({'ok': True})

@app.route('/api/track_ad_click', methods=['POST'])
def api_track_ad_click():
    """쿠팡 파트너스 광고 및 링크 클릭 실시간 추적 API"""
    try:
        data = request.get_json(silent=True) or {}
        ad_type = data.get('ad_type', 'unknown')
        page_name = data.get('page', '')
        client_ip = get_client_real_ip()
        device = detect_device()
        visitor_tracker.record_ad_click(client_ip, device, ad_type, page_name)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# ============================================================
# 라우트 - 일반 사용자
# ============================================================
@app.route('/')
def index():
    feeds = load_feeds_config()
    categories = list(feeds.keys())
    site_cfg = load_site_config()
    with RSS_CACHE_LOCK:
        cached = RSS_CACHE.get('전체')
        initial_news = cached.get('news', []) if cached else []
    is_mobile = detect_device() == '📱 모바일'
    return render_template('index.html', categories=categories, site_config=site_cfg, initial_news=initial_news, is_mobile=is_mobile)

@app.route('/health')
def health_check():
    return jsonify({'status': 'ok', 'service': 'news-now'}), 200

@app.route('/article')
def article_page():
    url = request.args.get('url', '').strip()
    if not url or not url.startswith('http'):
        return redirect('/')

    article_data = fetch_article_detail(url)
    site_cfg = load_site_config()
    feeds = load_feeds_config()
    categories = list(feeds.keys())

    # 하단 추천용 최신 뉴스 (캐시에서 0.0001초 만에 즉시 추출)
    related_news = []
    with RSS_CACHE_LOCK:
        cached_all = RSS_CACHE.get('전체', {}).get('news', [])
    if cached_all:
        related_news = [n for n in cached_all if n.get('link') != url][:8]

    is_mobile = detect_device() == '📱 모바일'
    return render_template('article.html',
                           article=article_data,
                           site_config=site_cfg,
                           categories=categories,
                           related_news=related_news,
                           is_mobile=is_mobile)

@app.route('/api/article')
def api_article():
    url = request.args.get('url', '').strip()
    if not url or not url.startswith('http'):
        return jsonify({'success': False, 'error': '유효한 URL이 필요합니다.'}), 400
    data = fetch_article_detail(url)
    return jsonify({'success': True, 'article': data})

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

# ============================================================
# 서버 측 RSS 스마트 캐시 & 비동기 갱신 엔진 (0초대 초고속화)
# ============================================================
NEWS_SNAPSHOT_FILE = os.path.join(os.path.dirname(__file__), 'news_snapshot.json')
RSS_CACHE = {}          # category -> {"timestamp": float, "news": list, "count": int, "is_refreshing": bool}
RSS_CACHE_LOCK = threading.Lock()
CACHE_TTL = 90          # 90초(1.5분) 동안은 캐시에서 0.001초 만에 즉시 반환

def save_snapshot():
    """최신 캐시 뉴스를 파일로 영구 보관하여 서버 재부팅 시에도 0.00초 즉시 제공"""
    try:
        with RSS_CACHE_LOCK:
            data = {cat: entry['news'] for cat, entry in RSS_CACHE.items() if entry.get('news')}
        if data:
            with open(NEWS_SNAPSHOT_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"[Snapshot save error]: {e}")

def load_snapshot():
    """서버 부팅 즉시 파일 스냅샷을 메모리 캐시로 로드 (0.001초 콜드 스타트 제거)"""
    if os.path.exists(NEWS_SNAPSHOT_FILE):
        try:
            with open(NEWS_SNAPSHOT_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                with RSS_CACHE_LOCK:
                    for cat, news_list in data.items():
                        RSS_CACHE[cat] = {
                            'timestamp': time.time() - 30,
                            'news': news_list,
                            'count': len(news_list),
                            'is_refreshing': False
                        }
            print(f"[Snapshot] Loaded news snapshot for categories: {list(data.keys())}")
        except Exception as e:
            print(f"[Snapshot load error]: {e}")

# 서버 시작 시 스냅샷 즉시 로드
load_snapshot()

def do_fetch_category_news(category, max_per_feed=15):
    """실제 언론사 RSS들을 병렬로 수집하고, 최상단 눈에 보이는 주요 기사 이미지만 신속 보완"""
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
        t.join(timeout=2.5)
    for i in range(len(feeds)):
        all_news.extend(results.get(i, []))

    # 1. 이미지가 누락된 기사 식별
    missing_items = [item for item in all_news if is_invalid_image(item.get('image')) and item.get('link')]

    # 2. 최상단 4개 항목(헤드라인 후보)만 동기식으로 초고속 보완 (0.1~0.2초 이내)
    top_missing = missing_items[:4]
    if top_missing:
        def fill_img(item):
            img = get_og_image(item['link'], category=category)
            if img:
                item['image'] = img

        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(fill_img, top_missing))

    # 3. 5번째 이후 누락 기사는 고화질 카테고리 테마 이미지로 즉시 세팅 (사용자 응답 0초 지연)
    rest_missing = missing_items[4:]
    pool = NEWS_THEME_FALLBACKS.get(category, NEWS_THEME_FALLBACKS.get('전체', []))
    for item in rest_missing:
        cached_img = IMAGE_CACHE.get(item['link'])
        if cached_img:
            item['image'] = cached_img
        elif pool:
            idx = abs(hash(item['link'])) % len(pool)
            item['image'] = pool[idx]

    # 4. 백그라운드 스레드에서 나머지 기사들의 실제 언론사 원문 og:image를 조용히 긁어 캐시 갱신
    if rest_missing:
        def bg_enrich():
            try:
                def enrich_worker(item):
                    real_img = fetch_og_image(item['link'])
                    if real_img and not is_invalid_image(real_img):
                        item['image'] = real_img
                        IMAGE_CACHE[item['link']] = real_img

                with ThreadPoolExecutor(max_workers=8) as ex:
                    list(ex.map(enrich_worker, rest_missing))
                save_snapshot()
            except Exception:
                pass
        threading.Thread(target=bg_enrich, daemon=True).start()

    return all_news

@app.route('/api/get_image')
def api_get_image():
    url = request.args.get('url', '').strip()
    category = request.args.get('category', '전체')
    if not url or not url.startswith('http'):
        return jsonify({'success': False, 'image': ''}), 400
    img = get_og_image(url, category=category)
    return jsonify({'success': True, 'image': img})

def background_refresh_category(category):
    """캐시 만료 시 백그라운드에서 최신 뉴스를 조용히 갱신 (Stale-While-Revalidate)"""
    with RSS_CACHE_LOCK:
        entry = RSS_CACHE.get(category)
        if entry and entry.get('is_refreshing'):
            return
        if entry:
            entry['is_refreshing'] = True

    def worker():
        try:
            news = do_fetch_category_news(category)
            if news:
                with RSS_CACHE_LOCK:
                    RSS_CACHE[category] = {
                        'timestamp': time.time(),
                        'news': news,
                        'count': len(news),
                        'is_refreshing': False
                    }
                save_snapshot()
        except Exception as e:
            print(f"[Background Cache Refresh Error] {category}: {e}")
            with RSS_CACHE_LOCK:
                if category in RSS_CACHE:
                    RSS_CACHE[category]['is_refreshing'] = False

    threading.Thread(target=worker, daemon=True).start()

def prewarm_rss_cache():
    """서버 실행 시 첫 방문자도 0초 로딩을 누릴 수 있도록 사전 캐시 빌드"""
    time.sleep(0.5)
    for cat in ['전체', '경제', '부동산', '정치']:
        try:
            news = do_fetch_category_news(cat)
            if news:
                with RSS_CACHE_LOCK:
                    RSS_CACHE[cat] = {
                        'timestamp': time.time(),
                        'news': news,
                        'count': len(news),
                        'is_refreshing': False
                    }
        except Exception:
            pass
    save_snapshot()

# 백그라운드 프리워밍 시작 (Gunicorn 및 로컬 공통)
threading.Thread(target=prewarm_rss_cache, daemon=True).start()

@app.route('/api/rss')
def api_rss():
    category = request.args.get('category', '전체')
    now = time.time()

    with RSS_CACHE_LOCK:
        cached = RSS_CACHE.get(category)

    # 1. 유효한 캐시가 있는 경우 -> 0.001초 즉시 반환
    if cached and (now - cached['timestamp'] < CACHE_TTL):
        resp = jsonify({'success': True, 'category': category, 'count': cached['count'], 'news': cached['news'], 'from_cache': True})
        resp.headers['Cache-Control'] = 'public, max-age=60, stale-while-revalidate=120'
        return resp

    # 2. 캐시가 있지만 90초가 지난 경우 -> 이전 데이터를 즉시 0.001초 반환하고, 백그라운드에서 조용히 갱신
    if cached and cached.get('news'):
        background_refresh_category(category)
        resp = jsonify({'success': True, 'category': category, 'count': cached['count'], 'news': cached['news'], 'from_cache': True, 'stale': True})
        resp.headers['Cache-Control'] = 'public, max-age=30, stale-while-revalidate=60'
        return resp

    # 3. 최초 호출인 경우 -> 동기 로드 후 캐시 보관
    news = do_fetch_category_news(category)
    with RSS_CACHE_LOCK:
        RSS_CACHE[category] = {
            'timestamp': now,
            'news': news,
            'count': len(news),
            'is_refreshing': False
        }
    save_snapshot()
    resp = jsonify({'success': True, 'category': category, 'count': len(news), 'news': news, 'from_cache': False})
    resp.headers['Cache-Control'] = 'public, max-age=60, stale-while-revalidate=120'
    return resp

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
        if pw == get_admin_password():
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

@app.route('/admin/api/visitor_stats', methods=['GET'])
def admin_visitor_stats():
    """오직 관리자만 조회 가능한 실시간/오늘/누적 방문자 통계 API (외부 열람 불가)"""
    if not is_admin():
        abort(403)
    return jsonify({'success': True, 'stats': visitor_tracker.get_stats()})

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
        feed = feedparser.parse(resp.content)
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

# ---- 네이버 우회 링크 및 카톡 전송 텍스트 변환 API ----
@app.route('/admin/api/convert_share_link', methods=['POST'])
def admin_convert_share_link():
    if not is_admin():
        abort(403)
    data = request.get_json() or {}
    raw_url = (data.get('url') or '').strip()
    if not raw_url:
        return jsonify({'success': False, 'message': '변환할 뉴스 기사 URL을 입력해주세요.'})

    try:
        # 1. naver.me 단축 링크인 경우 실제 목적지 추적
        if 'naver.me/' in raw_url:
            try:
                head_resp = requests.get(raw_url, allow_redirects=True, timeout=5, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                })
                raw_url = head_resp.url
            except Exception:
                pass

        # 2. 우리 사이트 기사 URL(/article?url=xxx)인지, 외부 원본 URL인지 판별
        target_news_url = raw_url
        if '/article?url=' in raw_url:
            parsed = urllib.parse.urlparse(raw_url)
            qs = urllib.parse.parse_qs(parsed.query)
            if 'url' in qs:
                target_news_url = qs['url'][0]
        elif 'link.naver.com/bridge?url=' in raw_url:
            parsed = urllib.parse.urlparse(raw_url)
            qs = urllib.parse.parse_qs(parsed.query)
            if 'url' in qs:
                inner_url = qs['url'][0]
                if '/article?url=' in inner_url:
                    inner_parsed = urllib.parse.urlparse(inner_url)
                    inner_qs = urllib.parse.parse_qs(inner_parsed.query)
                    if 'url' in inner_qs:
                        target_news_url = inner_qs['url'][0]
                else:
                    target_news_url = inner_url

        # 3. 기사 상세 정보 파싱 (제목, 언론사, 대표 이미지)
        article_data = fetch_article_detail(target_news_url)
        title = article_data.get('title') or '최신 주요 뉴스 속보'
        publisher = article_data.get('publisher') or '언론사'
        image = article_data.get('main_img') or ''

        # 4. 우리 사이트 배포 URL 기준 뷰어 링크 구성
        base_host = "https://news-now-82jg.onrender.com"
        our_article_url = f"{base_host}/article?url={urllib.parse.quote(target_news_url)}"

        # 5. 네이버 공식 우회 브릿지 링크 (link.naver.com)
        naver_bridge_url = f"https://link.naver.com/bridge?url={urllib.parse.quote(our_article_url)}"

        # 6. 초단축 URL (TinyURL) 옵션 생성
        short_url = ''
        try:
            t_resp = requests.get(f"https://tinyurl.com/api-create.php?url={urllib.parse.quote(naver_bridge_url)}", timeout=3)
            if t_resp.status_code == 200 and t_resp.text.startswith('http'):
                short_url = t_resp.text.strip()
        except Exception:
            pass

        # 7. 카카오톡 전송용 포맷 텍스트 완성
        kakao_text_bridge = f"{title}\n - {naver_bridge_url}"
        kakao_text_short = f"{title}\n - {short_url}" if short_url else kakao_text_bridge
        kakao_text_direct = f"{title}\n - {our_article_url}"

        return jsonify({
            'success': True,
            'title': title,
            'publisher': publisher,
            'image': image,
            'target_news_url': target_news_url,
            'our_article_url': our_article_url,
            'naver_bridge_url': naver_bridge_url,
            'short_url': short_url,
            'kakao_text_bridge': kakao_text_bridge,
            'kakao_text_short': kakao_text_short,
            'kakao_text_direct': kakao_text_direct
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'변환 실패: {str(e)}'})

# ---- 관리자 비밀번호 변경 API ----
@app.route('/admin/api/change_password', methods=['POST'])
def admin_change_password():
    if not is_admin():
        abort(403)
    data = request.get_json() or {}
    cur_pw = (data.get('current_password') or '').strip()
    new_pw = (data.get('new_password') or '').strip()

    if not cur_pw or not new_pw:
        return jsonify({'success': False, 'message': '현재 비밀번호와 새 비밀번호를 모두 입력해주세요.'})
    
    if cur_pw != get_admin_password():
        return jsonify({'success': False, 'message': '현재 비밀번호가 일치하지 않습니다.'})
    
    if len(new_pw) < 4:
        return jsonify({'success': False, 'message': '새 비밀번호는 최소 4자 이상이어야 합니다.'})
    
    cfg = load_site_config()
    cfg['admin_password'] = new_pw
    save_site_config(cfg)
    return jsonify({'success': True, 'message': '관리자 비밀번호가 성공적으로 변경되었습니다.'})

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
