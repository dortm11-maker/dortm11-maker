/* =============================================
   뉴스NOW - 메인 JavaScript (일반 사용자용)
   ============================================= */

let allNews = [];
let displayedCount = 0;
const PAGE_SIZE = 40;
let currentCategory = '전체';

// ============================================================
// 초기화
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    updateDate();
    setInterval(updateDate, 60000);

    // 티커 무한 스크롤 설정
    initTicker();

    // 광고 초기화
    initAds();

    // URL 파라미터로 카테고리가 넘어온 경우 처리 (예: /?cat=정치)
    const urlParams = new URLSearchParams(window.location.search);
    const initialCat = urlParams.get('cat') || '전체';
    switchCategory(initialCat);
});


function updateDate() {
    const el = document.getElementById('currentDate');
    if (!el) return;
    const now = new Date();
    const days = ['일', '월', '화', '수', '목', '금', '토'];
    el.textContent = `${now.getMonth()+1}.${now.getDate()}(${days[now.getDay()]})`;
}

// ============================================================
// 카테고리 전환
// ============================================================
function switchCategory(cat) {
    currentCategory = cat;

    // GNB 활성화
    document.querySelectorAll('.gnb-item').forEach(el => {
        const itemCat = el.dataset.category || (el.textContent.trim() === '홈' ? '전체' : el.textContent.trim());
        el.classList.toggle('active', itemCat === cat);
    });

    // 섹션 제목
    const headingEl = document.getElementById('sectionHeading');
    if (headingEl) headingEl.textContent = cat === '전체' ? '최신 뉴스' : cat;

    loadNews(cat);
}

// ============================================================
// 초고속 브라우저 로컬 캐시 & 스켈레톤 관리
// ============================================================
const LOCAL_CACHE_PREFIX = 'news_cache_v4_';

function getLocalCache(category) {
    try {
        const raw = localStorage.getItem(LOCAL_CACHE_PREFIX + category);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        // 캐시가 20분 이내인 경우 즉시 활용
        if (Date.now() - parsed.savedAt < 20 * 60 * 1000) {
            return parsed.news;
        }
    } catch (e) {}
    return null;
}

function setLocalCache(category, news) {
    try {
        localStorage.setItem(LOCAL_CACHE_PREFIX + category, JSON.stringify({
            savedAt: Date.now(),
            news: news.slice(0, 90)
        }));
    } catch (e) {}
}

function showSkeleton() {
    const headlineSection = document.getElementById('headlineSection');
    const newsGrid = document.getElementById('newsGrid');
    const layout = document.getElementById('newsLayout');
    const loadingScreen = document.getElementById('loadingScreen');

    if (loadingScreen) loadingScreen.style.display = 'none';
    if (layout) layout.style.display = 'block';

    if (headlineSection) {
        headlineSection.innerHTML = `
            <div class="headline-grid skeleton-container">
                <div class="headline-card skeleton-card">
                    <div class="headline-img-wrap skeleton-box"></div>
                    <div class="headline-body">
                        <div class="skeleton-line short"></div>
                        <div class="skeleton-line title"></div>
                        <div class="skeleton-line text"></div>
                    </div>
                </div>
                <div class="headline-card skeleton-card">
                    <div class="headline-img-wrap skeleton-box"></div>
                    <div class="headline-body">
                        <div class="skeleton-line short"></div>
                        <div class="skeleton-line title"></div>
                        <div class="skeleton-line text"></div>
                    </div>
                </div>
            </div>`;
    }

    if (newsGrid) {
        newsGrid.innerHTML = Array(6).fill(0).map(() => `
            <div class="news-card skeleton-card">
                <div class="news-card-img-wrap skeleton-box"></div>
                <div class="news-card-body">
                    <div class="skeleton-line short"></div>
                    <div class="skeleton-line title"></div>
                    <div class="skeleton-line date"></div>
                </div>
            </div>
        `).join('');
    }
}

