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
            'daily': {},         # {date_str: {'pure_total': int, 'by_type': {...}}}
            'recent_logs': []
        }
        self.last_saved = time.time()
        self.dirty = False
        self.last_github_sync = time.time()
        self._sync_from_github()  # Render 재배포/재부팅 시 GitHub에서 최신 통계 자동 복원
        self.load()
        threading.Thread(target=self._auto_sync_loop, daemon=True).start()

    def _sync_from_github(self):
        """Render 재배포 후 시작될 때 GitHub에서 최신 visitor_stats.json을 다운로드하여 복원"""
        token = os.environ.get('GITHUB_TOKEN', '').strip()
        if not token:
            return
        try:
            import base64
            url = 'https://api.github.com/repos/dortm11-maker/dortm11-maker/contents/visitor_stats.json'
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json',
                'X-GitHub-Api-Version': '2022-11-28'
            }
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code == 200:
                content_b64 = resp.json().get('content', '')
                if content_b64:
                    raw = base64.b64decode(content_b64).decode('utf-8')
                    gh_data = json.loads(raw)
                    should_write = True
                    if os.path.exists(VISITOR_STATS_FILE):
                        try:
                            with open(VISITOR_STATS_FILE, 'r', encoding='utf-8') as f:
                                local_data = json.load(f)
                            if local_data.get('total_uv', 0) > gh_data.get('total_uv', 0):
                                should_write = False
                        except Exception:
                            pass
                    if should_write:
                        with open(VISITOR_STATS_FILE, 'w', encoding='utf-8') as f:
                            f.write(raw)
                        print(f"[VisitorStats] GitHub에서 최신 통계 복원 완료 (UV: {gh_data.get('total_uv')}, PV: {gh_data.get('total_pv')})")
        except Exception as e:
            print(f"[VisitorStats] GitHub 복원 예외: {e}")

    def _sync_to_github(self):
        """visitor_stats.json을 GitHub에 커밋/푸시하여 영구 보존"""
        token = os.environ.get('GITHUB_TOKEN', '').strip()
        if not token:
            return
        try:
            import base64
            url = 'https://api.github.com/repos/dortm11-maker/dortm11-maker/contents/visitor_stats.json'
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json',
                'Content-Type': 'application/json',
                'X-GitHub-Api-Version': '2022-11-28'
            }
            sha = None
            get_resp = requests.get(url, headers=headers, timeout=8)
            if get_resp.status_code == 200:
                sha = get_resp.json().get('sha', '')

            if not os.path.exists(VISITOR_STATS_FILE):
                return
            with open(VISITOR_STATS_FILE, 'r', encoding='utf-8') as f:
                content_str = f.read()
            content_b64 = base64.b64encode(content_str.encode('utf-8')).decode('ascii')

            put_body = {
                'message': f'[auto] sync visitor stats (UV: {self.total_uv}, PV: {self.total_pv})',
                'content': content_b64,
                'branch': 'main'
            }
            if sha:
                put_body['sha'] = sha

            put_resp = requests.put(url, headers=headers, json=put_body, timeout=10)
            if put_resp.status_code in (200, 201):
                self.dirty = False
                self.last_github_sync = time.time()
                print(f"[VisitorStats] GitHub 영구 보존 동기화 성공 ✅ (UV: {self.total_uv}, PV: {self.total_pv})")
            else:
                print(f"[VisitorStats] GitHub 동기화 응답: {put_resp.status_code}")
        except Exception as e:
            print(f"[VisitorStats] GitHub 동기화 예외: {e}")

    def _auto_sync_loop(self):
        """백그라운드에서 3분마다 변동사항이 있을 때 GitHub에 자동 동기화"""
        while True:
            time.sleep(30)
            try:
                should_sync = False
                with self.lock:
                    if self.dirty and (time.time() - self.last_github_sync >= 180):
                        should_sync = True
                if should_sync:
                    self._sync_to_github()
            except Exception:
                pass

    def load(self):
        today = get_kst_today_str()
        self.current_date = today
        if os.path.exists(VISITOR_STATS_FILE):
            try:
                with open(VISITOR_STATS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.total_uv = data.get('total_uv', 0)
                    self.total_pv = data.get('total_pv', 0)
                    self.daily = data.get('daily', {})
                    self.visitor_logs = data.get('visitor_logs', {})
                    if data.get('current_date') == today:
                        self.today_vids = set(data.get('today_vids', []))
                    if 'ad_clicks' in data:
                        ac = data['ad_clicks']
                        self.ad_clicks = {
                            'by_type_total': ac.get('by_type_total', {'left': 0, 'right': 0, 'center': 0, 'popup': 0, 'link': 0, 'auto_redirect': 0}),
                            'by_type_today': ac.get('by_type_today', {'left': 0, 'right': 0, 'center': 0, 'popup': 0, 'link': 0, 'auto_redirect': 0}),
                            'daily': ac.get('daily', {}),
                            'recent_logs': ac.get('recent_logs', [])
                        }
            except Exception as e:
                print(f"[Stats] Load error: {e}")
        
        if today not in self.daily:
            self.daily[today] = {"uv": 0, "pv": 0}
        if 'daily' not in self.ad_clicks:
            self.ad_clicks['daily'] = {}
        if today not in self.ad_clicks['daily']:
            self.ad_clicks['daily'][today] = {
                'pure_total': 0,
                'by_type': {'left': 0, 'right': 0, 'center': 0, 'popup': 0, 'link': 0, 'auto_redirect': 0}
            }

    def save(self):
        try:
            saved_logs = dict(list(self.visitor_logs.items())[-100:])
            saved_ad_logs = self.ad_clicks.get('recent_logs', [])[-100:]
            data = {
                'total_uv': self.total_uv,
                'total_pv': self.total_pv,
                'current_date': self.current_date,
                'today_vids': list(self.today_vids),
                'daily': self.daily,
                'visitor_logs': saved_logs,
                'ad_clicks': {
                    'by_type_total': self.ad_clicks.get('by_type_total', {}),
                    'by_type_today': self.ad_clicks.get('by_type_today', {}),
                    'daily': self.ad_clicks.get('daily', {}),
                    'recent_logs': saved_ad_logs
                }
            }
            with open(VISITOR_STATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.last_saved = time.time()
            self.dirty = True
        except Exception as e:
            print(f"[Stats] Save error: {e}")

    def _check_date_rollover(self):
        today = get_kst_today_str()
        if today != self.current_date:
            yesterday = self.current_date
            PURE_AD_KEYS = ['center', 'left', 'right', 'popup', 'link', 'sticky', 'mobile']
            
            # 어제(전날) 클릭수 확실히 daily에 영구 보존 기록
            if 'daily' not in self.ad_clicks:
                self.ad_clicks['daily'] = {}
            if yesterday and yesterday not in self.ad_clicks['daily']:
                bt_y = dict(self.ad_clicks.get('by_type_today', {}))
                self.ad_clicks['daily'][yesterday] = {
                    'pure_total': sum(bt_y.get(k, 0) for k in PURE_AD_KEYS),
                    'by_type': bt_y
                }

            self.current_date = today
            self.today_vids.clear()
            for v in self.visitor_logs.values():
                v['visit_count'] = 0
            if today not in self.daily:
                self.daily[today] = {"uv": 0, "pv": 0}
            if 'by_type_today' in self.ad_clicks:
                self.ad_clicks['by_type_today'] = {k: 0 for k in self.ad_clicks['by_type_today']}
            if today not in self.ad_clicks['daily']:
                self.ad_clicks['daily'][today] = {
                    'pure_total': 0,
                    'by_type': {'left': 0, 'right': 0, 'center': 0, 'popup': 0, 'link': 0, 'auto_redirect': 0}
                }
            self.save()
            threading.Thread(target=self._sync_to_github, daemon=True).start()

    def record_ad_click(self, ip, device, ad_type, page_name):
        now = time.time()
        now_str = datetime.now(KST).strftime('%H:%M:%S')
        label_map = {
            'left': '좌측 날개 배너',
            'right': '우측 날개 배너',
            'center': '정면 본문 배너',
            'sticky': '모바일 하단 고정 배너',
            'mobile': '모바일 하단 고정 배너',
            'popup': '중앙 팝업 배너',
            'link': '쿠팡 파트너스 링크',
            'auto_redirect': '자동 자리이동'
        }
        ad_label = label_map.get(ad_type, f'광고 배너 ({ad_type})')
        PURE_AD_KEYS = ['center', 'left', 'right', 'popup', 'link', 'sticky', 'mobile']

        with self.lock:
            self._check_date_rollover()
            today = self.current_date

            if 'by_type_total' not in self.ad_clicks:
                self.ad_clicks['by_type_total'] = {'left': 0, 'right': 0, 'center': 0, 'popup': 0, 'link': 0, 'auto_redirect': 0}
            if 'by_type_today' not in self.ad_clicks:
                self.ad_clicks['by_type_today'] = {'left': 0, 'right': 0, 'center': 0, 'popup': 0, 'link': 0, 'auto_redirect': 0}
            if 'daily' not in self.ad_clicks:
                self.ad_clicks['daily'] = {}
            if today not in self.ad_clicks['daily']:
                self.ad_clicks['daily'][today] = {
                    'pure_total': 0,
                    'by_type': {'left': 0, 'right': 0, 'center': 0, 'popup': 0, 'link': 0, 'auto_redirect': 0}
                }
            if 'recent_logs' not in self.ad_clicks:
                self.ad_clicks['recent_logs'] = []

            bt_tot = self.ad_clicks['by_type_total']
            bt_today = self.ad_clicks['by_type_today']
            day_entry = self.ad_clicks['daily'][today]
            day_bt = day_entry.setdefault('by_type', {})

            bt_tot[ad_type] = bt_tot.get(ad_type, 0) + 1
            bt_today[ad_type] = bt_today.get(ad_type, 0) + 1
            day_bt[ad_type] = day_bt.get(ad_type, 0) + 1

            day_entry['pure_total'] = sum(day_bt.get(k, 0) for k in PURE_AD_KEYS)

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
            
            # 쿠팡 광고 클릭 통계 (순수 광고 배너 클릭 집계)
            PURE_AD_KEYS = ['center', 'left', 'right', 'popup', 'link', 'sticky', 'mobile']
            bt_tot = self.ad_clicks.get('by_type_total', {})
            bt_today = self.ad_clicks.get('by_type_today', {})

            # 1. 오늘 순수 클릭수 & 누적 총 클릭수
            pure_today = sum(bt_today.get(k, 0) for k in PURE_AD_KEYS)
            pure_total = sum(bt_tot.get(k, 0) for k in PURE_AD_KEYS)
            today_uv = today_stat.get('uv', 0)
            pure_ctr = round((pure_today / max(1, today_uv)) * 100, 1) if today_uv > 0 else 0.0

            # 2. 어제(전날) 클릭수 산출
            yesterday_date = (datetime.now(KST) - timedelta(days=1)).strftime('%Y-%m-%d')
            yesterday_ad = self.ad_clicks.get('daily', {}).get(yesterday_date, {})
            by_type_yesterday = yesterday_ad.get('by_type', {})
            pure_yesterday = yesterday_ad.get('pure_total', sum(by_type_yesterday.get(k, 0) for k in PURE_AD_KEYS))

            # 3. 최근 7일간 일별 방문자 및 일별 쿠팡 배너 클릭수 내역
            sorted_dates = sorted(self.daily.keys(), reverse=True)[:7]
            recent_daily = []
            for d in sorted_dates:
                d_ad = self.ad_clicks.get('daily', {}).get(d, {})
                d_pure_ad = d_ad.get('pure_total', sum(d_ad.get('by_type', {}).get(k, 0) for k in PURE_AD_KEYS))
                recent_daily.append({
                    "date": d,
                    "uv": self.daily[d].get('uv', 0),
                    "pv": self.daily[d].get('pv', 0),
                    "ad_clicks": d_pure_ad
                })

            # 최근 방문자 IP 리스트 생성
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

            # 자리이동(자동 리다이렉트) 분리 집계
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
                    'pure_yesterday': pure_yesterday,
                    'pure_total': pure_total,
                    'pure_ctr': pure_ctr,
                    'today': pure_today,           # 하위 호환
                    'yesterday': pure_yesterday,   # 어제(전날) 클릭수
                    'total': pure_total,           # 하위 호환
                    'ctr': pure_ctr,               # 하위 호환
                    'by_type_total': bt_tot,       # 위치별 누적 클릭수
                    'by_type_today': bt_today,     # 위치별 오늘 클릭수
                    'by_type_yesterday': by_type_yesterday, # 위치별 어제 클릭수
                    'redirect': {                  # 자리이동 통계
                        'today': redirect_today,
                        'yesterday': by_type_yesterday.get('auto_redirect', 0),
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
            "enabled": True,
            "mode": "coupang",
            "coupang_id": 1026359,
            "tracking_code": "AF3197388",
            "sub_id": "dortm111",
            "delay": 30,
            "interval_minutes": 5,
            "close_delay": 3,
            "width": 300,
            "height": 300,
            "custom_html": ""
        },
        "mobile": {
            "enabled": True,
            "mode": "coupang",
            "coupang_id": 1026359,
            "tracking_code": "AF3197388",
            "sub_id": "dortm111",
            "width": 360,
            "height": 100,
            "custom_html": ""
        }
    },
    "ai_rewrite": {
        "enabled": True,
        "api_provider": "gemini",
        "api_key": "",
        "use_premium_images": True,
        "image_safeguard": True,
        "rewrite_title": True,
        "rewrite_body": True
    },
    "auto_redirect": {
        "enabled": True,
        "target_url": "https://open.kakao.com/o/gTLTzqqd",
        "target_window": "_self",
        "apply_target": "article",
        "trigger_mode": "either",
        "time_seconds": 60,
        "scroll_percent": 95,
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
    cfg = DEFAULT_SITE_CONFIG.copy()
    if os.path.exists(SITE_CONFIG_FILE):
        try:
            with open(SITE_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # 혹시 'config' 키로 감싸져 들어온 경우 내부 키를 풀어서 병합
                    if 'config' in data and isinstance(data['config'], dict):
                        inner = data.pop('config')
                        for k, v in inner.items():
                            if k not in data:
                                data[k] = v
                    for k, v in DEFAULT_SITE_CONFIG.items():
                        if k not in data or data[k] is None:
                            data[k] = v.copy() if hasattr(v, 'copy') else v
                    if 'ads' in data and isinstance(data['ads'], dict) and 'mobile' not in data['ads']:
                        data['ads']['mobile'] = DEFAULT_SITE_CONFIG['ads']['mobile']
                    return data
        except Exception as e:
            print(f"[load_site_config] Error: {e}")
    return cfg

def save_site_config(config):
    # 중첩된 'config' 래핑 자동 제거 및 필수 키 보장
    if isinstance(config, dict) and 'config' in config and isinstance(config['config'], dict):
        inner = config.pop('config')
        for k, v in inner.items():
            if k not in config:
                config[k] = v
    for k, v in DEFAULT_SITE_CONFIG.items():
        if k not in config or config[k] is None:
            config[k] = v.copy() if hasattr(v, 'copy') else v

    with open(SITE_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    # 관리자가 저장할 때마다 GitHub에 자동 push (Render 재배포 시에도 설정 영구 유지)
    _auto_push_site_config_to_github(config)

def _auto_push_site_config_to_github(config):
    """
    GitHub REST API를 통해 site_config.json을 자동으로 레포에 커밋/push.
    환경변수 GITHUB_TOKEN이 설정된 경우에만 동작.
    """
    token = os.environ.get('GITHUB_TOKEN', '').strip()
    if not token:
        return  # 토큰 없으면 조용히 건너뜀

    try:
        import base64
        GITHUB_OWNER = 'dortm11-maker'
        GITHUB_REPO  = 'dortm11-maker'
        GITHUB_PATH  = 'site_config.json'
        API_BASE     = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_PATH}'

        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'Content-Type': 'application/json',
            'X-GitHub-Api-Version': '2022-11-28'
        }

        # 1. 현재 파일의 SHA 가져오기 (업데이트에 필요)
        get_resp = requests.get(API_BASE, headers=headers, timeout=8)
        sha = None
        if get_resp.status_code == 200:
            sha = get_resp.json().get('sha', '')

        # 2. 파일 내용 base64 인코딩
        content_str = json.dumps(config, ensure_ascii=False, indent=2)
        content_b64 = base64.b64encode(content_str.encode('utf-8')).decode('ascii')

        # 3. PUT 요청으로 파일 업데이트
        put_body = {
            'message': '[auto] admin: save site_config.json',
            'content': content_b64,
            'branch': 'main'
        }
        if sha:
            put_body['sha'] = sha

        put_resp = requests.put(API_BASE, headers=headers, json=put_body, timeout=10)
        if put_resp.status_code in (200, 201):
            print(f"[GitHub Auto-Push] site_config.json 업데이트 성공 ✅")
        else:
            print(f"[GitHub Auto-Push] 실패: {put_resp.status_code} {put_resp.text[:200]}")
    except Exception as e:
        print(f"[GitHub Auto-Push] 예외: {e}")

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

# 언론사 기본 로고 또는 플레이스홀더, 배너 광고, 기자 프로필 이미지 블랙리스트
BAD_IMG_KEYWORDS = [
    'yonhapnews_logo', 'yna_logo', 'r.yna.co.kr', 'logo_1200x800',
    'facebook_mknews', 'mk_logo', 'mk_sns', 'mai-property-main-img', 'l_mlogoky', 'ic_mai_w', 'trans_30x13',
    'hankyung_logo', 'hk_logo', 'chosun_logo', 'donga_logo', 'ytn_logo', 'sbs_logo', 'kbs_logo', 'mbc_logo',
    'default_thumb', 'default_img', 'no_image', 'noimage', 'blank.gif', 'spacer.gif', 'share_default',
    'reporter', 'journalist', 'profile', 'author', 'reporter_img', 'byline',
    'gsshop', 'criteo', 'google_ad', 'advert', 'banner', 'ad_banner', 'ad-banner',
    'logo.png', 'logo.jpg', 'logo.svg', 'logo.webp', 'icon', 'btn_', 'button'
]

def normalize_img_url(img_url):
    """상대경로 및 // 프로토콜 생략 URL을 완전한 절대 URL로 정규화"""
    if not img_url or not isinstance(img_url, str):
        return ''
    img_url = img_url.strip()
    if img_url.startswith('//'):
        return 'https:' + img_url
    return img_url

# 고화질 테마 이미지 풀 (services.image_enhancer 연동)
try:
    from services.image_enhancer import PREMIUM_STOCK_IMAGES
    NEWS_THEME_FALLBACKS = {
        '전체': PREMIUM_STOCK_IMAGES.get('economy', []) + PREMIUM_STOCK_IMAGES.get('society', []),
        '정치': PREMIUM_STOCK_IMAGES.get('law_policy', []),
        '경제': PREMIUM_STOCK_IMAGES.get('economy', []),
        '부동산': PREMIUM_STOCK_IMAGES.get('realestate', []),
        '증권': PREMIUM_STOCK_IMAGES.get('stock', []),
        '사회': PREMIUM_STOCK_IMAGES.get('society', []),
        'IT/과학': PREMIUM_STOCK_IMAGES.get('tech', []),
        '스포츠': PREMIUM_STOCK_IMAGES.get('sports', []),
        '연예': PREMIUM_STOCK_IMAGES.get('entertainment', []),
    }
except Exception:
    NEWS_THEME_FALLBACKS = {
        '전체': ['https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=85'],
        '경제': ['https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?auto=format&fit=crop&w=1200&q=85']
    }

def is_invalid_image(img_url):
    """유효하지 않은 이미지(비어있거나 언론사 로고 플레이트, 배너 광고, 기자 사진)인지 검사"""
    if not img_url:
        return True
    img_url = normalize_img_url(img_url)
    if not img_url.startswith('http'):
        return True
    low = img_url.lower()
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

RAW_ORIGIN_IMAGE_CACHE = {}

def get_raw_origin_image(url):
    """
    카카오톡 / 네이버 / SNS 링크 공유 시 매력적이고 관련도 높은 미리보기를 위해
    언론사 원본 기사 사진(RSS 대표 이미지 또는 메타태그 og:image)을 정밀 추출.
    (Unsplash AI 대체 이미지는 일절 배제하고 순수 원문 사진만 반환)
    """
    if not url or not str(url).startswith('http'):
        return ''
    if url in RAW_ORIGIN_IMAGE_CACHE and RAW_ORIGIN_IMAGE_CACHE[url]:
        return RAW_ORIGIN_IMAGE_CACHE[url]

    # 1. 메모리 RSS 캐시에서 원본 이미지 우선 탐색
    with RSS_CACHE_LOCK:
        for cat, entry in RSS_CACHE.items():
            for item in entry.get('news', []):
                if item.get('link') == url:
                    img = item.get('image', '')
                    if img and 'unsplash.com' not in img and not is_invalid_image(img):
                        RAW_ORIGIN_IMAGE_CACHE[url] = img
                        return img
                    break

    # 2. 원본 기사 웹페이지의 og:image 태그 정밀 추출
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=3.5)
        if resp.status_code == 200 and len(resp.text) > 150:
            resp_text = resp.text

            # 매일경제 특화 패턴
            if 'mk.co.kr' in url:
                mk_matches = re.findall(r'https?://(?:pimg|wimg)\.mk\.co\.kr/news/cms/[0-9a-zA-Z_/.]+\.(?:jpg|png|jpeg|webp)', resp_text)
                if mk_matches:
                    RAW_ORIGIN_IMAGE_CACHE[url] = mk_matches[0]
                    return mk_matches[0]

            # 한국경제 특화 패턴
            if 'hankyung.com' in url:
                hk_matches = re.findall(r'https?://img\.hankyung\.com/photo/[0-9a-zA-Z_/.]+\.(?:jpg|png|jpeg|webp)', resp_text)
                if hk_matches:
                    RAW_ORIGIN_IMAGE_CACHE[url] = hk_matches[0]
                    return hk_matches[0]

            # 표준 og:image 추출
            m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', resp_text, re.I)
            if not m:
                m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', resp_text, re.I)
            if m:
                cand = html.unescape(m.group(1).strip())
                if cand and 'unsplash.com' not in cand and not is_invalid_image(cand):
                    RAW_ORIGIN_IMAGE_CACHE[url] = cand
                    return cand

            # 본문 내 첫 번째 유효 이미지 추출
            soup = BeautifulSoup(resp_text, 'html.parser')
            body = (
                soup.find('div', id='articletxt') or 
                soup.find('div', class_='article-body') or
                soup.find('div', id='article_body') or
                soup.find('div', class_='news_cnt_detail_wrap') or
                soup.find('div', class_='art_txt') or
                soup.find('div', id='articleBody') or
                soup.find('div', class_='article_view') or
                soup.find('article')
            )
            if body:
                for im in body.find_all('img'):
                    src = im.get('src') or im.get('data-src') or ''
                    if src.startswith('//'):
                        src = 'https:' + src
                    if src and src.startswith('http') and 'unsplash.com' not in src and not is_invalid_image(src):
                        RAW_ORIGIN_IMAGE_CACHE[url] = src
                        return src
    except Exception as e:
        print(f"[get_raw_origin_image warning]: {e}")

    RAW_ORIGIN_IMAGE_CACHE[url] = ''
    return ''


RAW_ORIGIN_TITLE_CACHE = {}

def get_raw_origin_title(url):
    """
    원본 기사 URL에서 og:title 혹은 <title> 태그를 추출해 실제 기사 제목을 반환.
    RSS 캐시에서 찾지 못한 경우의 fallback으로 사용.
    """
    if not url or not str(url).startswith('http'):
        return ''
    if url in RAW_ORIGIN_TITLE_CACHE and RAW_ORIGIN_TITLE_CACHE[url]:
        return RAW_ORIGIN_TITLE_CACHE[url]

    # 먼저 RSS 캐시에서 탐색
    with RSS_CACHE_LOCK:
        for cat, entry in RSS_CACHE.items():
            for item in entry.get('news', []):
                if item.get('link') == url:
                    t = item.get('title', '').strip()
                    if t:
                        RAW_ORIGIN_TITLE_CACHE[url] = t
                        return t

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=4)
        if resp.status_code == 200 and len(resp.text) > 100:
            # og:title 우선
            m = re.search(r'<meta[^>]+property=["\']og:title["\']\s[^>]+content=["\']([^"\']{5,})["\']', resp.text, re.I)
            if not m:
                m = re.search(r'<meta[^>]+content=["\']([^"\']{5,})["\']\s[^>]+property=["\']og:title["\']', resp.text, re.I)
            if m:
                t = html.unescape(m.group(1).strip())
                if t:
                    RAW_ORIGIN_TITLE_CACHE[url] = t
                    return t
            # <title> 태그 fallback
            m2 = re.search(r'<title[^>]*>([^<]{5,})</title>', resp.text, re.I)
            if m2:
                t = html.unescape(m2.group(1).strip())
                # 사이트명 제거 (| / :: - 뒤 부분이 사이트명인 경우)
                for sep in [' | ', ' :: ', ' - ', ' – ']:
                    if sep in t:
                        t = t.split(sep)[0].strip()
                        break
                if t:
                    RAW_ORIGIN_TITLE_CACHE[url] = t
                    return t
    except Exception as e:
        print(f"[get_raw_origin_title warning]: {e}")

    RAW_ORIGIN_TITLE_CACHE[url] = ''
    return ''

