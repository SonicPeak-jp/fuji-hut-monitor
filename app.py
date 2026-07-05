#!/usr/bin/env python3
"""富士山山小屋 空き状況モニター

トモエ館(本八合目)と東洋館の2026年8月の空き状況を定期チェックし、
空きが出たら macOS 通知でお知らせする。標準ライブラリのみで動作。

起動:  python3 app.py
UI:    http://localhost:8787
"""
import json
import os
import re
import subprocess
import threading
import time
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "state.json")
CHECK_INTERVAL_MIN = int(os.environ.get("FUJI_CHECK_INTERVAL_MIN", "30"))
PORT = int(os.environ.get("FUJI_PORT") or os.environ.get("PORT") or "8787")
TARGET_MONTH = "2026-08"

TOMOEKAN_URL = "https://tomoekan.com/8tomoekan-calender/?ct=1785542400"
TAISHIKAN_URL = "https://www.tenawan.ne.jp/lodgment/rec/007/617/pcr.asp"
TOYOKAN_URL = (
    "https://www.489pro.com/asp/489/date.asp?id=19000037&group=&plan=17&room=6"
    "&year=2026&month=8&user_num=1&lan=JPN&ty=lim&mo=0&meal=0&m_menu=1&m_date=1"
    "&u_n=1&lmp=17&dt=4&s_y=2026&s_m=7&s_d=6&s_nd=&xyz=&s_bmin=&s_bmax=&s_sm="
    "&plan_type=-1&men=&women=&nights=&dayon=&first=&early=&long=&payment=0"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

state_lock = threading.Lock()
state = {
    "lastCheck": None,
    "intervalMin": CHECK_INTERVAL_MIN,
    "sites": {
        "tomoekan": {"name": "トモエ館 本八合目", "url": TOMOEKAN_URL,
                     "dates": {}, "error": None},
        "taishikan": {"name": "太子館", "url": TAISHIKAN_URL,
                      "dates": {}, "error": None},
        "toyokan": {"name": "東洋館", "url": TOYOKAN_URL,
                    "dates": {}, "error": None},
    },
    "events": [],  # 空き検知・消滅の履歴
}


def fetch(url, encoding="utf-8"):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode(encoding, errors="replace")


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s).replace("&nbsp;", "").strip()


def parse_tomoekan(html):
    """日付ごとの部屋別空き状況。room-status のクラスが full 以外なら空き。"""
    if 'caption-item">2026-8' not in html:
        raise ValueError("2026年8月のカレンダーが見つかりません(ページ構造変更の可能性)")
    dates = {}
    for m in re.finditer(r'<td class="day-(\d+)[^"]*">(.*?)</td>', html, re.S):
        day, cell = int(m.group(1)), m.group(2)
        rooms = []
        for rm in re.finditer(
            r'room-name[^"]*">([^<]*)</span>\s*<span class="room-status ([^"]*)">([^<]*)</span>',
            cell,
        ):
            name, cls, mark = rm.group(1), rm.group(2), rm.group(3).strip()
            rooms.append({
                "name": name,
                "mark": mark or "?",
                "available": "full" not in cls and mark != "×",
            })
        if not rooms:
            continue
        date = f"{TARGET_MONTH}-{day:02d}"
        dates[date] = {
            "available": any(r["available"] for r in rooms),
            "rooms": rooms,
        }
    if not dates:
        raise ValueError("日付セルを1件も解析できませんでした(ページ構造変更の可能性)")
    return dates


def parse_toyokan(html):
    """カレンダーセルのマーク。× = 満室, - = 設定なし, ○/数字 = 空きあり。"""
    dates = {}
    for chunk in html.split("<td")[1:]:
        chunk = chunk.split("</td>")[0]
        dm = re.search(r">\s*(\d{1,2})/(\d{1,2})\s*<br", chunk)
        mm = re.search(r'class="mark">(.*?)</span>', chunk, re.S)
        if not dm or not mm:
            continue
        month, day = int(dm.group(1)), int(dm.group(2))
        if f"2026-{month:02d}" != TARGET_MONTH:
            continue
        mark = strip_tags(mm.group(1)) or "?"
        dates[f"{TARGET_MONTH}-{day:02d}"] = {
            "available": mark not in ("×", "-", "?"),
            "mark": mark,
        }
    if not dates:
        raise ValueError("日付セルを1件も解析できませんでした(ページ構造変更の可能性)")
    return dates


TAISHIKAN_ROOMS = ["相部屋", "2人用小部屋", "3人用小部屋", "4人用小部屋"]
TAISHIKAN_OK_MARKS = ("○", "◯", "〇", "△")


