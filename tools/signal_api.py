#!/usr/bin/env python3
"""signal_api.py — 대량 신호를 실제 외부 API 처럼 내준다 (확장 과제 E1)

  python3 tools/signal_api.py [--port 8770]   → http://127.0.0.1:8770/signals?page=1

실제 수집 API 에서 늘 겪는 일을 그대로 낸다. 같은 요청에는 늘 같은 일이 일어난다(팀마다 공정하게).
  인증      X-Api-Key: team-<팀이름>  없으면 401
  쪽 나눔   page(1부터) · page_size(최대 200). 응답의 next_page 가 null 이면 끝
  속도 제한 초당 5회를 넘으면 429 + Retry-After(초)
  일시 장애 일부 쪽은 첫 요청에 503 을 낸다. 다시 요청하면 된다
  느린 응답 일부 쪽은 첫 요청이 8초 뒤 504 로 끝난다. 시간 제한을 짧게 두고 다시 요청한다
모든 요청은 dev/results/api-<팀>.jsonl 에 남는다. 채점: python3 tools/ext_check.py api <팀>
"""
from __future__ import annotations
import argparse, csv, hashlib, json, re, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "dev/results"
RATE = 5                                       # 초당 허용 요청 수
SLOW = 8.0


def load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def fault(page: int) -> str | None:
    """쪽마다 정해진 첫 요청 장애. 같은 쪽은 늘 같다"""
    h = int(hashlib.sha256(f"mi-api-{page}".encode()).hexdigest(), 16)
    return "503" if h % 7 == 3 else "slow" if h % 11 == 5 else None


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.calls: dict[str, list[float]] = {}
        self.seen: set[tuple[str, int]] = set()

    def admit(self, team: str, now: float) -> bool:
        with self.lock:
            q = [t for t in self.calls.get(team, []) if now - t < 1.0]
            ok = len(q) < RATE
            if ok:
                q.append(now)
            self.calls[team] = q
            return ok

    def first(self, team: str, page: int) -> bool:
        with self.lock:
            k = (team, page)
            if k in self.seen:
                return False
            self.seen.add(k)
            return True


def make_handler(rows: list[dict], state: State, log_dir: Path):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def reply(self, code: int, body: dict, headers: dict | None = None):
            b = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            try:
                self.wfile.write(b)
                self.wfile.flush()
                return True
            except (BrokenPipeError, ConnectionResetError):
                return False                   # 클라이언트가 시간 제한으로 끊었다

        def record(self, team: str, page, status: int, t0: float, size: int | None = None):
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(log_dir / f"api-{team}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": round(t0, 3), "page": page, "page_size": size, "status": status}) + "\n")

        def do_GET(self):
            t0 = time.time()
            u = urllib.parse.urlparse(self.path)
            if u.path != "/signals":
                return self.reply(404, {"error": "없는 경로입니다. /signals 를 쓰세요"})
            key = self.headers.get("X-Api-Key", "")
            m = re.fullmatch(r"team-([\w가-힣\-]{1,40})", key)
            if not m:
                return self.reply(401, {"error": "X-Api-Key: team-<팀이름> 헤더가 필요합니다"})
            team = m.group(1)
            q = urllib.parse.parse_qs(u.query)
            try:
                page = int(q.get("page", ["1"])[0])
                size = min(int(q.get("page_size", ["100"])[0]), 200)
                if page < 1 or size < 1:
                    raise ValueError
            except ValueError:
                self.record(team, None, 400, t0)
                return self.reply(400, {"error": "page 는 1 이상, page_size 는 1~200 입니다"})
            if not state.admit(team, t0):
                self.record(team, page, 429, t0, size)
                return self.reply(429, {"error": "요청이 너무 많습니다"}, {"Retry-After": "1"})
            pages = (len(rows) + size - 1) // size
            if page > pages:
                self.record(team, page, 404, t0, size)
                return self.reply(404, {"error": f"마지막 쪽은 {pages} 입니다"})
            if state.first(team, page):
                f = fault(page)
                if f == "503":
                    self.record(team, page, 503, t0, size)
                    return self.reply(503, {"error": "일시 장애입니다. 잠시 뒤 다시 요청하세요"})
                if f == "slow":                # 게이트웨이가 오래 기다리다 끊는다. 시간 제한을 짧게 두고 다시 요청한다
                    time.sleep(SLOW)
                    self.record(team, page, 504, t0, size)
                    return self.reply(504, {"error": "응답 시간이 초과됐습니다"})
            items = rows[(page - 1) * size: page * size]
            self.record(team, page, 200, t0, size)
            return self.reply(200, {"page": page, "page_size": size, "total": len(rows), "next_page": page + 1 if page < pages else None, "items": items})
    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--signals", default=str(ROOT / "dev/data/signals.csv"))
    a = ap.parse_args()
    rows = load(Path(a.signals))
    print(f"신호 API: http://127.0.0.1:{a.port}/signals ({len(rows)}건)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(rows, State(), LOG)).serve_forever()


if __name__ == "__main__":
    main()
