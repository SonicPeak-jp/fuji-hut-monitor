# 🗻 富士山山小屋 空き状況モニター

**公開ページ（誰でも閲覧可）**: https://sonicpeak-jp.github.io/fuji-hut-monitor/

GitHub Actions が30分ごとに空き状況をチェックして上記ページを自動更新します
（`.github/workflows/check.yml` + `cloud_check.py`）。
以下はローカル版（macOS通知つき）の説明です。

トモエ館（本八合目）と東洋館の **2026年8月** の空き状況を30分ごとに自動チェックし、
空きが出た瞬間に **macOS通知（サウンド付き）** でお知らせします。

- 追加インストール不要（macOS標準のPython 3だけで動作）
- UI: http://localhost:8787

## 使い方

```bash
python3 app.py
```

ブラウザで http://localhost:8787 を開くと、両山小屋の8月カレンダーが見られます。

- **今すぐチェック** ボタン: その場で再チェック
- **通知テスト** ボタン: macOS通知の動作確認
- 空きが出た日は緑色で表示され、クリックすると予約ページが開きます
- トモエ館はセルにマウスを乗せると部屋タイプ別（1〜6名部屋）の空き状況を表示

## ログイン時に自動起動する（推奨）

PCにログインしている間ずっと監視させるには:

```bash
cp com.fuji.hut-monitor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.fuji.hut-monitor.plist
```

停止するには:

```bash
launchctl unload ~/Library/LaunchAgents/com.fuji.hut-monitor.plist
```

## 設定（環境変数）

| 変数 | デフォルト | 説明 |
|---|---|---|
| `FUJI_CHECK_INTERVAL_MIN` | 30 | チェック間隔（分） |
| `FUJI_PORT` | 8787 | UIのポート番号 |

## 仕組み

- トモエ館: 公式カレンダーページのHTMLから部屋タイプごとの空き記号（×以外＝空き）を解析
- 東洋館: 予約システム（489pro）のカレンダーから日別マークを解析（× = 満室、○/数字 = 空き）
- 前回チェックとの差分で「新たに空きが出た日」だけ通知（同じ空きで何度も通知しない）
- 状態は `state.json` に保存され、再起動しても検知履歴が残ります

## 注意

- 通知はサーバー（app.py）が動いている間のみ届きます。スリープ中はチェックされません
- サイト側のHTML構造が変わると解析に失敗します。その場合はUI上に「取得エラー」と表示されます
- 東洋館のURLはシングルルーム2食付きプランの空き状況です
