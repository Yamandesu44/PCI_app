# 少人数ロケテスト運用手順

友人など招待した少人数に使ってもらい、展開予想の理解しやすさと継続利用意向を確認する。
精度を保証する公開版ではなく、改善材料を集める期間限定テストとして扱う。

## 1. 開始条件

次をすべて満たすまで外部公開しない。

- APIの`/ready`が`status=ready`かつ`database=ok`
- トップ画面で取り込み失敗、成績未取込、馬場情報欠損、重複レースの重大警告がない
- 今週末の全レースで、レース名、コース、距離、頭数、出走馬が実データと一致する
- Webのテスト、型チェック、本番ビルドが成功する
- APIとingestion-workerのテスト、Ruff、mypyが成功する
- WebとAPIの両方を招待者だけに制限できる
- `.env`、DB接続情報、JV-Link利用キー、Webhook URLを公開物へ含めない
- 画面に「予想精度は検証データを蓄積中」と表示される

予想照合が30件未満でも、UIの感想を得る限定テストは可能。ただし精度評価を目的にせず、
参加者へ「検証中であり、購入判断を保証しない」と事前に伝える。

## 2. 公開範囲

- 招待者は最初は3〜5人、期間は開催2週分を目安にする
- 一般公開URLや検索エンジンへの掲載は行わない
- 現在のAPIには一般ユーザー認証がないため、APIを無制限にインターネット公開しない
- 公開方式は、Web/APIを同じアクセス制限下に置ける構成を選ぶ
- アクセス制限方式が決まるまでは、同一LANまたは管理されたプライベート接続だけで試す

## 3. 開始前点検

```cmd
cd C:\Users\yuuta\PCI_app
git status --short
git log -1 --oneline

cd apps\api
set PYTHONPATH=src
.\.venv\Scripts\python.exe -m pytest -m "not integration" -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy src --strict --python-version 3.12

cd ..\..\apps\ingestion-worker
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy src --strict --python-version 3.12

cd ..\..\apps\web
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
```

起動後は`http://localhost:8000/ready`、レース一覧、代表3レースの詳細を確認する。
代表レースは芝短距離、ダート中距離、枠順確定後の多頭数レースを各1件選ぶ。

## 4. 参加者に確認すること

各開催日の利用後、次の5項目を1〜5段階と自由記述で集める。

1. 3秒以内に想定展開を理解できたか
2. 10秒以内に有力馬と注意馬を理解できたか
3. 統合順位と展開恩恵馬の違いを理解できたか
4. 情報量は少ない、適切、多いのどれか
5. 次の開催でも使いたいか

誤データは、開催日、競馬場、R番号、表示内容、正しい内容、画面画像を記録する。
予想への賛否とデータ不具合を同じ分類にせず、別々に集計する。

## 5. 停止条件

次のいずれかが発生したら新規招待を止め、必要なら公開を停止する。

- レース名、頭数、出走馬、確定結果が実際と異なる
- 前日以前の成績未取込や重複レースが増加する
- API 500が同一操作で再現する
- 認証情報や内部実数値が画面・ログ・配布物へ露出する
- 予想検証が再現不能、または未来情報の混入が疑われる

## 6. 初回終了判定

開催2週後に、回答者数、主要5項目の中央値、誤データ件数、API 500件数、
事前予想照合件数を`docs/HANDOFF.md`へ記録する。

継続条件は、重大な誤データ0件、API 500の再現0件、想定展開と有力馬の理解度中央値4以上。
未達の場合は公開人数を増やさず、原因を`tasks/current.md`へ具体的な修正タスクとして登録する。