// ============================================================
// 뉴스 로딩 - 눈에 보이는 상단 헤드라인 먼저 출력 & 아래 연결
// ============================================================
async function loadNews(category) {
    displayedCount = 0;

    // 1. 브라우저 로컬 캐시가 있으면 -> 0.00초 만에 상단부터 즉시 출력!
    const cached = getLocalCache(category);
    if (cached && cached.length > 0) {
        renderTopFirst(cached);
    } else {
        // 첫 방문 등으로 캐시가 전혀 없으면 -> 빛나는 스켈레톤 즉시 표시 (흰 공백 화면 방지)
        showSkeleton();
    }

    // 2. 서버(Render)에서 실시간 최신 뉴스 수신
    try {
        const resp = await fetch(`/api/rss?category=${encodeURIComponent(category)}&max=15`);
        const data = await resp.json();

        if (data.success && data.news && data.news.length > 0) {
            setLocalCache(category, data.news);
            // 최신 데이터 도착 시 상단부터 스르륵 최신화
            renderTopFirst(data.news);
        }
    } catch (e) {
        console.error('뉴스 로딩 오류:', e);
        if (!cached || cached.length === 0) {
            const grid = document.getElementById('newsGrid');
            if (grid) {
                grid.innerHTML = `<div class="empty-state">뉴스를 불러오는 중입니다. 잠시 후 새로고침해주세요.</div>`;
            }
        }
    }
}

// ============================================================
// 점진적 렌더링: 상단 2개 대형 헤드라인 우선 출력 후 아래 그리드 연결
// ============================================================
function renderTopFirst(newsList) {
    allNews = newsList;

    const layout = document.getElementById('newsLayout');
    const loadingScreen = document.getElementById('loadingScreen');
    if (loadingScreen) loadingScreen.style.display = 'none';
    if (layout) layout.style.display = 'block';

    // 1단계: 사용자 눈에 가장 먼저 보이는 최상단 헤드라인 2개 즉각 렌더링!
    renderHeadlines();

    // 2단계: 헤드라인 렌더링 직후 자연스럽게 아래 뉴스 그리드 연결
    requestAnimationFrame(() => {
        renderGrid();
        const countEl = document.getElementById('sectionCount');
        if (countEl) countEl.textContent = `${allNews.length}건`;
    });
}

// ============================================================
// 이미지 로딩 실패 시 프록시 2차 우회 및 안전 플레이스홀더 처리
// ============================================================
function handleImgError(img, originalUrl, isHeadline) {
    if (!img.dataset.retried && originalUrl && originalUrl.startsWith('http')) {
        img.dataset.retried = 'true';
        img.src = `/api/image_proxy?url=${encodeURIComponent(originalUrl)}`;
        return;
    }
    const cls = isHeadline ? 'headline-img-placeholder' : 'news-card-img-placeholder';
    if (img.parentElement) {
        img.parentElement.innerHTML = `<div class="${cls}">📰</div>`;
    }
}

// ============================================================
// 헤드라인 & 그리드 렌더링
// ============================================================
function renderHeadlines() {
    const section = document.getElementById('headlineSection');
    if (!section || allNews.length === 0) return;

    // 이미지 있는 것 우선, 없으면 상위 2개
    const withImg = allNews.filter(n => n.image);
    const top2 = withImg.length >= 2 ? withImg.slice(0, 2) : allNews.slice(0, 2);

    section.innerHTML = `<div class="headline-grid">` + top2.map(item => createHeadlineCard(item)).join('') + `</div>`;
}

function renderGrid() {
    const grid = document.getElementById('newsGrid');
    if (!grid) return;

    // 상단에 나간 헤드라인 2개 제외하고 목록 구성
    const withImg = allNews.filter(n => n.image);
    const top2 = withImg.length >= 2 ? withImg.slice(0, 2) : allNews.slice(0, 2);
    const top2Links = new Set(top2.map(t => t.link));
    const rest = allNews.filter(n => !top2Links.has(n.link));

    const toShow = rest.slice(0, PAGE_SIZE);
    displayedCount = toShow.length;

    if (toShow.length === 0) {
        grid.innerHTML = `<div class="empty-state">표시할 뉴스가 없습니다.</div>`;
    } else {
        grid.innerHTML = toShow.map(item => createNewsCard(item)).join('');
        resolveMissingImages();
    }

    const moreWrap = document.getElementById('moreWrap');
    if (moreWrap) {
        moreWrap.style.display = (rest.length > displayedCount) ? 'block' : 'none';
    }
}