def parse_date(entry):
    try:
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            utc_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            kst_dt = utc_dt.astimezone(KST)
            return kst_dt.strftime('%m.%d %H:%M')
    except:
        pass
    try:
        if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            utc_dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
            kst_dt = utc_dt.astimezone(KST)
            return kst_dt.strftime('%m.%d %H:%M')
    except:
        pass
    return datetime.now(KST).strftime('%m.%d %H:%M')

def fetch_rss(feed_url, source_name, logo, max_items=15):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(feed_url, headers=headers, timeout=5)
        feed = feedparser.parse(resp.content)
        items = []
        from services.ai_rewriter import is_meaningless_news, clean_news_title, rewrite_news_title, clean_news_summary

        for entry in feed.entries[:max_items]:
            raw_title = clean_html(getattr(entry, 'title', ''))
            raw_summary = clean_html(getattr(entry, 'summary', '') or getattr(entry, 'description', ''))

            # 실질적 의미 없는 뉴스(유튜브/방송 예고, 운세, 인사, 부고 등) 배제
            if is_meaningless_news(raw_title, raw_summary):
                continue

            cleaned_title = clean_news_title(raw_title)
            if not cleaned_title or len(cleaned_title) < 6:
                continue

            # 원문 제목과 100% 동일하지 않게 재구성된 독창적 헤드라인 생성
            distinct_title = rewrite_news_title(cleaned_title)

            # 저작권 안전을 위해 (서울=연합뉴스) 김예나 기자 = 등 모든 바이라인/언론사/기자명 100% 제거
            summary = clean_news_summary(raw_summary)

            link = getattr(entry, 'link', '#')
            if len(summary) > 150:
                summary = summary[:150] + '...'
            image = get_image_from_entry(entry)
            pub_date = parse_date(entry)

            items.append({
                'title': distinct_title,
                'original_title': raw_title,
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
    """
    저작권 안심 독자적 뉴스 큐레이션 & 브리핑 리포트 엔진:
    - 언론사 원문 기사 본문 스크래핑/인용/DB저장 ❌ (연합뉴스 등 저작권 완전 보호)
    - 언론사 원본 이미지 수집/저장 ❌
    - 오직 RSS 메타데이터(제목, 링크, 출처, 날짜, 카테고리)만 저장 및 참조
    - 공개된 이슈 헤드라인을 바탕으로 사건 배경, 시장 영향, 시사점, 전망을 분석한 독자적 뉴스 브리핑 리포트 제공
    - 모든 게시물 하단에 원본 언론사명과 원문 URL 공식 아웃링크 제공
    """
    if not url or not url.startswith('http'):
        return None

    now_ts = time.time()
    if url in ARTICLE_CACHE:
        cached_time, cached_data = ARTICLE_CACHE[url]
        if now_ts - cached_time < 3600:
            if cached_data.get('paragraphs') and len(cached_data['paragraphs']) >= 2:
                if not cached_data.get('og_img') or 'unsplash.com' in cached_data.get('og_img', ''):
                    raw_origin_img = get_raw_origin_image(url)
                    if raw_origin_img:
                        cached_data['og_img'] = raw_origin_img
                return cached_data

    from services.curation_db import get_curated_article_by_url
    from services.ai_rewriter import build_full_news_article, clean_news_title, rewrite_news_title

    # 1. Curation DB에 유효한 브리핑이 저장되어 있는 경우 즉시 반환
    existing = get_curated_article_by_url(url)
    if existing and existing.get('ai_content') and isinstance(existing.get('ai_content'), dict):
        ai_cnt = existing['ai_content']
        paras = ai_cnt.get('paragraphs', [])
        summary_pts = ai_cnt.get('summary_points', [])
        # 기존 글이 추상적 템플릿이거나 찌꺼기 캡션, 엉뚱한 제목, 중복 요약이 있는 경우 최신 엔진으로 업그레이드
        from services.image_enhancer import get_premium_stock_image
        orig_t = clean_news_title(existing.get('original_title', ''))
        current_ai_t = existing.get('ai_title', '')
        
        from services.ai_rewriter import is_meaningless_news
        has_caption_junk = any(re.search(r'촬영|제공|재판매|DB\s*금지|송고시간|송고|\d{4}년\s*\d{1,2}월\s*\d{1,2}일\s*\d{1,2}시', p) for p in paras)
        has_host_junk = any(re.search(r'진행\s*[:：]|출연\s*[:：]|한겨레\s*정치팀|시청\s*바랍니다|시청바랍니다', p) for p in paras)
        has_web_junk = any(re.search(r'폰트\s*\d단계|\d+px|글자크기|본문\s*글자\s*크기|구독\s*구독중|심민규|북마크|공유하기|카카오톡|페이스북|메신저|네이버\s*밴드|URL\s*복사|프린트|제보', p) for p in paras) or any(re.search(r'폰트\s*\d단계|글자크기|북마크|카카오톡|페이스북|URL\s*복사', s) for s in summary_pts)
        has_bracket_tag = bool(re.search(r'^\[[^\]]+\]', current_ai_t)) or any('촬영' in s for s in summary_pts)
        has_awkward_title = '고부가 제품군' in current_ai_t and '고부가' not in orig_t
        has_duplicate_summary = len(summary_pts) > 1 and len(summary_pts) != len(set(summary_pts))
        is_abstract_template = any('단순한 일회성 현상에 그치지 않고' in p for p in paras)
        has_double_dot = any('..' in p for p in paras)
        is_same_as_raw = (current_ai_t == existing.get('original_title')) or (current_ai_t == orig_t)
        is_meaningless = is_meaningless_news(existing.get('original_title', ''), text=" ".join(paras))
        is_too_short = sum(len(p) for p in paras) < 500 or len(paras) < 8
        has_incomplete_summary = any(
            re.search(r'[\s,]+(?:을|를|이|가|에|의|과|와|로|으로|는|은|도|며|고|서|이라는|라고)$', s.strip()) or
            s.strip().endswith(('‘', '’', '“', '”', '\"', '\'')) or
            ('”고' in s or '’고' in s or '을”' in s or '를”' in s) or
            (not s.strip().endswith(('다', '다.', '요', '습니다', '했습니다', '밝혔습니다', '전했습니다', '분석했습니다', '강조했습니다', '말했습니다', '비판했습니다', '꼬집었습니다', '전망', '분석', '대책', '기록', '추진', '밝혀', '보고')))
            for s in summary_pts
        )

        # 결함(웹 찌꺼기 텍스트, 방송 출연진, 너무 짧은 볼륨, 불완전 요약, 원문과 동일한 제목 등) 감지 시 재구성 실행
        if has_web_junk or has_caption_junk or has_host_junk or has_bracket_tag or has_awkward_title or has_duplicate_summary or is_abstract_template or has_double_dot or is_same_as_raw or is_meaningless or is_too_short or has_incomplete_summary:
            pass # 건너뛰어 아래 3단계 build_full_news_article 실행
        else:
            publisher = existing.get('source_name')
            if not publisher or publisher == '주요 언론사':
                p_name, _ = get_publisher_info(url)
                publisher = p_name if (p_name and p_name != '주요 언론사') else '주요 언론사'

            current_ai_title = existing.get('ai_title', '')
            if not current_ai_title or current_ai_title == orig_t or current_ai_title == existing.get('original_title'):
                final_title = rewrite_news_title(orig_t, category=existing.get('category', '전체'))
            else:
                final_title = clean_news_title(current_ai_title)

            if summary_pts and (summary_pts[0] == orig_t or summary_pts[0] == existing.get('original_title')):
                summary_pts[0] = final_title

            current_img = existing.get('ai_image', '')
            is_crime_news = bool(re.search(r'시신|살인|피의자|검거|체포|구속|경찰|수사|용의자|사건|참사|범죄|냉동창고', orig_t))
            is_sports_img = any(s in current_img for s in ['photo-1579952363873', 'photo-1461896836934', 'photo-1574629810360', 'photo-1431324155629', 'photo-1540747913346', 'photo-1534438327276'])
            if not current_img or ('현대차' in orig_t and current_img != '/static/img/ai/hyundai_car.jpg') or (is_crime_news and is_sports_img):
                current_img = get_premium_stock_image(final_title, text=orig_t, category=existing.get('category', '사회' if is_crime_news else '전체'))

            # 카카오톡/SNS 링크 공유용 원본 기사 사진 추출 (사이트 본문에서는 current_img AI 이미지 유지)
            raw_origin_img = ai_cnt.get('og_img')
            if not raw_origin_img or 'unsplash.com' in raw_origin_img:
                raw_origin_img = get_raw_origin_image(url)

            result = {
                'id': existing.get('id'),
                'title': final_title,
                'original_title': existing.get('original_title'),
                'publisher': publisher,
                'pub_logo': '📰',
                'pub_date': existing.get('published_at', ''),
                'author': '',
                'main_img': current_img,
                'og_img': raw_origin_img or current_img,
                'caption': '',
                'summary_points': summary_pts,
                'paragraphs': paras,
                'url': existing.get('original_url') or url,
                'is_rewritten': True,
                'is_curated': True
            }
            ARTICLE_CACHE[url] = (now_ts, result)
            return result

    # 2. RSS 캐시에서 메타데이터 추출 (원문 웹페이지 본문 스크래핑 ❌ 절대 안 함)
    site_cfg = load_site_config()
    cluster_match = None
    with RSS_CACHE_LOCK:
        for cat, entry in RSS_CACHE.items():
            for item in entry.get('news', []):
                if item.get('link') == url:
                    cluster_match = item
                    break
            if cluster_match:
                break

    publisher, pub_logo = get_publisher_info(url)
    category = '전체'
    raw_title = ''
    pub_date = datetime.now().strftime('%m.%d %H:%M')

    if cluster_match:
        category = cluster_match.get('category', '전체')
        raw_title = cluster_match.get('title', '')
        pub_date = cluster_match.get('date', pub_date)
        if cluster_match.get('source'):
            publisher = cluster_match['source']

    if not raw_title:
        # RSS 캐시 미매칭 → 원본 페이지 og:title 실시간 스크랩으로 실제 기사 제목 복원
        raw_title = get_raw_origin_title(url) or "실시간 주요 뉴스 속보"

    # 3. 공개 헤드라인을 기반으로 독자적 이슈 분석 브리핑 리포트 생성 (원문 본문 전달 일절 없음)
    art = build_full_news_article(raw_title, site_cfg=site_cfg, url=url, category=category, publisher_name=publisher)

    # 카카오톡/SNS 링크 공유용 원본 기사 사진 추출 (사이트 본문에서는 art['main_img'] AI 이미지 유지)
    raw_origin_img = get_raw_origin_image(url)

    result = {
        'id': '',
        'title': art['title'],
        'original_title': raw_title,
        'publisher': publisher,
        'pub_logo': pub_logo,
        'pub_date': pub_date,
        'author': '',
        'main_img': art['main_img'],
        'og_img': raw_origin_img or art['main_img'],
        'caption': '',
        'summary_points': art['summary_points'],
        'paragraphs': art['paragraphs'],
        'url': url,
        'is_rewritten': True,
        'is_curated': True
    }
    ARTICLE_CACHE[url] = (now_ts, result)
    return result


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
            from services.ai_rewriter import clean_news_summary, clean_news_title
            with open(NEWS_SNAPSHOT_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                with RSS_CACHE_LOCK:
                    for cat, news_list in data.items():
                        # 스냅샷 기사들의 요약 및 제목에서도 바이라인/동향분석 꼬리표 완전 제거
                        for n in news_list:
                            if n.get('summary'):
                                n['summary'] = clean_news_summary(n['summary'])
                            if n.get('title'):
                                n['title'] = clean_news_title(n['title'])
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
    """언론사 RSS를 병렬 수집하고, 중복 기사를 클러스터링(이슈별 묶기)하여 상업적 라이선스 안전 이미지와 매칭"""
    from services.news_cluster import cluster_news_items
    from services.image_enhancer import get_premium_stock_image, NEWS_STOCK_CATALOG

    feeds_config = load_feeds_config()
    raw_feeds = feeds_config.get(category, feeds_config.get('전체', []))
    # 이용약관 상 상업적 재사용 제한 소스 필터링 On/Off
    feeds = [f for f in raw_feeds if f.get('enabled', True) and f.get('commercial_allowed', True) is not False]

    all_raw_news = []
    results = {}

    def fetch_worker(feed_info, key):
        items = fetch_rss(feed_info['url'], feed_info['name'], feed_info.get('logo', '📰'), max_per_feed)
        results[key] = items

    threads = []
    for i, feed_info in enumerate(feeds):
        t = threading.Thread(target=fetch_worker, args=(feed_info, i))
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=2.5)
    for i in range(len(feeds)):
        for it in results.get(i, []):
            it['category'] = category
            all_raw_news.append(it)

    # 1. 사건/이슈별 중복 기사 클러스터링 (제목 유사도 & 핵심 명사 결합)
    clusters = cluster_news_items(all_raw_news)

    # 2. 클러스터별 대표 기사 포맷팅 및 안전 이미지 매칭 (중복 방지 및 언론사명 비노출)
    curated_items = []
    used_page_images = set()

    for cl in clusters:
        primary = cl['primary']
        raw_title = primary.get('title', '')
        link = primary.get('link', '')
        cluster_sources = cl.get('cluster_sources', [])
        cluster_count = len(cluster_sources)

        from services.ai_rewriter import is_meaningless_news, clean_news_title, rewrite_news_title

        # 실질적 뉴스 가치가 없는 글(방송 예고, 유튜브 안내, 운세, 인사 등) 배제
        if is_meaningless_news(raw_title, primary.get('summary', '')):
            continue

        cleaned_title = clean_news_title(raw_title)
        if not cleaned_title or len(cleaned_title) < 6:
            continue

        # 원문 제목과 100% 동일하지 않도록 독창적 뉴스 헤드라인으로 재구성
        display_title = rewrite_news_title(cleaned_title, category=category)

        # 상업적 무상 스톡 이미지 매칭 (페이지 내 이미지 중복 방지)
        safe_img = get_premium_stock_image(display_title, primary.get('summary', ''), category=category, used_images=used_page_images)

        # 언론사명(연합뉴스, 한겨레 등) 직접 노출 배제 -> 카테고리/실시간 브리핑으로 대체
        display_source = f"{category} 속보" if category and category != '전체' else "실시간 속보"
        if cluster_count > 1:
            display_source = f"종합 이슈 ({cluster_count}개사)"

        curated_items.append({
            'title': display_title,
            'original_title': raw_title,
            'link': link,
            'summary': primary.get('summary', ''),
            'image': safe_img,
            'date': primary.get('date', ''),
            'source': display_source,
            'logo': '⚡',
            'category': category,
            'cluster_count': cluster_count,
            'cluster_sources': cluster_sources
        })

    return curated_items

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

def auto_rss_refresh_daemon():
    """서버 시작 시 사전 캐시를 빌드하고, 이후 3분마다 24시간 실시간 최신 뉴스를 자동 수집/대체"""
    time.sleep(1)
    while True:
        try:
            feeds_config = load_feeds_config()
            target_cats = list(feeds_config.keys()) if feeds_config else ['전체', '경제', '부동산', '정치', '사회', '증권', '연예', 'IT/과학', '스포츠']
            for cat in target_cats[:7]:
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
                time.sleep(1.5)
            save_snapshot()
        except Exception as e:
            print(f"[Auto RSS Refresh Error]: {e}")
        time.sleep(180)  # 3분(180초)마다 자동으로 새로운 뉴스를 수집해 교체

# 24시간 실시간 뉴스 자동 갱신 데몬 시작
threading.Thread(target=auto_rss_refresh_daemon, daemon=True).start()

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

@app.route('/admin/api/visitor_stats/sync', methods=['POST'])
def admin_sync_visitor_stats():
    """관리자가 수동으로 방문자 통계를 GitHub에 즉시 백업/동기화"""
    if not is_admin():
        abort(403)
    visitor_tracker._sync_to_github()
    return jsonify({'success': True, 'message': '방문자 통계가 GitHub에 안전하게 동기화되었습니다.'})

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

def guess_news_category(title, text=""):
    combined = f"{title} {text}".lower()
    if any(k in combined for k in ['아파트', '분양', '전세', '월세', '부동산', '재개발', '재건축', '청약', '국토부', '집값', '매매가', '공인중개사']):
        return '부동산'
    if any(k in combined for k in ['코스피', '코스닥', '나스닥', '증시', '주가', '목표가', '상한가', '하한가', '외국인 순매수', '기관 순매도', 'etf', '배당금', '공매도']):
        return '증권'
    if any(k in combined for k in ['금리', '환율', '물가', '한국은행', '기재부', '수출', '수입', '무역수지', '인플레이션', '성장률', '금융위', '소비자물가', '매출', '영업이익']):
        return '경제'
    if any(k in combined for k in ['대통령', '국회', '의원', '민주당', '국민의힘', '야당', '여당', '청문회', '특검', '국정감사', '당대표', '원내대표', '총선', '대선', '장관']):
        return '정치'
    if any(k in combined for k in ['ai', '인공지능', '반도체', '챗gpt', '스마트폰', '소프트웨어', '우주선', '로봇', '양자', '클라우드', '빅데이터', '통신사', '5g', '애플', '삼성전자']):
        return 'IT/과학'
    if any(k in combined for k in ['아이돌', '가수', '배우', '드라마', '영화', '음원', '콘서트', '빌보드', '스타', '결혼', '열애', '방탄소년단', 'bts', '블랙핑크', '예능']):
        return '연예'
    if any(k in combined for k in ['축구', '야구', '골프', '손흥민', '이강인', '김하성', '오타니', '올림픽', '월드컵', 'k리그', 'kbo', '메이저리그', '프리미어리그', '우승']):
        return '스포츠'
    if any(k in combined for k in ['경찰', '검찰', '법원', '재판', '구속', '사고', '화재', '날씨', '지진', '태풍', '침수', '병원', '복지', '노동자', '환경']):
        return '사회'
    return '전체'

@app.route('/admin/api/custom_news/add', methods=['POST'])
def admin_add_custom_news():
    """
    관리자가 원하는 뉴스 링크(URL)를 입력하면,
    자동으로 기사를 수집/분석하고 AI 리라이팅을 거쳐 지정된 카테고리 및 홈페이지 최상단에 즉시 추가!
    """
    if not is_admin():
        abort(403)

    data = request.get_json(silent=True) or {}
    url = (data.get('url') or '').strip()
    selected_cat = (data.get('category') or 'auto').strip()

    if not url or not url.startswith('http'):
        return jsonify({'success': False, 'message': '올바른 뉴스 기사 URL(http:// 또는 https://)을 입력해주세요.'})

    try:
        from services.ai_rewriter import (
            extract_factual_data,
            build_full_news_article,
            rewrite_news_title,
            clean_news_summary,
            clean_news_title
        )
        from services.image_enhancer import get_premium_stock_image

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=7.0)
        if resp.status_code != 200:
            return jsonify({'success': False, 'message': f'기사 페이지에 접속하지 못했습니다. (응답코드 {resp.status_code})'})

        html_text = decode_html_bytes(resp.content, resp.headers)
        soup = BeautifulSoup(html_text, 'html.parser')

        # 1. 원문 제목 추출
        og_t = soup.find('meta', property='og:title') or soup.find('meta', attrs={'name': 'title'})
        raw_title = (og_t.get('content') if og_t else '') or (soup.title.string if soup.title else '')
        raw_title = clean_html(raw_title)
        raw_title = re.sub(r'\s*[-|ㅣ].*$', '', raw_title).strip()

        if not raw_title:
            return jsonify({'success': False, 'message': '해당 링크에서 기사 제목을 추출할 수 없습니다.'})

        # 2. 언론사 추출
        publisher, pub_logo = get_publisher_info(url, soup=soup)

        # 3. 원문 대표 사진 (카카오톡/SNS 공유용)
        og_img_tag = soup.find('meta', property='og:image') or soup.find('meta', attrs={'name': 'image'})
        raw_origin_img = normalize_img_url(og_img_tag.get('content')) if og_img_tag else ''

        # 4. 본문 팩트 데이터 추출
        fact_points = extract_factual_data(url, raw_title)

        # 5. 카테고리 결정
        if selected_cat == 'auto' or not selected_cat or selected_cat == '전체':
            body_sample = " ".join(fact_points[:5])
            target_category = guess_news_category(raw_title, body_sample)
        else:
            target_category = selected_cat

        # 6. AI 뉴스 기사 전면 빌드
        site_cfg = load_site_config()
        art = build_full_news_article(raw_title, site_cfg=site_cfg, url=url, category=target_category, publisher_name=publisher, raw_paragraphs=fact_points)

        # 7. 기사 썸네일 & 시간
        final_thumb = art['main_img']
        now_date_str = datetime.now(KST).strftime('%m.%d %H:%M')

        # 8. 요약문
        summary_text = ""
        if art.get('summary_points'):
            summary_text = " ".join(art['summary_points'][:2])
        elif fact_points:
            summary_text = " ".join(fact_points[:2])
        if len(summary_text) > 150:
            summary_text = summary_text[:150] + '...'

        new_item = {
            'title': art['title'],
            'original_title': raw_title,
            'link': url,
            'summary': summary_text,
            'image': final_thumb,
            'og_img': raw_origin_img or final_thumb,
            'date': now_date_str,
            'source': publisher,
            'logo': pub_logo or '📰',
            'category': target_category,
            'is_custom': True
        }

        # 9. RSS_CACHE 최상단에 즉각 반영
        with RSS_CACHE_LOCK:
            if target_category not in RSS_CACHE:
                RSS_CACHE[target_category] = {'timestamp': time.time(), 'news': [], 'count': 0, 'is_refreshing': False}
            RSS_CACHE[target_category]['news'] = [n for n in RSS_CACHE[target_category].get('news', []) if n.get('link') != url]
            RSS_CACHE[target_category]['news'].insert(0, new_item)
            RSS_CACHE[target_category]['count'] = len(RSS_CACHE[target_category]['news'])
            RSS_CACHE[target_category]['timestamp'] = time.time()

            if '전체' not in RSS_CACHE:
                RSS_CACHE['전체'] = {'timestamp': time.time(), 'news': [], 'count': 0, 'is_refreshing': False}
            RSS_CACHE['전체']['news'] = [n for n in RSS_CACHE['전체'].get('news', []) if n.get('link') != url]
            RSS_CACHE['전체']['news'].insert(0, new_item)
            RSS_CACHE['전체']['count'] = len(RSS_CACHE['전체']['news'])
            RSS_CACHE['전체']['timestamp'] = time.time()

        # 10. 스냅샷 영구 저장
        save_snapshot()

        return jsonify({
            'success': True,
            'message': f'[{target_category}] 카테고리 및 전체 홈 최상단에 성공적으로 등록되었습니다!',
            'item': new_item
        })

    except Exception as e:
        print(f"[Custom News Add Error]: {e}")
        return jsonify({'success': False, 'message': f'처리 중 오류가 발생했습니다: {str(e)}'})

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
        image = article_data.get('og_img') or article_data.get('main_img') or ''

        # 4. 우리 사이트 배포 URL 기준 뷰어 링크 구성
        base_host = "https://news-now-82jg.onrender.com"
        our_article_url = f"{base_host}/article?url={urllib.parse.quote(target_news_url)}"

        # 5. 네이버 공식 우회 브릿지 링크 (link.naver.com - 모바일에서 네이버홈으로 튕기지 않도록 dst 명시)
        naver_bridge_url = f"https://link.naver.com/bridge?url={urllib.parse.quote(our_article_url)}&dst={urllib.parse.quote(our_article_url)}"

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

# ---- AI 리라이팅 & 이미지 즉시 테스트 API ----
@app.route('/admin/api/test_ai_rewrite', methods=['POST'])
def admin_test_ai_rewrite():
    if not is_admin():
        abort(403)
    data = request.get_json() or {}
    news_url = (data.get('url') or '').strip()
    if not news_url:
        return jsonify({'success': False, 'message': '뉴스 기사 URL을 입력해주세요.'})
    try:
        art = fetch_article_detail(news_url)
        if not art:
            return jsonify({'success': False, 'message': '기사를 불러올 수 없습니다.'})
        return jsonify({
            'success': True,
            'title': art.get('title'),
            'original_title': art.get('original_title', art.get('title')),
            'main_img': art.get('main_img'),
            'publisher': art.get('publisher'),
            'paragraphs': art.get('paragraphs', [])[:4],
            'is_rewritten': art.get('is_rewritten', False)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'테스트 오류: {str(e)}'})

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
