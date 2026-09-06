/**
 * 쿠팡 파트너스 광고 및 링크 클릭 실시간 추적 엔진
 * - Cross-Origin iframe 클릭 감지 (Iframe Focus / Window Blur 패턴)
 * - 모바일 터치(Touchstart) + 포커스 이동 정밀 포착
 * - 쿠팡 파트너스 직링크(a[href*="coupang.com"]) 클릭 감지
 * - 자동 페이지 이동(auto_redirect) 전환수 기록
 */
(function() {
    'use strict';

    let currentHoverAd = null;
    let hoverClearTimer = null;
    let lastClickTimestamp = 0;
    const CLICK_COOLDOWN_MS = 1500; // 1.5초 내 동일 중복 클릭 방지

    // 광고 위치별 식별 설정
    const AD_CONTAINERS = [
        { selector: '#adWingLeft, .ad-wing-banner.left', type: 'left', label: '좌측 날개 배너' },
        { selector: '#adWingRight, .ad-wing-banner.right', type: 'right', label: '우측 날개 배너' },
        { selector: '#adCenterBanner, .ad-banner-horizontal:not(.mobile-sticky-ad-bar)', type: 'center', label: '본문 가로 배너' },
        { selector: '#mobileStickyAd, .mobile-sticky-ad-bar', type: 'mobile', label: '모바일 하단 고정 배너' },
        { selector: '#popupOverlay .popup-box, .popup-body', type: 'popup', label: '중앙 팝업 배너' }
    ];

    function getPageName() {
        const title = document.title || '';
        const path = window.location.pathname;
        if (path === '/' || path === '') return '메인 뉴스 홈';
        if (path.includes('/article')) {
            const h1 = document.querySelector('h1.article-title') || document.querySelector('h1');
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

        const payload = {
            ad_type: adType,
            label: adLabel,
            page: getPageName(),
            url: window.location.href,
            timestamp: now
        };

        const jsonStr = JSON.stringify(payload);

        // 1. sendBeacon 시도 (페이지 이동 시에도 가장 안전하게 전송됨)
        if (navigator.sendBeacon) {
            const blob = new Blob([jsonStr], { type: 'application/json' });
            navigator.sendBeacon('/api/track_ad_click', blob);
        } else {
            // 2. fetch keepalive fallback
            fetch('/api/track_ad_click', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: jsonStr,
                keepalive: true
            }).catch(() => {});
        }

        console.log('[AdTracker] 쿠팡 광고 클릭 전송 성공:', adType, adLabel);
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
                    hoverClearTimer = setTimeout(() => {
                        currentHoverAd = null;
                    }, 250);
                };

                el.addEventListener('mouseenter', onEnter, { passive: true });
                el.addEventListener('mousemove', onEnter, { passive: true });
                el.addEventListener('touchstart', onEnter, { passive: true });

                el.addEventListener('mouseleave', onLeave, { passive: true });
            });
        });

        // 윈도우 포커스 소실(blur) 감지:
        // 마우스가 광고 배너(iframe) 위에 있는 상태에서 blur가 발생하면 = iframe 배너 클릭!
        window.addEventListener('blur', function() {
            if (currentHoverAd) {
                const target = currentHoverAd;
                sendAdClick(target.type, target.label);
                // 클릭 후 타겟 초기화
                setTimeout(() => {
                    currentHoverAd = null;
                }, 400);
            }
        });
    }

    // 텍스트/이미지 직링크 클릭 감지
    function initLinkClickTracking() {
        document.addEventListener('click', function(e) {
            const linkEl = e.target.closest('a');
            if (!linkEl) return;

            const href = (linkEl.getAttribute('href') || '').toLowerCase();
            if (href.includes('coupang.com') || href.includes('link.coupang.com') || linkEl.classList.contains('coupang-link')) {
                sendAdClick('link', '쿠팡 파트너스 링크 클릭');
            }
        }, { passive: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            initIframeClickTracking();
            initLinkClickTracking();
        });
    } else {
        initIframeClickTracking();
        initLinkClickTracking();
    }

    // 동적으로 생성되는 iframe이나 팝업을 위해 1초, 3초 뒤 한 번 더 컨테이너 바인딩 갱신
    setTimeout(initIframeClickTracking, 1200);
    setTimeout(initIframeClickTracking, 3500);

})();