function loadMore() {
    const grid = document.getElementById('newsGrid');
    if (!grid) return;

    const withImg = allNews.filter(n => n.image);
    const top2 = withImg.length >= 2 ? withImg.slice(0, 2) : allNews.slice(0, 2);
    const top2Links = new Set(top2.map(t => t.link));
    const rest = allNews.filter(n => !top2Links.has(n.link));

    const nextItems = rest.slice(displayedCount, displayedCount + PAGE_SIZE);
    grid.insertAdjacentHTML('beforeend', nextItems.map(item => createNewsCard(item)).join(''));
    displayedCount += nextItems.length;
    resolveMissingImages();

    const moreWrap = document.getElementById('moreWrap');
    if (moreWrap) {
        moreWrap.style.display = (rest.length > displayedCount) ? 'block' : 'none';
    }
}

// ============================================================
// 카드 생성 - 클릭 시 사이트 내부 자체 기사 뷰어(/article)로 연결
// ============================================================
function getArticleUrl(link) {
    if (!link || link === '#') return '#';
    return `/article?url=${encodeURIComponent(link)}`;
}

// ============================================================
// 기사 클릭 초고속화: 마우스 오버 시 사전 로딩 & 클릭 시 즉시 프로그레스바
// ============================================================
const prefetchSet = new Set();
function prefetchArticle(link) {
    if (!link || link === '#' || prefetchSet.has(link)) return;
    prefetchSet.add(link);
    // 마우스가 카드 위로 올라가는 0.2~0.3초 사이에 서버가 기사를 미리 캐싱해둠!
    fetch(`/api/article?url=${encodeURIComponent(link)}`, { priority: 'low' }).catch(() => {});
}

function onCardClick() {
    let bar = document.getElementById('topLoadingBar');
    if (!bar) {
        bar = document.createElement('div');
        bar.id = 'topLoadingBar';
        bar.style.position = 'fixed';
        bar.style.top = '0';
        bar.style.left = '0';
        bar.style.height = '3px';
        bar.style.width = '0%';
        bar.style.backgroundColor = '#1a56db';
        bar.style.zIndex = '99999';
        bar.style.transition = 'width 0.2s cubic-bezier(0.1, 0.9, 0.2, 1)';
        bar.style.boxShadow = '0 0 10px rgba(26, 86, 219, 0.9)';
        document.body.appendChild(bar);
    }
    bar.style.display = 'block';
    bar.style.width = '0%';
    setTimeout(() => { bar.style.width = '75%'; }, 10);
    setTimeout(() => { bar.style.width = '96%'; }, 180);
}

function createHeadlineCard(item) {
    const hasImg = item.image && item.image.trim() !== '';
    const targetUrl = getArticleUrl(item.link);
    return `
    <a class="headline-card" href="${targetUrl}"
       onmouseenter="prefetchArticle('${escAttr(item.link)}')"
       ontouchstart="prefetchArticle('${escAttr(item.link)}')"
       onclick="onCardClick()">
        <div class="headline-img-wrap">
            ${hasImg
                ? `<img class="headline-img" src="${escAttr(item.image)}" alt="" loading="lazy"
                       referrerpolicy="no-referrer"
                       onerror="handleImgError(this, '${escAttr(item.image)}', true)">`
                : `<div class="headline-img-placeholder">📰</div>`}
        </div>
        <div class="headline-body">
            <div class="headline-source">
                <span class="headline-source-dot"></span>
                ${esc(item.source)}
            </div>
            <div class="headline-title">${esc(item.title)}</div>
            ${item.summary ? `<div class="headline-summary">${esc(item.summary)}</div>` : ''}
            <div class="headline-date">${esc(item.date)}</div>
        </div>
    </a>`;
}

function createNewsCard(item) {
    const hasImg = item.image && item.image.trim() !== '';
    const targetUrl = getArticleUrl(item.link);
    return `
    <a class="news-card" href="${targetUrl}"
       onmouseenter="prefetchArticle('${escAttr(item.link)}')"
       ontouchstart="prefetchArticle('${escAttr(item.link)}')"
       onclick="onCardClick()">
        <div class="news-card-img-wrap" ${!hasImg ? `data-fetch-img="${escAttr(item.link)}"` : ''}>
            ${hasImg
                ? `<img class="news-card-img" src="${escAttr(item.image)}" alt="" loading="lazy"
                       referrerpolicy="no-referrer"
                       onerror="handleImgError(this, '${escAttr(item.image)}', false)">`
                : `<div class="news-card-img-placeholder">📰</div>`}
        </div>
        <div class="news-card-body">
            <div class="news-card-source">${esc(item.logo)} ${esc(item.source)}</div>
            <div class="news-card-title">${esc(item.title)}</div>
            <div class="news-card-date">${esc(item.date)}</div>
        </div>
    </a>`;
}

