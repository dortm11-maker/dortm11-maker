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

    // 첫 뉴스 로딩
    loadNews('전체');
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
// 뉴스 로딩
// ============================================================
async function loadNews(category) {
    document.getElementById('loadingScreen').style.display = 'flex';
    document.getElementById('newsLayout').style.display = 'none';
    allNews = [];
    displayedCount = 0;

    try {
        const resp = await fetch(`/api/rss?category=${encodeURIComponent(category)}&max=15&_t=${Date.now()}`);
        const data = await resp.json();

        if (data.success) {
            allNews = data.news;
            renderAll();
            document.getElementById('newsLayout').style.display = 'block';
        }
    } catch (e) {
        console.error(e);
        document.getElementById('newsLayout').innerHTML = `
            <div class="empty-state">뉴스를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.</div>`;
        document.getElementById('newsLayout').style.display = 'block';
    } finally {
        document.getElementById('loadingScreen').style.display = 'none';
    }
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
// 렌더링
// ============================================================
function renderAll() {
    renderHeadlines();
    renderGrid();
    const count = allNews.length;
    const countEl = document.getElementById('sectionCount');
    if (countEl) countEl.textContent = `${count}건`;
}

function renderHeadlines() {
    const section = document.getElementById('headlineSection');
    if (!section || allNews.length === 0) return;

    // 이미지 있는 것 우선, 없으면 그냥 상위 2개
    const withImg = allNews.filter(n => n.image);
    const top2 = withImg.length >= 2 ? withImg.slice(0, 2) : allNews.slice(0, 2);

    section.innerHTML = `<div class="headline-grid">` + top2.map(item => createHeadlineCard(item)).join('') + `</div>`;
}

function renderGrid() {
    const grid = document.getElementById('newsGrid');
    if (!grid) return;

    // 헤드라인 2개는 제외
    const rest = allNews.slice(2);
    const toShow = rest.slice(0, PAGE_SIZE);
    displayedCount = toShow.length;

    if (toShow.length === 0) {
        grid.innerHTML = `<div class="empty-state">표시할 뉴스가 없습니다.</div>`;
    } else {
        grid.innerHTML = toShow.map(item => createNewsCard(item)).join('');
    }

    const moreWrap = document.getElementById('moreWrap');
    if (moreWrap) {
        moreWrap.style.display = (rest.length > displayedCount) ? 'block' : 'none';
    }
}

function loadMore() {
    const grid = document.getElementById('newsGrid');
    if (!grid) return;
    const rest = allNews.slice(2);
    const nextItems = rest.slice(displayedCount, displayedCount + PAGE_SIZE);
    grid.insertAdjacentHTML('beforeend', nextItems.map(item => createNewsCard(item)).join(''));
    displayedCount += nextItems.length;

    const moreWrap = document.getElementById('moreWrap');
    if (moreWrap) {
        moreWrap.style.display = (rest.length > displayedCount) ? 'block' : 'none';
    }
}

// ============================================================
// 카드 생성 - 클릭 시 원문 바로 이동 (복사/원문 버튼 없음)
// ============================================================
function createHeadlineCard(item) {
    const hasImg = item.image && item.image.trim() !== '';
    return `
    <a class="headline-card" href="${escAttr(item.link)}" target="_blank" rel="noopener noreferrer">
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
    return `
    <a class="news-card" href="${escAttr(item.link)}" target="_blank" rel="noopener noreferrer">
        <div class="news-card-img-wrap">
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




