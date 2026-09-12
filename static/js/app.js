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
const LOCAL_CACHE_PREFIX = 'news_cache_v9_';

function getLocalCache(category) {
    try {
        const raw = localStorage.getItem(LOCAL_CACHE_PREFIX + category);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        // 캐시가 2분 이내인 경우 즉시 활용
        if (Date.now() - parsed.savedAt < 2 * 60 * 1000) {
            // 캐시 내 첫 기사가 오늘 기사인지 검사 (오늘 기사가 아니면 즉시 만료하여 최신 서버 데이터 수신)
            if (parsed.news && parsed.news.length > 0) {
                const firstDate = parsed.news[0].date || '';
                const now = new Date();
                const todayPrefix = String(now.getMonth() + 1).padStart(2, '0') + '.' + String(now.getDate()).padStart(2, '0');
                if (firstDate && !firstDate.startsWith(todayPrefix) && (Date.now() - parsed.savedAt > 15 * 1000)) {
                    return null;
                }
            }
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
    let initialDataRendered = false;

    // 1. 서버가 HTML과 함께 전달한 초기 뉴스(SSR)가 있으면 -> 0.00초 즉시 렌더링!
    if (category === '전체' && window.INITIAL_NEWS && window.INITIAL_NEWS.length > 0) {
        const ssrNews = window.INITIAL_NEWS;
        setLocalCache('전체', ssrNews);
        renderTopFirst(ssrNews);
        initialDataRendered = true;
        window.INITIAL_NEWS = null; // 1회 소비 후 초기화
    }

    // 2. 브라우저 로컬 캐시가 있으면 -> 0.00초 만에 상단부터 즉시 출력!
    if (!initialDataRendered) {
        const cached = getLocalCache(category);
        if (cached && cached.length > 0) {
            renderTopFirst(cached);
            initialDataRendered = true;
        } else {
            // 첫 방문 등으로 캐시가 전혀 없을 때만 스켈레톤 표시
            showSkeleton();
        }
    }

    // 3. 서버(Render)에서 실시간 최신 뉴스 수신 (백그라운드 비동기 최신화)
    try {
        const resp = await fetch(`/api/rss?category=${encodeURIComponent(category)}&max=15`);
        const data = await resp.json();

        if (data.success && data.news && data.news.length > 0) {
            setLocalCache(category, data.news);
            // 사용자가 아직 동일 카테고리에 머물고 있다면 최신 뉴스로 갱신
            if (currentCategory === category) {
                renderTopFirst(data.news);
            }

            // 서버 응답이 stale(콜드 부팅 이전 캐시)인 경우, 서버 백그라운드 갱신 완료 후 최신 뉴스 자동 재수신
            if (data.stale) {
                setTimeout(async () => {
                    if (currentCategory === category) {
                        try {
                            const freshResp = await fetch(`/api/rss?category=${encodeURIComponent(category)}&max=15&fresh=1`);
                            const freshData = await freshResp.json();
                            if (freshData.success && freshData.news && freshData.news.length > 0) {
                                setLocalCache(category, freshData.news);
                                if (currentCategory === category) {
                                    renderTopFirst(freshData.news);
                                }
                            }
                        } catch(e) {}
                    }
                }, 2500);
            }
        }
    } catch (e) {
        console.error('뉴스 로딩 오류:', e);
        if (!allNews || allNews.length === 0) {
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
// 이미지 로딩 실패 시 100% 검증된 안전 고화질 이미지 즉시 대체 (회색 플레이스홀더 배제)
// ============================================================
const SAFE_FALLBACK_IMAGES = [
    'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=600&q=80',
    'https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?auto=format&fit=crop&w=600&q=80',
    'https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=600&q=80',
    'https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=600&q=80',
    'https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?auto=format&fit=crop&w=600&q=80',
    'https://images.unsplash.com/photo-1558494949-ef010cbdcc31?auto=format&fit=crop&w=600&q=80',
    'https://images.unsplash.com/photo-1579952363873-27f3bade9f55?auto=format&fit=crop&w=600&q=80',
    'https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=600&q=80'
];

function getSafeFallback(seed) {
    const s = String(seed || '');
    let hash = 0;
    for (let i = 0; i < s.length; i++) hash = (hash * 31 + s.charCodeAt(i)) & 0xffffffff;
    return SAFE_FALLBACK_IMAGES[Math.abs(hash) % SAFE_FALLBACK_IMAGES.length];
}

function handleImgError(img, originalUrl, isHeadline) {
    img.onerror = null; // 무한 재귀 호출 방지
    img.src = getSafeFallback(originalUrl || img.src);
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

function formatNewsSource(source, category) {
    const cat = (category && category !== '전체') ? category : '';
    const defaultBadge = cat ? `${cat} 속보` : '실시간 속보';
    if (!source || typeof source !== 'string') return defaultBadge;
    const s = source.trim();
    const mediaPattern = /(연합뉴스|뉴스1|뉴시스|매일경제|한국경제|조선일보|동아일보|중앙일보|한겨레|경향신문|헤럴드경제|머니투데이|아시아경제|SBS|MBC|KBS|YTN|데일리안|이데일리|디지털타임스|전자신문|아이뉴스24|파이낸셜뉴스|로이터|AP|AFP|EPA|언론사)/i;
    if (mediaPattern.test(s)) {
        return defaultBadge;
    }
    if (s.includes('속보') || s.includes('이슈')) {
        return s;
    }
    return defaultBadge;
}

function cleanTitle(text) {
    if (!text) return '';
    let t = text.trim();
    t = t.replace(/(?:…|\.\.\.|\s)*동향\s*분석/g, '');
    t = t.replace(/[…\.\s]+$/, '');
    return t.trim();
}

function cleanSummary(text) {
    if (!text) return '';
    let t = text.trim();
    // 1. (도시=언론사) + [기자명 기자] = 바이라인 완벽 제거
    t = t.replace(/^\s*[\(\[][가-힣a-zA-Z\s]+=[가-힣a-zA-Z\s]+[\)\]]\s*(?:[가-힣]{2,4}\s*(?:기자|특파원|논설위원|연구위원|인턴기자)\s*)?=?\s*/i, '');
    // 2. 언론사명 괄호 제거
    t = t.replace(/[\(\[][^\)\]]*(?:연합뉴스|뉴스1|뉴시스|매일경제|한국경제|조선일보|동아일보|중앙일보|한겨레|경향신문|헤럴드경제|머니투데이|아시아경제|SBS|MBC|KBS|YTN|데일리안|이데일리|디지털타임스|전자신문|아이뉴스24|파이낸셜뉴스|로이터|AP|AFP|EPA|언론사)[^\)\]]*[\)\]]\s*(?:[가-힣]{2,4}\s*(?:기자|특파원|논설위원|연구위원|인턴기자)\s*)?=?\s*/gi, '');
    // 3. 사진/출처 괄호 제거
    t = t.replace(/[\(\[][^\)\]]*(?:촬영|제공|재판매|DB|금지|저작권|사진|자료|그래픽|캡처|무단|전재|배포|송고)[^\)\]]*[\)\]]/gi, '');
    // 4. 단독 기자명 = 제거
    t = t.replace(/^[가-힣]{2,4}\s*(?:기자|특파원|논설위원|연구위원|인턴기자)\s*=\s*/, '');
    t = t.replace(/^[=\-~:\s]+/, '');
    return t.trim();
}