def parse_taishikan(html):
    """8月テーブルの日別×部屋タイプ別マーク。○/△ = 空きあり(△は残りわずか)。"""
    start, end = html.find("8月"), html.find("9月")
    if start < 0 or end < 0:
        raise ValueError("8月のカレンダーが見つかりません(ページ構造変更の可能性)")
    dates = {}
    for m in re.finditer(
        r"<b>(\d{1,2})</b>.*?<div class=\"roomtbl\">\s*<table>(.*?)</table>",
        html[start:end], re.S,
    ):
        day, tbl = int(m.group(1)), m.group(2)
        marks = [strip_tags(c) for c in
                 re.findall(r'<td class="tdc\d">(.*?)</td>', tbl, re.S)]
        rooms = [{"name": name, "mark": mark or "?",
                  "available": mark in TAISHIKAN_OK_MARKS or mark.isdigit()}
                 for name, mark in zip(TAISHIKAN_ROOMS, marks)]
        if not rooms:
            continue
        ok_marks = {r["mark"] for r in rooms if r["available"]}
        dates[f"{TARGET_MONTH}-{day:02d}"] = {
            "available": bool(ok_marks),
            "mark": "○" if "○" in ok_marks else ("△" if ok_marks else "×"),
            "rooms": rooms,
        }
    if not dates:
        raise ValueError("日付セルを1件も解析できませんでした(ページ構造変更の可能性)")
    return dates


def notify_mac(title, message):
    try:
        subprocess.run(
            ["osascript", "-e",
             'display notification "{}" with title "{}" sound name "Glass"'.format(
                 message.replace('"', "'"), title.replace('"', "'"))],
            timeout=10,
        )
    except Exception as e:
        print(f"[warn] 通知に失敗: {e}")


def run_check():
    """両サイトをチェックし、新たに空きが出た日付があれば通知する。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parsers = {"tomoekan": (TOMOEKAN_URL, parse_tomoekan, "utf-8"),
               "taishikan": (TAISHIKAN_URL, parse_taishikan, "shift_jis"),
               "toyokan": (TOYOKAN_URL, parse_toyokan, "utf-8")}
    results = {}
    for key, (url, parser, enc) in parsers.items():
        try:
            results[key] = {"dates": parser(fetch(url, enc)), "error": None}
        except Exception as e:
            results[key] = {"dates": None, "error": str(e)}
            print(f"[error] {key}: {e}")

    newly_available = []
    with state_lock:
        state["lastCheck"] = now
        for key, res in results.items():
            site = state["sites"][key]
            if res["error"]:
                site["error"] = res["error"]
                continue  # 取得失敗時は前回データを保持
            old_avail = {d for d, v in site["dates"].items() if v["available"]}
            new_avail = {d for d, v in res["dates"].items() if v["available"]}
            for d in sorted(new_avail - old_avail):
                # 初回チェック(dates空)でも空きがあれば通知対象にする
                newly_available.append((site["name"], d))
                state["events"].insert(0, {
                    "time": now, "site": site["name"], "date": d, "type": "open"})
            for d in sorted(old_avail - new_avail):
                state["events"].insert(0, {
                    "time": now, "site": site["name"], "date": d, "type": "close"})
            site["dates"] = res["dates"]
            site["error"] = None
        state["events"] = state["events"][:100]
        save_state()

    if newly_available:
        lines = [f"{name} {d[5:].replace('-', '/')}" for name, d in newly_available]
        notify_mac("🗻 富士山山小屋に空きが出ました！",
                   "、".join(lines) + " — 今すぐ予約サイトへ")
        print(f"[notify] {lines}")
    summary = {k: (v["error"] or f"{sum(1 for x in v['dates'].values() if x['available'])}日空きあり")
               for k, v in results.items() if v}
    print(f"[{now}] チェック完了: {summary}")


def save_state():
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def load_state():
    try:
        with open(STATE_FILE) as f:
            saved = json.load(f)
        for key in state["sites"]:
            if key in saved.get("sites", {}):
                state["sites"][key]["dates"] = saved["sites"][key].get("dates", {})
        state["events"] = saved.get("events", [])
        state["lastCheck"] = saved.get("lastCheck")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[warn] state.json 読み込み失敗: {e}")


def checker_loop():
    while True:
        try:
            run_check()
        except Exception as e:
            print(f"[error] チェックループ: {e}")
        time.sleep(CHECK_INTERVAL_MIN * 60)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        # file:// やプレビューパネルから直接開いた index.html からの fetch を許可
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            with open(os.path.join(BASE_DIR, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif self.path == "/api/status":
            with state_lock:
                body = json.dumps(state, ensure_ascii=False)
            self._send(200, body)
        else:
            self._send(404, '{"error":"not found"}')

    def do_POST(self):
        if self.path == "/api/refresh":
            threading.Thread(target=run_check, daemon=True).start()
            self._send(200, '{"ok":true}')
        elif self.path == "/api/test-notify":
            notify_mac("🗻 通知テスト", "空きが出るとこの通知が届きます")
            self._send(200, '{"ok":true}')
        else:
            self._send(404, '{"error":"not found"}')

    def log_message(self, fmt, *args):
        pass  # アクセスログは抑制


def main():
    load_state()
    threading.Thread(target=checker_loop, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"富士山山小屋モニター起動: http://localhost:{PORT} "
          f"(チェック間隔 {CHECK_INTERVAL_MIN}分)")
    server.serve_forever()


if __name__ == "__main__":
    main()
