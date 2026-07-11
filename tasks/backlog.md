# tasks/backlog.md — 未着手タスク・改善候補・技術的負債

> 現時点で確認できる未着手事項を整理する。**確定タスク**（やると決まっている）と
> **改善案/検討**（やるかどうか未確定）を区別する。着手したら `tasks/current.md` へ移す。

最終更新: 2026-07-11

---

## A. 確定タスク（方針は決定済み・未着手）

- [x] ~~P1 想定RPCI の精度検証~~ → **検証完了**（2026-07-11、`docs/SPEC.md §8`・ADR-0005 §5.4）。
- [x] ~~P1 未達なら要因追加の判断~~ → **方針決定済み**（2026-07-11、`docs/DECISIONS.md`）。
  当面は追加投資せず現行モデルを継続、`forecast_accuracy` 蓄積で継続監視。見直し条件あり。
- [x] ~~P1 `forecast_accuracy` のフロント表示~~ → 完了（コミット `e65f919`）。
- [x] ~~P2 backtest_forecast.py の PAI希釈対策（track別内訳表示）~~ → 完了（2026-07-11、
  `group_races_by_track` + `_print_track_breakdown`）。
- [ ] **P2 バックテスト結果の可視化/保存**（現状 `backtest_forecast.py` は print のみ・永続化なし）。
  的中率の推移を見たいフェーズで DB 化 or レポート出力を検討。
- [ ] **P2 Windows ワーカー運用の監視強化**（design/07）。`ingest_log` は導入済み。失敗の可視化・
  再実行導線・Webhook 通知の定着（`NOTIFY_WEBHOOK_URL`）。

## B. 改善候補（やるか未確定・要判断）

- [ ] 🧪 暫定定数の検証と正式化: `_NEIGHBOR_BLEED_RATIO`(affinity)・上がり3F 妥当範囲(se_parser)・
  `RuleWeights`(rule-v4)・`PaiWeights`(pai-v1)。実データ検証後に確定（独断で確定しない）。
- [ ] 脚質判定ルールの最適化（design/07 C9・データ蓄積後）。
- [ ] 展開コメントの LLM（Gemini）本採用可否と品質基準（ADR-0008）。数値はドメイン確定・表現のみ LLM。
- [ ] PAI 正式定義の確定（design/07 C10・実運用検証後）。
- [ ] ダート「ハイ」(17.2%)/芝「平均(49–51)」(14.3%)再現率の構造的課題への対応
  （2026-07-11実測、ADR-0005 §5.4・§5.3）。閾値調整では解決不可と結論済み（rule-v5試行）。
  特徴量追加・学習データ拡張が候補。**現時点では未着手が方針**（`docs/DECISIONS.md` 2026-07-11）。
  見直し条件（`forecast_accuracy`蓄積増加・ダートの外れの偏り）に該当したら着手を検討。

## C. 技術的負債・環境

- [ ] `mypy src/ --strict` を全体で通すための SQLAlchemy/Pydantic/FastAPI スタブ導入 or 設定
  （infrastructure/presentation で多数エラー・現状は domain/application のみ strict 確認）。
- [ ] 旧 `docs/handoff-claude-code-2026-06-25.md` の記載ファイル名が現構成と不一致。
  歴史資料として残置するか、`docs/ARCHITECTURE.md` へ吸収して削除するか要判断。
- [ ] 統合テスト（testcontainers-postgres）の日常実行環境（CI/ローカル Docker）整備。
- [ ] JV-Data バイトオフセットの JV-Link 新バージョン追従手順の明文化（`jv_spec.py`）。

## D. 将来スコープ（MVP 外・design/07 参照）

- [ ] 当日リアルタイム速報更新（C6/C7）
- [ ] 地方競馬対応（C5・中央で価値実証後）
- [ ] 認証・課金・マルチテナント（C11・SaaS 化フェーズ）
- [ ] バックフィル 10年への拡張（C8・運用安定後）
- [ ] 正式公開時の JRA-VAN 規約適合性確認（C2・法務）