function createHeadlineCard(item) {
    const hasImg = item.image && item.image.trim() !== '';
    const targetUrl = getArticleUrl(item.link);
    const clusterBadge = item.cluster_count && item.cluster_count > 1
        ? `<span style="background:#eff6ff; color:#1d4ed8; font-size:11px; font-weight:700; padding:2px 7px; border-radius:10px; border:1px solid #bfdbfe; margin-left:4px;">🔥 ${item.cluster_count}개사 종합</span>`
        : '';
    const cleanedTitle = cleanTitle(item.title);
    const cleanedSum = cleanSummary(item.summary);
    const displaySource = formatNewsSource(item.source, item.category);

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
                ${esc(displaySource)}
                ${clusterBadge}
            </div>
            <div class="headline-title">${esc(cleanedTitle)}</div>
            ${cleanedSum ? `<div class="headline-summary">${esc(cleanedSum)}</div>` : ''}
            <div class="headline-date">${esc(item.date)}</div>
        </div>
    </a>`;
}

function createNewsCard(item) {
    const hasImg = item.image && item.image.trim() !== '';
    const targetUrl = getArticleUrl(item.link);
    const clusterBadge = item.cluster_count && item.cluster_count > 1
        ? `<span style="background:#eff6ff; color:#1d4ed8; font-size:11px; font-weight:700; padding:2px 7px; border-radius:10px; border:1px solid #bfdbfe; margin-left:4px;">🔥 ${item.cluster_count}개사 종합</span>`
        : '';
    const categoryName = (item.category && item.category !== '전체') ? item.category : '실시간 속보';
    const tagBadge = `<span style="background:#f8fafc; color:#475569; font-size:11px; font-weight:600; padding:2px 6px; border-radius:4px; border:1px solid #e2e8f0;">🏷️ ${esc(categoryName)}</span>`;

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
            <div class="news-card-source">${tagBadge} ${clusterBadge}</div>
            <div class="news-card-title">${esc(cleanTitle(item.title))}</div>
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




