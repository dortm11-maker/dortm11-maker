/**
 * 쿠팡 파트너스 광고 및 링크 클릭 실시간 추적 엔진
 * - Cross-Origin iframe 클릭 감지 (Iframe Focus / Window Blur / ActiveElement 폴링)
 * - 모바일 터치(Touchstart) + 화면 이탈(visibilitychange / pagehide) 정밀 포착
 * - 중앙 팝업 배너, 본문 정면 배너, 좌/우 날개 배너, 모바일 하단 배너 포지션별 100% 자동 집계
 * - 자동 페이지 이동(auto_redirect) 전환수 기록
 */
(function() {
    'use strict';

    let currentHoverAd = null;
    let hoverClearTimer = null;
    let lastClickTimestamp = 0;
    const CLICK_COOLDOWN_MS = 1200; // 1.2초 내 동일 중복 클릭 방지

    // 광고 위치별 식별 설정
    const AD_CONTAINERS = [
        { selector: '#adWingLeft, .ad-wing-banner.left', type: 'left', label: '좌측 날개 배너' },
        { selector: '#adWingRight, .ad-wing-banner.right', type: 'right', label: '우측 날개 배너' },
        { selector: '#adCenterBanner, .ad-banner-horizontal:not(.mobile-sticky-ad-bar)', type: 'center', label: '정면 본문 배너' },
        { selector: '#mobileStickyAd, .mobile-sticky-ad-bar', type: 'mobile', label: '모바일 하단 고정 배너' },
        { selector: '#popupOverlay .popup-box, #popupOverlay .popup-body, #popupOverlay', type: 'popup', label: '중앙 팝업 배너' }
    ];

    function getPageName() {
        const title = document.title || '';
        const path = window.location.pathname;
        if (path === '/' || path === '') return '메인 뉴스 홈';
        if (path.includes('/article')) {
            const h1 = document.querySelector('h1.article-title') || document.querySelector('h1.article-view-title') || document.querySelector('h1');
            return h1 ? h1.textContent.trim().slice(0, 40) : '기사 상세';
        }
        return title.slice(0, 40) || path;
    }

    function sendAdClick(adType, adLabel) {
        const now = Date.now();
        if (now - lastClickTimestamp < CLICK_COOLDOWN_MS) {
            return;
        }
        lastClickTimestamp = now;

        const page = getPageName();
        const payload = {
            ad_type: adType,
            label: adLabel,
            page: page,
            url: window.location.href,
            timestamp: now
        };

        const jsonStr = JSON.stringify(payload);
        const queryParams = `?ad_type=${encodeURIComponent(adType)}&page=${encodeURIComponent(page)}&_ts=${now}`;
        const targetUrl = `/api/track_ad_click${queryParams}`;

        // 1. sendBeacon 시도 (문자열 전송으로 CORS preflight 차단 없이 안전하게 전송)
        let beaconSent = false;
        if (navigator.sendBeacon) {
            try {
                beaconSent = navigator.sendBeacon(targetUrl, jsonStr);
            } catch(e) {}
        }

        // 2. fetch keepalive fallback
        if (!beaconSent) {
            try {
                fetch(targetUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: jsonStr,
                    keepalive: true
                }).catch(() => {});
            } catch(e) {
                try {
                    const img = new Image();
                    img.src = targetUrl;
                } catch(err) {}
            }
        }

        console.log('[AdTracker] 클릭 집계 전송 성공:', adType, adLabel);
    }

    // 전역 함수로 노출 (auto_redirect.js 등에서 호출 가능)
    window.trackAdClickDirect = sendAdClick;

    function initIframeClickTracking() {
        AD_CONTAINERS.forEach(cfg => {
            const elements = document.querySelectorAll(cfg.selector);
            elements.forEach(el => {
                // 마우스 진입 / 터치 시 현재 활성 광고 타겟 지정
                const onEnter = () => {
                    if (hoverClearTimer) {
                        clearTimeout(hoverClearTimer);
                        hoverClearTimer = null;
                    }
                    currentHoverAd = cfg;
                };

                const onLeave = () => {
                    if (hoverClearTimer) clearTimeout(hoverClearTimer);
                    hoverClearTimer = setTimeout(() => {
                        currentHoverAd = null;
                    }, 3000);
                };

                el.addEventListener('mouseenter', onEnter, { passive: true });
                el.addEventListener('mousemove', onEnter, { passive: true });
                el.addEventListener('touchstart', onEnter, { passive: true });

                el.addEventListener('mouseleave', onLeave, { passive: true });
            });
        });

        // 윈도우 포커스 소실(blur) 감지 (PC 브라우저 iframe 클릭 포착)
        window.addEventListener('blur', function() {
            if (currentHoverAd) {
                const target = currentHoverAd;
                sendAdClick(target.type, target.label);
                setTimeout(() => {
                    currentHoverAd = null;
                }, 500);
            }
        });

        // 모바일 화면 전환 및 탭 이동 감지 (모바일에서 배너 터치로 새창/쿠팡앱 열릴 때 100% 포착)
        window.addEventListener('visibilitychange', function() {
            if (document.hidden && currentHoverAd) {
                sendAdClick(currentHoverAd.type, currentHoverAd.label);
                currentHoverAd = null;
            }
        });

        window.addEventListener('pagehide', function() {
            if (currentHoverAd) {
                sendAdClick(currentHoverAd.type, currentHoverAd.label);
                currentHoverAd = null;
            }
        });
    }

    // iframe 활성 포커스 폴링 (PC & 모바일 공통 브라우저 표준 iframe 포커스 추적)
    let lastActiveIframe = null;
    setInterval(() => {
        const active = document.activeElement;
        if (active && active.tagName === 'IFRAME') {
            if (active !== lastActiveIframe) {
                lastActiveIframe = active;
                for (const cfg of AD_CONTAINERS) {
                    if (active.closest(cfg.selector)) {
                        sendAdClick(cfg.type, cfg.label);
                        return;
                    }
                }
                if (currentHoverAd) {
                    sendAdClick(currentHoverAd.type, currentHoverAd.label);
                }
            }
        } else {
            lastActiveIframe = null;
        }
    }, 200);

    // 광고 컨테이너 및 링크 직접 클릭 감지 (capture 단계)
    function initClickTracking() {
        document.addEventListener('click', function(e) {
            // 닫기 버튼은 집계 제외
            if (e.target.closest('#popupCloseBtn, .popup-corner-close, .mobile-sticky-ad-close, [onclick*="close"]')) {
                return;
            }

            // 1. 특정 광고 컨테이너 내부 클릭 (팝업, 본문, 날개, 모바일 등)
            for (const cfg of AD_CONTAINERS) {
                if (e.target.closest(cfg.selector)) {
                    sendAdClick(cfg.type, cfg.label);
                    return;
                }
            }

            // 2. 일반 쿠팡 직링크 클릭
            const linkEl = e.target.closest('a');
            if (linkEl) {
                const href = (linkEl.getAttribute('href') || '').toLowerCase();
                if (href.includes('coupang.com') || href.includes('link.coupang.com') || linkEl.classList.contains('coupang-link')) {
                    sendAdClick('link', '쿠팡 파트너스 링크 클릭');
                }
            }
        }, true);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            initIframeClickTracking();
            initClickTracking();
        });
    } else {
        initIframeClickTracking();
        initClickTracking();
    }

    setTimeout(initIframeClickTracking, 1200);
    setTimeout(initIframeClickTracking, 3500);

})();
