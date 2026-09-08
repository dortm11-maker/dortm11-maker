import sqlite3
import os
import json
import hashlib
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
DB_FILE = os.path.join(DB_DIR, 'curated_news.db')

def get_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS curated_articles (
                id TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                original_title TEXT NOT NULL,
                original_url TEXT NOT NULL UNIQUE,
                published_at TEXT,
                category TEXT,
                keywords TEXT,
                ai_title TEXT,
                ai_content TEXT,
                ai_image TEXT,
                cluster_sources TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_curated_cat ON curated_articles(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_curated_url ON curated_articles(original_url)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_curated_created ON curated_articles(created_at DESC)")
        conn.commit()

def generate_article_id(url):
    return hashlib.sha256(url.strip().encode('utf-8')).hexdigest()[:16]

def save_curated_article(data):
    """
    저장 항목: id, source_name, original_title, original_url, published_at, category, keywords, ai_title, ai_content, ai_image, cluster_sources, created_at
    ※ 원문 기사 본문 전체나 원본 이미지 파일/URL은 절대 저장하지 않음.
    """
    url = data.get('original_url') or data.get('link', '')
    if not url:
        return None

    art_id = data.get('id') or generate_article_id(url)
    
    keywords = data.get('keywords', [])
    if isinstance(keywords, (list, tuple)):
        keywords_str = json.dumps(keywords, ensure_ascii=False)
    else:
        keywords_str = str(keywords or '')

    ai_content = data.get('ai_content', {})
    if isinstance(ai_content, (dict, list)):
        ai_content_str = json.dumps(ai_content, ensure_ascii=False)
    else:
        ai_content_str = str(ai_content or '')

    cluster_sources = data.get('cluster_sources', [])
    if isinstance(cluster_sources, (list, tuple)):
        cluster_sources_str = json.dumps(cluster_sources, ensure_ascii=False)
    else:
        cluster_sources_str = str(cluster_sources or '')

    with get_db() as conn:
        conn.execute("""
            INSERT INTO curated_articles (
                id, source_name, original_title, original_url, published_at,
                category, keywords, ai_title, ai_content, ai_image, cluster_sources, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(original_url) DO UPDATE SET
                ai_title = excluded.ai_title,
                ai_content = excluded.ai_content,
                ai_image = excluded.ai_image,
                cluster_sources = excluded.cluster_sources,
                keywords = excluded.keywords
        """, (
            art_id,
            data.get('source_name') or data.get('source', '주요 언론사'),
            data.get('original_title') or data.get('title', ''),
            url,
            data.get('published_at') or data.get('date', ''),
            data.get('category', '전체'),
            keywords_str,
            data.get('ai_title') or data.get('title', ''),
            ai_content_str,
            data.get('ai_image', ''),
            cluster_sources_str
        ))
        conn.commit()

    return art_id

def get_curated_article_by_url(url):
    if not url:
        return None
    with get_db() as conn:
        row = conn.execute("SELECT * FROM curated_articles WHERE original_url = ?", (url,)).fetchone()
        if not row:
            return None
        return parse_curated_row(row)

def get_curated_article_by_id(art_id):
    if not art_id:
        return None
    with get_db() as conn:
        row = conn.execute("SELECT * FROM curated_articles WHERE id = ?", (art_id,)).fetchone()
        if not row:
            return None
        return parse_curated_row(row)

def parse_curated_row(row):
    d = dict(row)
    try:
        d['keywords'] = json.loads(d.get('keywords') or '[]')
    except:
        d['keywords'] = [k.strip() for k in (d.get('keywords') or '').split(',') if k.strip()]

    try:
        d['ai_content'] = json.loads(d.get('ai_content') or '{}')
    except:
        d['ai_content'] = {'raw': d.get('ai_content', '')}

    try:
        d['cluster_sources'] = json.loads(d.get('cluster_sources') or '[]')
    except:
        d['cluster_sources'] = []

    return d

def get_recent_curated_articles(category='전체', limit=40):
    with get_db() as conn:
        if category == '전체':
            rows = conn.execute(
                "SELECT * FROM curated_articles ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM curated_articles WHERE category = ? ORDER BY created_at DESC LIMIT ?", (category, limit)
            ).fetchall()
        return [parse_curated_row(r) for r in rows]

def delete_curated_article(url):
    """지정된 원문 URL의 큐레이션 기사를 DB에서 완전히 삭제"""
    if not url:
        return False
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM curated_articles WHERE original_url = ?", (url.strip(),))
            conn.commit()
        return True
    except Exception as e:
        print(f"[delete_curated_article error]: {e}")
        return False

# 앱 시작 시 DB 초기화
init_db()
