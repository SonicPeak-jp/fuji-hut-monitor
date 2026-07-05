#!/usr/bin/env python3
"""GitHub Actions 用: 1回チェックして静的ページ(_site/index.html)を生成する。

前回結果(公開中の status.json)と比較し、新たに空きが出た場合は
GITHUB_OUTPUT の `new` に書き出す(ワークフローがIssue作成→メール通知)。
"""
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

from app import (TAISHIKAN_URL, TOMOEKAN_URL, TOYOKAN_URL, fetch,
                 parse_taishikan, parse_tomoekan, parse_toyokan)

STATUS_URL = "https://sonicpeak-jp.github.io/fuji-hut-monitor/status.json"

JST = timezone(timedelta(hours=9))
WDAYS = ["日", "月", "火", "水", "木", "金", "土"]

SITES = [
    ("トモエ館 本八合目", TOMOEKAN_URL, parse_tomoekan, "utf-8"),
    ("太子館", TAISHIKAN_URL, parse_taishikan, "shift_jis"),
    ("東洋館", TOYOKAN_URL, parse_toyokan, "utf-8"),
]


def calendar_html(dates, url):
    out = ['<div class="cal">']
    out += [f'<div class="wd">{w}</div>' for w in WDAYS]
    first_wd = (datetime(2026, 8, 1).weekday() + 1) % 7  # 日曜=0
    out += ['<div class="cell empty"></div>'] * first_wd
    for d in range(1, 32):
        key = f"2026-08-{d:02d}"
        info = dates.get(key)
        if not info:
            out.append(f'<div class="cell"><span class="d">{d}</span>'
                       f'<div class="mark">?</div></div>')
            continue
        avail = info["available"]
        mark = info.get("mark", "○" if avail else "×")
        if avail and mark == "×":
            mark = "○"
        rooms = info.get("rooms")
        title = ""
        if rooms:
            title = " title=\"{}\"".format(
                " / ".join(f"{r['name']}:{r['mark']}" for r in rooms))
        if avail:
            out.append(f'<a class="cell avail" href="{url}" target="_blank"{title}>'
                       f'<span class="d">{d}</span><div class="mark">{mark}</div></a>')
        else:
            out.append(f'<div class="cell"{title}><span class="d">{d}</span>'
                       f'<div class="mark">{mark}</div></div>')
    out.append("</div>")
    return "".join(out)


def load_previous():
    """前回デプロイ時の空き一覧。取得できなければ None(=全件を新規扱い)。"""
    try:
        with urllib.request.urlopen(STATUS_URL, timeout=15) as r:
            return set(json.load(r)["available"])
    except Exception:
        return None


def main():
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    sections, all_avail = [], []
    for name, url, parser, enc in SITES:
        try:
            dates = parser(fetch(url, enc))
            err = None
        except Exception as e:
            dates, err = {}, str(e)
        avail = sorted(d for d, v in dates.items() if v["available"])
        all_avail += [f"{name} {d[5:].replace('-', '/')}" for d in avail]
        body = ""
        if err:
            body += f'<div class="err">⚠ 取得エラー: {err}</div>'
        if avail:
            days = "、".join(d[5:].replace("-", "/") for d in avail)
            body += f'<div class="got">空きあり: {days}</div>'
        body += calendar_html(dates, url)
        sections.append(
            f'<section class="site"><h2>{name} '
            f'<a href="{url}" target="_blank">予約ページ ↗</a></h2>{body}</section>')

    if all_avail:
        banner = ('<div class="banner found">🎉 空きがあります！ '
                  + "、".join(all_avail) + "</div>")
    else:
        banner = ('<div class="banner none">現在、2026年8月の空きはありません。'
                  "30分ごとに自動更新されます。</div>")

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="900">
<title>🗻 富士山山小屋 空き状況 2026年8月</title>
<style>
  :root {{ --ok: #e7f7ec; --ok-border: #34a853; --ok-text: #1e7e34;
          --ng: #f6f7f8; --ng-text: #b0b8bf; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: "Hiragino Sans", "Yu Gothic", sans-serif;
         background: #f4f6f8; color: #1a2733; }}
  header {{ background: linear-gradient(135deg, #2b6cb0, #4c8fd6); color: #fff;
           padding: 16px 20px; }}
  header h1 {{ font-size: 18px; margin: 0; }}
  header .meta {{ font-size: 12px; opacity: .9; }}
  main {{ max-width: 720px; margin: 0 auto; padding: 16px 12px 50px; }}
  .banner {{ border-radius: 12px; padding: 13px 16px; margin-bottom: 16px;
            font-weight: 600; font-size: 14px; }}
  .banner.none {{ background: #eef1f4; color: #6b7a88; }}
  .banner.found {{ background: var(--ok); color: var(--ok-text);
                  border: 2px solid var(--ok-border); }}
  .site {{ background: #fff; border-radius: 14px; padding: 16px;
          margin-bottom: 18px; box-shadow: 0 1px 4px rgba(0,0,0,.07); }}
  .site h2 {{ margin: 0 0 6px; font-size: 16px; }}
  .site h2 a {{ font-size: 12px; font-weight: normal; margin-left: 8px; }}
  .err {{ color: #c0392b; font-size: 13px; margin: 6px 0; }}
  .got {{ color: var(--ok-text); font-size: 13px; font-weight: 600; margin: 6px 0; }}
  .cal {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px;
         margin-top: 10px; }}
  .wd {{ text-align: center; font-size: 11px; color: #6b7a88; padding: 3px 0; }}
  .cell {{ border-radius: 7px; min-height: 44px; padding: 4px 5px; font-size: 12px;
          background: var(--ng); color: var(--ng-text); text-decoration: none;
          display: block; }}
  .cell .d {{ font-size: 10px; }}
  .cell .mark {{ font-size: 15px; font-weight: 700; text-align: center; }}
  .cell.avail {{ background: var(--ok); color: var(--ok-text);
                border: 2px solid var(--ok-border); }}
  .cell.empty {{ background: transparent; }}
  .footnote {{ font-size: 11px; color: #6b7a88; }}
</style>
</head>
<body>
<header>
  <h1>🗻 富士山山小屋 空き状況 <small>2026年8月</small></h1>
  <span class="meta">最終チェック: {now}（30分ごとに自動更新）</span>
</header>
<main>
{banner}
{"".join(sections)}
<p class="footnote">緑の日をタップすると予約ページが開きます。
○ = 空室あり、△ = 残りわずか、× = 満室。
表示は自動チェック時点の状況で、予約時に埋まっている場合もあります。</p>
</main>
</body>
</html>"""
    os.makedirs("_site", exist_ok=True)
    with open("_site/index.html", "w") as f:
        f.write(html)
    with open("_site/status.json", "w") as f:
        json.dump({"available": all_avail, "checked": now}, f, ensure_ascii=False)

    prev = load_previous()
    new_items = [a for a in all_avail if prev is None or a not in prev]
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write("new=" + "、".join(new_items) + "\n")
    print(f"generated _site/index.html ({now}) avail={all_avail or 'なし'} "
          f"new={new_items or 'なし'}")


if __name__ == "__main__":
    main()
