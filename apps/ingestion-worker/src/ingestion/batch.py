"""JV-Link 日次バッチランナー（エントリーポイント）。

使い方:
    # 開発環境（fixtures/ を使う）
    python -m ingestion.batch --mode fixture

    # 本番（Windows + JV-Link COM）
    python -m ingestion.batch --mode jvlink --date 20260619

環境変数 (.env):
    API_BASE_URL   : Ingest API の URL（例: http://localhost:8000）
    INGEST_TOKEN   : Bearer トークン（未設定時は認証スキップ）
    JV_LINK_SID    : JV-Link サービス ID（--mode jvlink 時のみ必要）
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import logging
import os
import sys

from dotenv import load_dotenv

from ingestion.client.base import JvLinkClient
from ingestion.client.fixture_client import FixtureJvLinkClient
from ingestion.ingest_api import IngestApiClient
from ingestion.models import (
    HorseRecord,
    JockeyRecord,
    RaceEntriesRecord,
    RaceResultRecord,
    TrainerRecord,
)
from ingestion.parser.master_parsers import parse_ch, parse_ks, parse_um
from ingestion.parser.ra_parser import parse_ra as _parse_ra
from ingestion.parser.se_parser import (
    get_horse_info_from_se,
    parse_race_key_from_se,
    parse_se_entry,
    parse_se_result,
)

_log = logging.getLogger(__name__)
_MASTER_FLUSH_SIZE = 1000


def _notify_failure(step: str, date_from: str, error: str) -> None:
    """NOTIFY_WEBHOOK_URL が設定されていれば Slack 互換 Webhook に失敗通知を送る。"""
    url = os.environ.get("NOTIFY_WEBHOOK_URL", "")
    if not url:
        return
    try:
        import httpx

        msg = (
            f":x: *ingestion-worker 失敗*\n"
            f"• step: `{step}`\n"
            f"• 日付: `{date_from}`\n"
            f"• エラー: ```{error[:500]}```"
        )
        httpx.post(url, json={"text": msg}, timeout=10.0)
        _log.info("失敗通知を送信しました")
    except Exception as exc:
        _log.warning("失敗通知の送信に失敗しました: %s", exc)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _build_client(mode: str, race_option: int = 1) -> JvLinkClient:
    if mode == "fixture":
        return FixtureJvLinkClient()
    if mode == "jvlink":
        from ingestion.client.windows_client import WindowsJvLinkClient

        sid = os.environ.get("JV_LINK_SID", "")
        if not sid:
            raise RuntimeError("JV_LINK_SID 環境変数が未設定です。.env に追記してください。")
        return WindowsJvLinkClient(sid=sid, race_option=race_option)
    if mode == "mykeibadb":
        from ingestion.client.mykeibadb_client import MyKeibaDbClient

        return MyKeibaDbClient()
    raise ValueError(f"未知のモード: {mode!r}。'fixture' または 'jvlink' を指定してください。")


def ingest_mykeibadb_special_entries(
    api: IngestApiClient,
    date_from: str,
    date_to: str,
    *,
    today: datetime.date | None = None,
) -> None:
    """mykeibadb の特別登録テーブルから出走前レースを取り込む。"""
    from ingestion.client.mykeibadb_client import MyKeibaDbClient

    client = MyKeibaDbClient()
    for race_key in sorted(client.excluded_race_keys):
        try:
            api.delete_race(race_key)
        except Exception as exc:
            _log.error("mykeibadb 除外レース削除エラー %s: %s", race_key, exc)

    current = (today or datetime.date.today()).strftime("%Y%m%d")
    effective_from = max(date_from, current)
    if effective_from > date_to:
        _log.info("mykeibadb 特別登録の未来レースなし: %s→%s", date_from, date_to)
        return

    races = client.fetch_special_entries(effective_from, date_to)
    horses = client.fetch_special_horses(effective_from, date_to)

    if not races:
        _log.info("mykeibadb 特別登録データが見つかりません: %s→%s", date_from, date_to)
        return

    if horses:
        api.upsert_horses(horses)

    # 特別登録では騎手未定が多いため、TBD を共通プレースホルダとして登録する。
    api.upsert_jockeys([JockeyRecord(code="TBD", name="未定")])

    trainer_codes = {
        entry.trainer_code
        for race in races
        for entry in race.entries
        if entry.trainer_code and entry.trainer_code != "TBD"
    }
    trainers = [TrainerRecord(code="TBD", name="未定")]
    trainers.extend(TrainerRecord(code=code, name=code) for code in sorted(trainer_codes))
    api.upsert_trainers(trainers)

    for race in races:
        race.field_size = len(race.entries)
        try:
            api.register_entries(race)
        except Exception as exc:
            _log.error("mykeibadb 特別登録送信エラー %s: %s", race.race_key, exc)


# ---------------------------------------------------------------------------
# マスタデータ取り込み
# ---------------------------------------------------------------------------


def ingest_masters(client: JvLinkClient, api: IngestApiClient) -> None:
    """UM / KS / CH レコードから馬・騎手・調教師マスタを取り込む。"""
    horses: list[HorseRecord] = []
    for rec in client.iter_um_records():
        try:
            parsed = parse_um(rec)
            if parsed:
                horses.append(parsed)
                if len(horses) >= _MASTER_FLUSH_SIZE:
                    api.upsert_horses(horses)
                    horses.clear()
        except Exception as exc:
            _log.warning("UM パースエラー: %s | レコード先頭: %.40s", exc, rec)
    if horses:
        api.upsert_horses(horses)

    jockeys: list[JockeyRecord] = []
    for rec in client.iter_ks_records():
        try:
            parsed = parse_ks(rec)
            if parsed:
                jockeys.append(parsed)
                if len(jockeys) >= _MASTER_FLUSH_SIZE:
                    api.upsert_jockeys(jockeys)
                    jockeys.clear()
        except Exception as exc:
            _log.warning("KS パースエラー: %s", exc)
    if jockeys:
        api.upsert_jockeys(jockeys)

    trainers: list[TrainerRecord] = []
    for rec in client.iter_ch_records():
        try:
            parsed = parse_ch(rec)
            if parsed:
                trainers.append(parsed)
                if len(trainers) >= _MASTER_FLUSH_SIZE:
                    api.upsert_trainers(trainers)
                    trainers.clear()
        except Exception as exc:
            _log.warning("CH パースエラー: %s", exc)
    if trainers:
        api.upsert_trainers(trainers)


# ---------------------------------------------------------------------------
# 出走表取り込み
# ---------------------------------------------------------------------------


def ingest_entries(
    client: JvLinkClient,
    api: IngestApiClient,
    date_from: str,
    date_to: str,
) -> None:
    """RA + SE レコードから出走表を取り込む。"""
    # race_key → RaceEntriesRecord のバッファ
    races: dict[str, RaceEntriesRecord] = {}

    for rec in client.iter_ra_records(date_from, date_to):
        try:
            ra = _parse_ra(rec)
            if ra:
                races[ra.race_key] = ra
        except Exception as exc:
            _log.warning("RA パースエラー: %s | %.40s", exc, rec)

    # SE エントリを RA に紐付け
    # SE から馬マスタを補完するため horse_supplement を収集
    horse_supplements: list[HorseRecord] = []
    # UMABAN=0（特別登録前段階・番号未確定）のとき ketto_num → 連番を管理する。
    race_ketto_to_no: dict[str, dict[str, int]] = {}

    for rec in client.iter_se_records(date_from, date_to):
        try:
            race_key = parse_race_key_from_se(rec)
            entry = parse_se_entry(rec)
            if entry is None:
                continue

            # RA がない場合はスキップ
            if race_key not in races:
                _log.debug("SE に対応する RA がありません: %s", race_key)
                continue

            # UMABAN=0 は特別登録段階で馬番未確定。ketto_num で重複排除し連番を付与する。
            # 抽選済み（DATA_KUBUN='2'）の UMABAN 実値を上書きしないよう 0 のときだけ適用。
            if entry.horse_no == 0 and entry.ketto_num:
                ketto_map = race_ketto_to_no.setdefault(race_key, {})
                if entry.ketto_num not in ketto_map:
                    ketto_map[entry.ketto_num] = len(ketto_map) + 1
                entry = dataclasses.replace(entry, horse_no=ketto_map[entry.ketto_num])

            # 同一馬番の重複を後勝ちで排除する。出走前('1'/'2')→確定('7')の順で
            # 両方届く場合（フィクスチャや週跨ぎ取得）、確定レコードは実馬体重を
            # 持つため、後から来た確定で上書きするのが正しい。
            entries = races[race_key].entries
            for i, existing in enumerate(entries):
                if existing.horse_no == entry.horse_no:
                    entries[i] = entry
                    break
            else:
                entries.append(entry)

            # 馬マスタ補完
            ketto, name, sex = get_horse_info_from_se(rec)
            if ketto and name:
                horse_supplements.append(HorseRecord(ketto_num=ketto, name=name, sex=sex))
        except Exception as exc:
            _log.warning("SE(entry) パースエラー: %s | %.40s", exc, rec)

    # 馬マスタ補完（UM レコードが不足している場合の保険）
    if horse_supplements:
        api.upsert_horses(horse_supplements)

    _log.info(
        "出走表集計 %s→%s: RA %d レース / SE エントリ紐付け済み %d レース",
        date_from,
        date_to,
        len(races),
        sum(1 for r in races.values() if r.entries),
    )

    # API へ送信
    for race_key, race in races.items():
        if not race.entries:
            _log.info("出走馬なし、スキップ: %s", race_key)
            continue
        # 出走頭数は出走前 SE エントリ数（取消/除外を除いた実出走馬）で確定する。
        # RA の SyussoTosu の byte 位置が未特定でも正確で、entries と必ず整合する。
        race.field_size = len(race.entries)
        try:
            api.register_entries(race)
        except Exception as exc:
            _log.error("出走表送信エラー %s: %s", race_key, exc)


# ---------------------------------------------------------------------------
# 確定成績取り込み
# ---------------------------------------------------------------------------


def ingest_results(
    client: JvLinkClient,
    api: IngestApiClient,
    date_from: str,
    date_to: str,
    *,
    race_keys: set[str] | None = None,
) -> None:
    """SE レコード（DataKubun=4/7）+ RA レコード（DataKubun=7）から確定成績を取り込む。"""
    # race_key → RaceResultRecord のバッファ
    race_results: dict[str, RaceResultRecord] = {}
    target_by_identity: dict[str, set[str]] = {}
    if race_keys is not None:
        for target_key in race_keys:
            target_by_identity.setdefault(_race_identity(target_key), set()).add(target_key)
    stale_race_keys: set[str] = set()

    # RA 確定レコード（DataKubun=7）から HaronTimeL3（後半3F）を収集する。
    # ingest_entries より後に呼ばれるが、RA は SE と独立したデータ種別のため再取得可能。
    race_s3f_map: dict[str, float] = {}
    race_l3f_map: dict[str, float] = {}
    grade_map: dict[str, str] = {}
    entry_snapshots: dict[str, RaceEntriesRecord] = {}
    for rec in client.iter_ra_records(date_from, date_to):
        try:
            ra = _parse_ra(rec)
            if ra:
                if race_keys is not None:
                    matching = target_by_identity.get(_race_identity(ra.race_key), set())
                    if ra.race_key not in race_keys and not matching:
                        continue
                    stale_race_keys.update(key for key in matching if key != ra.race_key)
                entry_snapshots[ra.race_key] = ra
                if ra.race_s3f is not None:
                    race_s3f_map[ra.race_key] = ra.race_s3f
                if ra.race_l3f is not None:
                    race_l3f_map[ra.race_key] = ra.race_l3f
                if ra.grade is not None:
                    grade_map[ra.race_key] = ra.grade
        except Exception as exc:
            _log.warning("RA(results) パースエラー: %s | %.40s", exc, rec)

    # 取り込みが「exit 0 なのに0件」のとき、SE行が読めていない（mykeibadb未取得）のか、
    # 読めているが確定成績として解析できていない（列マッピング/DATA_KUBUN不整合）のかを
    # ログだけで切り分けられるよう、各段の件数を記録する（2026-07-20 調査で追加）。
    se_rows = 0
    parsed_results = 0
    for rec in client.iter_se_records(date_from, date_to):
        se_rows += 1
        try:
            race_key = parse_race_key_from_se(rec)
            if race_keys is not None:
                matching = target_by_identity.get(_race_identity(race_key), set())
                if race_key not in race_keys and not matching:
                    continue
            entry = parse_se_entry(rec)
            snapshot = entry_snapshots.get(race_key)
            if entry is not None and snapshot is not None and entry.horse_no > 0:
                for index, current in enumerate(snapshot.entries):
                    if current.horse_no == entry.horse_no:
                        snapshot.entries[index] = entry
                        break
                else:
                    snapshot.entries.append(entry)

            result = parse_se_result(rec)
            if result is None:
                continue
            parsed_results += 1

            if race_key not in race_results:
                race_results[race_key] = RaceResultRecord(race_key=race_key)
            race_results[race_key].results.append(result)
        except Exception as exc:
            _log.warning("SE(result) パースエラー: %s | %.40s", exc, rec)

    _log.info(
        "確定成績集計 %s→%s: SE %d 行読込 / 確定成績 %d 行解析 / %d レース記録予定",
        date_from,
        date_to,
        se_rows,
        parsed_results,
        len(race_results),
    )
    if se_rows > 0 and parsed_results == 0:
        _log.warning(
            "SE行は読めているが確定成績が0件です。mykeibadbに確定データ（着順・タイム・"
            "上り3F）が未取得か、列名がパーサ候補と不一致の可能性があります。"
            "`python -m ingestion.diagnose_results --date %s --date-to %s` で原因切り分け可。",
            date_from,
            date_to,
        )

    sent_ok = 0
    sent_fail = 0
    for stale_race_key in sorted(stale_race_keys):
        try:
            api.delete_race(stale_race_key)
        except Exception as exc:
            sent_fail += 1
            _log.error("旧レースキー削除エラー %s: %s", stale_race_key, exc)

    snapshots_to_send = (
        entry_snapshots
        if race_keys is not None
        else {
            key: entry_snapshots[key]
            for key in race_results
            if key in entry_snapshots
        }
    )
    for race_key, snapshot in snapshots_to_send.items():
        if not snapshot.entries:
            sent_fail += 1
            _log.error("確定出馬表を再構成できないため成績送信を中止: %s", race_key)
            continue
        snapshot.entries.sort(key=lambda entry: entry.horse_no)
        snapshot.field_size = len(snapshot.entries)
        try:
            api.register_entries(snapshot)
        except Exception as exc:
            sent_fail += 1
            _log.error("確定出馬表送信エラー %s: %s", race_key, exc)
            continue
        rr = race_results.get(race_key)
        if rr is None or not rr.results:
            continue
        rr.race_s3f = race_s3f_map.get(race_key)
        rr.race_l3f = race_l3f_map.get(race_key)
        rr.grade = grade_map.get(race_key)
        if rr.race_s3f is not None and rr.race_l3f is not None:
            _log.debug("HaronTime 取得 %s: S3=%.1f L3=%.1f", race_key, rr.race_s3f, rr.race_l3f)
        try:
            api.record_results(rr)
            sent_ok += 1
        except Exception as exc:
            sent_fail += 1
            _log.error("成績送信エラー %s: %s", race_key, exc)

    # 解析はできたのに送信で全滅している状態（＝APIレイヤの問題。レース未登録で
    # find_by_key が None を返す等）を exit 0 に埋もれさせない。件数を明示する。
    _log.info(
        "確定成績送信 %s→%s: 成功 %d レース / 失敗 %d レース（解析済み %d レース）",
        date_from,
        date_to,
        sent_ok,
        sent_fail,
        len(race_results),
    )
    if race_results and sent_ok == 0:
        _log.warning(
            "確定成績を解析できたが、API送信が全件失敗しています。"
            "上の『成績送信エラー』の内容（例: レースが見つかりません=出走表未登録、"
            "HTTPエラー=API/DB接続先の相違）を確認してください。"
        )


def _race_identity(race_key: str) -> str:
    """開催回・開催日次を除いた、日付・競馬場・R番号の同一性キーを返す。"""
    return f"{race_key[:10]}{race_key[-2:]}"


def _to_iso_date(yyyymmdd: str) -> str:
    """YYYYMMDD 形式を ISO 8601 (YYYY-MM-DD) へ変換する（ingest_log API 送信用）。"""
    return datetime.datetime.strptime(yyyymmdd, "%Y%m%d").date().isoformat()


def precompute_forecasts(
    api: IngestApiClient,
    date_from: str,
    date_to: str,
    *,
    today: datetime.date | None = None,
) -> dict[str, int]:
    """同期範囲のうち今日以降だけをAPIへ事前生成依頼する。"""
    start = datetime.datetime.strptime(date_from, "%Y%m%d").date()
    end = datetime.datetime.strptime(date_to, "%Y%m%d").date()
    current_date = today or datetime.date.today()
    effective_start = max(start, current_date)
    if effective_start > end:
        _log.info("予想事前生成対象なし: %s→%s", date_from, date_to)
        return {"scanned": 0, "generated": 0, "skipped": 0}
    return api.precompute_forecasts(effective_start.isoformat(), end.isoformat())


def iter_date_chunks(date_from: str, date_to: str, chunk_days: int) -> list[tuple[str, str]]:
    """長期取り込みを、指定日数ごとの範囲に分割する。"""
    if chunk_days <= 0:
        return [(date_from, date_to)]

    start = datetime.datetime.strptime(date_from, "%Y%m%d").date()
    end = datetime.datetime.strptime(date_to, "%Y%m%d").date()
    if start > end:
        raise ValueError("--date は --date-to 以前の日付にしてください。")

    chunks: list[tuple[str, str]] = []
    current = start
    while current <= end:
        chunk_end = min(current + datetime.timedelta(days=chunk_days - 1), end)
        chunks.append((current.strftime("%Y%m%d"), chunk_end.strftime("%Y%m%d")))
        current = chunk_end + datetime.timedelta(days=1)
    return chunks


# ---------------------------------------------------------------------------
# メインエントリーポイント
# ---------------------------------------------------------------------------


def main() -> None:
    load_dotenv()
    _setup_logging()

    parser = argparse.ArgumentParser(
        description="JV-Link 日次データ取り込みバッチ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mode",
        choices=["fixture", "jvlink", "mykeibadb"],
        default="fixture",
        help=(
            "データソース（fixture=開発用JSON / jvlink=本番Windows COM / "
            "mykeibadb=mykeibadb MySQL）"
        ),
    )
    parser.add_argument(
        "--date",
        default=datetime.date.today().strftime("%Y%m%d"),
        help="取得日付 YYYYMMDD（デフォルト: 今日）",
    )
    parser.add_argument(
        "--date-to",
        default=None,
        help="取得終了日付 YYYYMMDD（デフォルト: --date と同じ）",
    )
    parser.add_argument(
        "--step",
        choices=["all", "masters", "entries", "results", "special-entries", "forecasts"],
        default="all",
        help="実行ステップ（デフォルト: all）",
    )
    parser.add_argument(
        "--race-option",
        type=int,
        choices=[1, 2, 3, 4],
        default=1,
        help=(
            "JVOpen RACE の option。通常データ=1。"
            "未来データは ingestion.probe_race_options で取得できる option を確認してください。"
        ),
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=0,
        help=(
            "長期レンジを指定日数ごとに分割して取り込む。"
            "0 の場合は従来どおり一括で処理する。"
        ),
    )
    parser.add_argument(
        "--only-incomplete",
        action="store_true",
        help="APIが検出した成績未取り込みのJRA平地レースだけを再同期する。",
    )
    args = parser.parse_args()

    date_from: str = args.date
    date_to: str = args.date_to or args.date

    api_base_url = os.environ.get("API_BASE_URL", "http://localhost:8000")
    ingest_token = os.environ.get("INGEST_TOKEN", "")

    api = IngestApiClient(base_url=api_base_url, token=ingest_token)
    incomplete_race_keys: set[str] | None = None
    if args.only_incomplete:
        if args.step != "results":
            parser.error("--only-incomplete は --step results と組み合わせてください。")
        incomplete_race_keys = api.incomplete_race_keys()
        _log.info("--- 成績未取り込み限定: %d レース ---", len(incomplete_race_keys))

    _log.info(
        "=== ingestion-worker 開始 mode=%s date=%s→%s race_option=%s ===",
        args.mode,
        date_from,
        date_to,
        args.race_option,
    )

    started_at = datetime.datetime.now(datetime.UTC)

    try:
        if args.step == "forecasts":
            _log.info("--- 今後のレース予想を事前生成 ---")
            precompute_forecasts(api, date_from, date_to)
            _log.info("=== ingestion-worker 完了 ===")
            api.log_batch(
                batch_date=_to_iso_date(date_from),
                step=args.step,
                mode=args.mode,
                started_at=started_at.isoformat(),
                finished_at=datetime.datetime.now(datetime.UTC).isoformat(),
                status="ok",
            )
            return

        if args.mode == "mykeibadb" and args.step == "special-entries":
            _log.info("--- mykeibadb 特別登録取り込み ---")
            ingest_mykeibadb_special_entries(api, date_from, date_to)
            _log.info("=== ingestion-worker 完了 ===")
            api.log_batch(
                batch_date=_to_iso_date(date_from),
                step=args.step,
                mode=args.mode,
                started_at=started_at.isoformat(),
                finished_at=datetime.datetime.now(datetime.UTC).isoformat(),
                status="ok",
            )
            return

        client = _build_client(args.mode, race_option=args.race_option)

        if args.step in ("all", "masters"):
            _log.info("--- マスタデータ取り込み ---")
            ingest_masters(client, api)

        chunks = iter_date_chunks(date_from, date_to, args.chunk_days)
        if len(chunks) > 1:
            _log.info("--- 日付レンジ分割: %d チャンク ---", len(chunks))

        for chunk_from, chunk_to in chunks:
            if len(chunks) > 1:
                _log.info("--- 取り込み範囲 %s→%s ---", chunk_from, chunk_to)

            if args.step in ("all", "entries"):
                _log.info("--- 出走表取り込み ---")
                ingest_entries(client, api, chunk_from, chunk_to)

            if args.step in ("all", "results"):
                _log.info("--- 確定成績取り込み ---")
                ingest_results(
                    client,
                    api,
                    chunk_from,
                    chunk_to,
                    race_keys=incomplete_race_keys,
                )

        _log.info("=== ingestion-worker 完了 ===")
        api.log_batch(
            batch_date=_to_iso_date(date_from),
            step=args.step,
            mode=args.mode,
            started_at=started_at.isoformat(),
            finished_at=datetime.datetime.now(datetime.UTC).isoformat(),
            status="ok",
        )

    except Exception as exc:
        _log.error("致命的エラー: %s", exc, exc_info=True)
        err_str = str(exc)
        api.log_batch(
            batch_date=_to_iso_date(date_from),
            step=args.step,
            mode=args.mode,
            started_at=started_at.isoformat(),
            finished_at=datetime.datetime.now(datetime.UTC).isoformat(),
            status="error",
            error_msg=err_str[:2000],
        )
        _notify_failure(args.step, date_from, err_str)
        sys.exit(1)


if __name__ == "__main__":
    main()
