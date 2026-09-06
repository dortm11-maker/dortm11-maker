import subprocess
import re
import sys
import os
import time

def copy_to_clipboard(text):
    try:
        process = subprocess.Popen('clip', stdin=subprocess.PIPE, shell=True)
        process.communicate(text.encode('utf-16le'))
    except Exception:
        pass

def find_running_flask_port():
    import socket
    for p in [5100, 5101, 5102, 5000, 8000]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex(('127.0.0.1', p)) == 0:
                    return p
        except Exception:
            pass
    return 5100

def main():
    print("=" * 66)
    print("  [뉴스NOW - 외부 공유 웹링크 생성 엔진]")
    print("=" * 66)
    
    port = find_running_flask_port()
    print(f"\n[안내] 로컬 뉴스 서버(포트: {port})를 감지했습니다.")
    print("[안내] Cloudflare 보안 터널을 연결하고 있습니다. 잠시만 기다려주세요...\n")

    cmd = ["cloudflared.exe", "tunnel", "--url", f"http://127.0.0.1:{port}"]
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1
        )
    except Exception as e:
        print(f"[오류] cloudflared.exe 실행 실패: {e}")
        input("\n종료하려면 엔터 키를 누르세요...")
        return

    found_url = None
    url_pattern = re.compile(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com')

    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if not line:
            continue

        if not found_url:
            match = url_pattern.search(line)
            if match:
                found_url = match.group(0)
                copy_to_clipboard(found_url)
                print("\n" + "=" * 66)
                print("  🎉 [외부 공유용 뉴스NOW 웹링크 발급 완료!]")
                print("=" * 66)
                print(f"\n  👉 공유 주소:  \033[92m{found_url}\033[0m")
                print("\n  ★ 이 주소가 클립보드에 [자동 복사] 되었습니다!")
                print("  ★ 상대방(지인/고객) 카톡이나 문자에 [Ctrl + V (붙여넣기)] 하세요!")
                print("  ★ 공유받은 사람은 이 링크로 바로 접속하여 뉴스를 볼 수 있습니다.")
                print("=" * 66)
                print("  ※ 이 검은 창을 닫으면 외부 공유가 즉시 안전하게 종료됩니다.")
                print("=" * 66 + "\n")
                print("[실시간 연결 대기 중...]")

    process.wait()

if __name__ == '__main__':
    main()
