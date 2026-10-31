"""
로컬 개발용 통합 서버 (Static Files + /api/generate)
Vercel CLI 없이도 순수 Python만으로 로컬에서 전체 서비스를 완벽하게 테스트할 수 있습니다.
실행 방법: python dev_server.py
"""

import os
import sys
import socket

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from api.generate import handler as ApiHandler

PREFERRED_PORTS = [8080, 8000, 5000, 3001, 8888]

class CombinedDevHandler(SimpleHTTPRequestHandler):
    _send_json = ApiHandler._send_json

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)

    def do_OPTIONS(self):
        if self.path.startswith("/api/"):
            ApiHandler.do_OPTIONS(self)
        else:
            super().do_OPTIONS()

    def do_POST(self):
        if self.path.startswith("/api/generate"):
            ApiHandler.do_POST(self)
        else:
            self.send_error(404, "Not Found")

    def do_GET(self):
        if self.path.split("?", 1)[0] in {"/anime", "/public/anime", "/boardgames", "/public/boardgames"}:
            self.path = self.path.split("?", 1)[0] + "/index.html"
        if self.path.startswith("/api/"):
            ApiHandler.do_GET(self)
        else:
            super().do_GET()


def find_available_port(ports):
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    # 임의의 가용 포트
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def run():
    # .env 파일 로드
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip()
            print("[\u2713] .env 환경 변수가 로드되었습니다.")
        except Exception as e:
            print(f"[!] .env 로드 중 오류: {e}")

    port = find_available_port(PREFERRED_PORTS)
    server_address = ("", port)
    httpd = ThreadingHTTPServer(server_address, CombinedDevHandler)
    print("=" * 60)
    print(f"🚀 오늘의 덕질 웹툰 추천 사이트 개발 서버 실행 완료")
    print(f"👉 브라우저 접속: http://localhost:{port}")
    print(f"👉 웹툰 카탈로그와 정적 화면을 제공합니다.")
    print(f"👉 종료하려면 Ctrl + C를 누르세요.")
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")
        httpd.server_close()


if __name__ == "__main__":
    run()
