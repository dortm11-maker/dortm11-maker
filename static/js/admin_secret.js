/* ============================================================
   뉴스NOW - 관리자 시크릿 단축키 및 접근 제어 엔진
   - Ctrl + P (또는 Cmd + P) 누르면 기본 인쇄창 차단 및 관리자 모드로 즉시 전환
   - 모바일 지원: 상단 로고 5회 연속 탭 시 관리자 모드로 비밀 전환
   ============================================================ */
(function() {
    // 1. 키보드 단축키 감지 (Ctrl + P / Cmd + P)
    window.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && (e.key === 'p' || e.key === 'P' || e.keyCode === 80 || e.code === 'KeyP')) {
            e.preventDefault();
            e.stopPropagation();

            showAdminTransitionNotice();
            setTimeout(function() {
                window.location.href = '/admin';
            }, 350);
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
                showAdminTransitionNotice();
                setTimeout(function() {
                    window.location.href = '/admin';
                }, 350);
            }
        });
    }

    // 시각적 전환 안내 토스트
    function showAdminTransitionNotice() {
        let toast = document.getElementById('adminSecretNotice');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'adminSecretNotice';
            toast.style.cssText = 'position:fixed; top:24px; left:50%; transform:translateX(-50%); background:#0f172a; color:#38bdf8; padding:12px 24px; border-radius:30px; font-size:14px; font-weight:700; z-index:999999; box-shadow:0 10px 30px rgba(0,0,0,0.35); border:1px solid #334155; display:flex; align-items:center; gap:8px; font-family:"Noto Sans KR",-apple-system,sans-serif;';
            toast.innerHTML = '<span>🔒</span> <span>관리자 모드로 전환 중입니다...</span>';
            document.body.appendChild(toast);
        }
        toast.style.display = 'flex';
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initLogoSecret);
    } else {
        initLogoSecret();
    }
})();
