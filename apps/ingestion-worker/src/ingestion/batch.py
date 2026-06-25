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


def ingest_mykeibadb_special_entries(api: IngestApiClient, date_from: str, date_to: str) -> None:
    """mykeibadb の特別登録テーブルから出走前レースを取り込む。"""
    from ingestion.client.mykeibadb_client import MyKeibaDbClient

    client = MyKeibaDbClient()
    for race_key in sorted(client.excluded_race_keys):
        try:
            api.delete_race(race_key)
        except Exception as exc:
            _log.error("mykeibadb 除外レース削除エラー %s: %s", race_key, exc)

    races = client.fetch_special_entries(date_from, date_to)
    horses = client.fetch_special_horses(date_from, date_to)

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
) -> None:
    """SE レコード（DataKubun=4/7）+ RA レコード（DataKubun=7）から確定成績を取り込む。"""
    # race_key → RaceResultRecord のバッファ
    race_results: dict[str, RaceResultRecord] = {}

    # RA 確定レコード（DataKubun=7）から HaronTimeL3（後半3F）を収集する。
    # ingest_entries より後に呼ばれるが、RA は SE と独立したデータ種別のため再取得可能。
    race_s3f_map: dict[str, float] = {}
    race_l3f_map: dict[str, float] = {}
    for rec in client.iter_ra_records(date_from, date_to):
        try:
            ra = _parse_ra(rec)
            if ra:
                if ra.race_s3f is not None:
                    race_s3f_map[ra.race_key] = ra.race_s3f
                if ra.race_l3f is not None:
                    race_l3f_map[ra.race_key] = ra.race_l3f
        except Exception as exc:
            _log.warning("RA(results) パースエラー: %s | %.40s", exc, rec)

    for rec in client.iter_se_records(date_from, date_to):
        try:
            race_key = parse_race_key_from_se(rec)
            result = parse_se_result(rec)
            if result is None:
                continue

            if race_key not in race_results:
                race_results[race_key] = RaceResultRecord(race_key=race_key)
            race_results[race_key].results.append(result)
        except Exception as exc:
            _log.warning("SE(result) パースエラー: %s | %.40s", exc, rec)

    for race_key, rr in race_results.items():
        if not rr.results:
            continue
        rr.race_s3f = race_s3f_map.get(race_key)
        rr.race_l3f = race_l3f_map.get(race_key)
        if rr.race_s3f is not None and rr.race_l3f is not None:
            _log.debug("HaronTime 取得 %s: S3=%.1f L3=%.1f", race_key, rr.race_s3f, rr.race_l3f)
        try:
            api.record_results(rr)
        except Exception as exc:
            _log.error("成績送信エラー %s: %s", race_key, exc)


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
        choices=["all", "masters", "entries", "results", "special-entries"],
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
    args = parser.parse_args()

    date_from: str = args.date
    date_to: str = args.date_to or args.date

    api_base_url = os.environ.get("API_BASE_URL", "http://localhost:8000")
    ingest_token = os.environ.get("INGEST_TOKEN", "")

    api = IngestApiClient(base_url=api_base_url, token=ingest_token)

    _log.info(
        "=== ingestion-worker 開始 mode=%s date=%s→%s race_option=%s ===",
        args.mode,
        date_from,
        date_to,
        args.race_option,
    )

    try:
        if args.mode == "mykeibadb":
            if args.step == "special-entries":
                _log.info("--- mykeibadb 特別登録取り込み ---")
                ingest_mykeibadb_special_entries(api, date_from, date_to)
                _log.info("=== ingestion-worker 完了 ===")
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
                ingest_results(client, api, chunk_from, chunk_to)

        _log.info("=== ingestion-worker 完了 ===")

    except Exception as exc:
        _log.error("致命的エラー: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
