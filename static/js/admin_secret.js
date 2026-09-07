/* ============================================================
   뉴스NOW - 시크릿 단축키 및 비공개 접근 제어 엔진
   - Ctrl + F12 (또는 Cmd + F12): 관리자 모드(/admin)로 즉시 전환
   - Ctrl + F11 (또는 Cmd + F11): 뉴스 상세 페이지에서 언론사 원문으로 즉시 이동 (비밀 루트)
   - 모바일 지원: 상단 로고 5회 연속 탭 시 관리자 모드로 비밀 전환
   ============================================================ */
(function() {
    // 1. 키보드 단축키 감지
    window.addEventListener('keydown', function(e) {
        // [비밀 루트 1] Ctrl + F12 (Cmd + F12): 관리자 페이지 전환
        const isF12 = e.key === 'F12' || e.code === 'F12' || e.keyCode === 123;
        if ((e.ctrlKey || e.metaKey) && isF12) {
            e.preventDefault();
            e.stopPropagation();

            showNoticeToast('🔒 관리자 모드로 전환 중입니다...', '#38bdf8');
            setTimeout(function() {
                window.location.href = '/admin';
            }, 300);
            return false;
        }

        // [비밀 루트 2] Ctrl + F11 (Cmd + F11): 해당 뉴스 언론사 원문으로 바로가기
        const isF11 = e.key === 'F11' || e.code === 'F11' || e.keyCode === 122;
        if ((e.ctrlKey || e.metaKey) && isF11) {
            e.preventDefault();
            e.stopPropagation();

            // 기사 원문 URL 획득 (전역 변수 또는 URL 쿼리스트링)
            const urlParams = new URLSearchParams(window.location.search);
            const originalUrl = window.__ORIGINAL_ARTICLE_URL__ || urlParams.get('url');

            if (originalUrl && (originalUrl.startsWith('http://') || originalUrl.startsWith('https://'))) {
                showNoticeToast('🚀 언론사 원문 페이지로 이동합니다...', '#10b981');
                setTimeout(function() {
                    const win = window.open(originalUrl, '_blank', 'noopener,noreferrer');
                    if (!win) {
                        // 팝업이 차단된 경우 현재 탭에서 이동
                        window.location.href = originalUrl;
                    }
                }, 300);
            } else {
                showNoticeToast('ℹ️ 뉴스 상세 페이지에서만 원문 이동이 가능합니다.', '#f59e0b');
            }
            return false;
        }
    }, true);

    // 2. 모바일/터치 지원: 상단 로고 5회 연속 탭 시 관리자 전환
    let logoTapCount = 0;
    let logoTapTimer = null;

    function initLogoSecret() {
        const logoEl = document.querySelector('.logo') || document.querySelector('.logo-link') || document.querySelector('.header-logo') || document.querySelector('.nav-brand');
        if (!logoEl) return;

        logoEl.addEventListener('click', function(e) {
            logoTapCount++;
            clearTimeout(logoTapTimer);
            logoTapTimer = setTimeout(function() {
                logoTapCount = 0;
            }, 2500);

            if (logoTapCount >= 5) {
                e.preventDefault();
                logoTapCount = 0;
                showNoticeToast('🔒 관리자 모드로 전환 중입니다...', '#38bdf8');
                setTimeout(function() {
                    window.location.href = '/admin';
                }, 350);
            }
        });
    }

    // 시각적 전환 안내 토스트
    function showNoticeToast(text, accentColor) {
        let toast = document.getElementById('secretNoticeToast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'secretNoticeToast';
            toast.style.cssText = 'position:fixed; top:24px; left:50%; transform:translateX(-50%); background:#0f172a; color:#f8fafc; padding:12px 24px; border-radius:30px; font-size:14px; font-weight:700; z-index:999999; box-shadow:0 10px 30px rgba(0,0,0,0.45); border:1px solid #334155; display:flex; align-items:center; gap:8px; font-family:"Noto Sans KR",-apple-system,sans-serif; transition:opacity 0.2s ease; pointer-events:none;';
            document.body.appendChild(toast);
        }
        toast.style.borderColor = accentColor || '#38bdf8';
        toast.innerHTML = `<span>${text}</span>`;
        toast.style.display = 'flex';
        toast.style.opacity = '1';

        setTimeout(function() {
            toast.style.opacity = '0';
            setTimeout(function() {
                toast.style.display = 'none';
            }, 250);
        }, 2200);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initLogoSecret);
    } else {
        initLogoSecret();
    }
})();
