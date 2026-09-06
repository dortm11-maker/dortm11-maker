/* ============================================================
   뉴스NOW - 자동 페이지 이동 (Auto Redirect) 엔진
   - 독자가 뉴스를 읽을 때 지정 시간 경과 또는 스크롤 도달 시 외부 링크로 자동 이동
   ============================================================ */
(function() {
    function runAutoRedirect() {
        const cfg = window.SITE_CONFIG?.auto_redirect;
        if (!cfg || !cfg.enabled || !cfg.target_url) return;

        const isArticlePage = window.location.pathname.startsWith('/article');
        const applyTarget = cfg.apply_target || 'article'; // 'article' or 'all'

        // 기사 본문 전용 모드인데 기사 페이지가 아니면 작동하지 않음
        if (applyTarget === 'article' && !isArticlePage) return;

        // 세션당 1회 이동 방지 (뒤로가기로 돌아왔을 때 무한 루프 방지)
        const SESSION_KEY = 'auto_redirect_done';
        if (cfg.prevent_repeat && sessionStorage.getItem(SESSION_KEY)) {
            return;
        }

        let redirected = false;

        function executeRedirect(reason) {
            if (redirected) return;
            redirected = true;

            if (cfg.prevent_repeat) {
                sessionStorage.setItem(SESSION_KEY, 'true');
            }

            console.log(`[뉴스NOW] 자동 이동 실행 (${reason}) -> ${cfg.target_url}`);

            if (cfg.target_window === '_blank') {
                window.open(cfg.target_url, '_blank');
            } else {
                window.location.href = cfg.target_url;
            }
        }

        const mode = cfg.trigger_mode || 'either'; // 'either', 'time', 'scroll', 'both'
        const timeSec = Math.max(1, parseFloat(cfg.time_seconds) || 5);
        const scrollPct = Math.min(99, Math.max(5, parseFloat(cfg.scroll_percent) || 50));

        let timeTriggered = false;
        let scrollTriggered = false;

        // 1. 체류 시간 타이머 설정
        if (mode === 'time' || mode === 'either' || mode === 'both') {
            setTimeout(() => {
                timeTriggered = true;
                if (mode === 'time' || mode === 'either') {
                    executeRedirect(`체류 시간 ${timeSec}초 도달`);
                } else if (mode === 'both' && scrollTriggered) {
                    executeRedirect(`시간(${timeSec}초) + 스크롤(${scrollPct}%) 동시 만족`);
                }
            }, timeSec * 1000);
        }

        // 2. 스크롤 깊이 감지 리스너 설정
        if (mode === 'scroll' || mode === 'either' || mode === 'both') {
            function onScrollCheck() {
                if (redirected) return;
                const scrollTop = window.scrollY || document.documentElement.scrollTop;
                const docHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight;
                if (docHeight <= 0) return;

                const currentPercent = (scrollTop / docHeight) * 100;
                if (currentPercent >= scrollPct) {
                    scrollTriggered = true;
                    if (mode === 'scroll' || mode === 'either') {
                        window.removeEventListener('scroll', onScrollCheck);
                        executeRedirect(`스크롤 깊이 ${Math.round(currentPercent)}% 도달 (설정값: ${scrollPct}%)`);
                    } else if (mode === 'both' && timeTriggered) {
                        window.removeEventListener('scroll', onScrollCheck);
                        executeRedirect(`스크롤(${scrollPct}%) + 시간(${timeSec}초) 동시 만족`);
                    }
                }
            }

            window.addEventListener('scroll', onScrollCheck, { passive: true });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', runAutoRedirect);
    } else {
        runAutoRedirect();
    }
})();