function resolveMissingImages() {
    document.querySelectorAll('.news-card-img-wrap[data-fetch-img]').forEach(wrap => {
        const link = wrap.dataset.fetchImg;
        if (!link) return;
        delete wrap.dataset.fetchImg;
        fetch(`/api/get_image?url=${encodeURIComponent(link)}&category=${encodeURIComponent(currentCategory)}`)
            .then(res => res.json())
            .then(data => {
                if (data.success && data.image) {
                    wrap.innerHTML = `<img class="news-card-img" src="${escAttr(data.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="handleImgError(this, '${escAttr(data.image)}', false)">`;
                }
            })
            .catch(() => {});
    });
}

// ============================================================
// 유틸
// ============================================================
// 유틸
// ============================================================
function esc(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function escAttr(str) {
    if (!str) return '#';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;');
}

// ============================================================
// 티커 무한 스크롤
// ============================================================
function initTicker() {
    const track = document.getElementById('tickerTrack');
    if (!track) return;

    const cfg = window.SITE_CONFIG;
    const speed = cfg?.ticker?.speed || 35;
    track.style.setProperty('--ticker-speed', speed + 's');

    // 내용 복제해서 끊김 없는 무한 스크롤 구현
    const items = track.innerHTML;
    track.innerHTML = items + items; // 2번 반복하여 트랙 채움
}

// ============================================================
// 팝업 광고 초기화
// ============================================================
// ============================================================
// 팝업 광고 제어 (3초 카운트다운 & N분마다 재노출)
// ============================================================
let popupCanClose = false;
let popupCountdownTimer = null;

function initAds() {
    const cfg = window.SITE_CONFIG?.ads;
    if (!cfg || !cfg.popup || !cfg.popup.enabled) return;

    // 1) 초기 지연 시간 후 첫 전면광고 노출
    const delay = (cfg.popup.delay !== undefined ? cfg.popup.delay : 2) * 1000;
    setTimeout(() => {
        showPopup();
    }, delay);

    // 2) N분마다 자동 재노출 (0보다 크면 주기적 반복 실행)
    const intervalMin = parseInt(cfg.popup.interval_minutes) || 0;
    if (intervalMin > 0) {
        setInterval(() => {
            showPopup();
        }, intervalMin * 60 * 1000);
    }
}

function showPopup() {
    const overlay = document.getElementById('popupOverlay');
    if (!overlay) return;

    const btn = document.getElementById('popupCloseBtn');
    const cfg = window.SITE_CONFIG?.ads?.popup;
    let remaining = cfg?.close_delay !== undefined ? parseInt(cfg.close_delay) : 3;
    if (remaining < 1) remaining = 1;

    popupCanClose = false;
    if (btn) {
        btn.disabled = true;
        btn.textContent = remaining;
        btn.title = `${remaining}초 후 닫을 수 있습니다`;
    }

    overlay.style.display = 'flex';

    if (popupCountdownTimer) clearInterval(popupCountdownTimer);
    popupCountdownTimer = setInterval(() => {
        remaining--;
        if (remaining > 0) {
            if (btn) {
                btn.textContent = remaining;
                btn.title = `${remaining}초 후 닫을 수 있습니다`;
            }
        } else {
            clearInterval(popupCountdownTimer);
            popupCountdownTimer = null;
            popupCanClose = true;
            if (btn) {
                btn.disabled = false;
                btn.textContent = '✕';
                btn.title = '닫기';
            }
        }
    }, 1000);
}

function closePopup() {
    if (!popupCanClose) return; // 3초 카운트다운 전에는 닫히지 않음
    const overlay = document.getElementById('popupOverlay');
    if (overlay) overlay.style.display = 'none';
    if (popupCountdownTimer) {
        clearInterval(popupCountdownTimer);
        popupCountdownTimer = null;
    }
}

function onOverlayClick() {
    if (!popupCanClose) return; // 3초 카운트다운 전에는 배경을 클릭해도 닫히지 않음
    closePopup();
}




