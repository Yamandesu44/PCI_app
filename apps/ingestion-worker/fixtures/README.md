# JV-Link サンプルフィクスチャ

JV-Link（Windows専用 COM）を使わずに domain / application / API の開発を進めるための
サンプルレコードを格納するディレクトリ（ADR-0002）。

## 利用方針

- `*.txt` などのファイルに JV-Link 固定長レコードのサンプルを置く
- 実際の JV-Data から手で切り出したものか、同形式で手作成したものを使用
- **生データ・認証情報は一切コミットしない**（法務: C2、セキュリティ: CLAUDE.md）

## ファイル命名規則

```
{レコード種別}_{説明}.txt
例:
  RA_sample_race.txt    # RA レコード（レース詳細）
  SE_sample_entry.txt   # SE レコード（馬毎レース情報）
  UM_sample_horse.txt   # UM レコード（競走馬マスタ）
```

## 追加手順

1. Windows 環境の JV-Link で取得したレコードから1〜数行をコピー
2. 馬名・騎手名などの固有名詞を適宜マスキング（必要な場合）
3. このディレクトリに配置
4. `apps/api/tests/` の integration テストで参照

## 現状

まだフィクスチャは追加されていない。S3（ingestion-worker 実装 Sprint）で整備予定。
