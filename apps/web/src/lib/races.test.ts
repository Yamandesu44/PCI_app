import { describe, expect, it } from "vitest";

import type { RaceSummary } from "@pci/api-client";

import {
  compareRaceSummary,
  formatRaceDate,
  groupRacesByDateAndVenue,
  jyoName,
  raceClassLabel,
  raceCondition,
  raceHref,
  raceDates,
  raceNumber,
  raceNumberValue,
  raceTitle,
  statusLabel,
  statusTone,
} from "./races";

function makeRace(overrides: Partial<RaceSummary> = {}): RaceSummary {
  return {
    race_key: "2026062005010111",
    race_date: "2026-06-20",
    jyo_cd: "05",
    distance_m: 1600,
    track_type: "芝",
    status: "entries",
    field_size: 16,
    grade: null,
    race_class: null,
    ...overrides,
  };
}

describe("jyoName", () => {
  it("既知の競馬場コードを名称へ変換する", () => {
    expect(jyoName("05")).toBe("東京");
    expect(jyoName("06")).toBe("中山");
    expect(jyoName("09")).toBe("阪神");
  });

  it("未知コードはそのまま返す", () => {
    expect(jyoName("99")).toBe("99");
  });
});

describe("statusTone / statusLabel", () => {
  it("result は確定後に対応づける", () => {
    expect(statusTone("result")).toBe("confirmed");
    expect(statusLabel("result")).toBe("確定後");
  });

  it("entries は出走前に対応づける", () => {
    expect(statusTone("entries")).toBe("upcoming");
    expect(statusLabel("entries")).toBe("出走前");
  });

  it("未知状態は出走前にフォールバックする", () => {
    expect(statusTone("???")).toBe("upcoming");
    expect(statusLabel("???")).toBe("出走前");
  });
});

describe("raceHref", () => {
  it("出走前は forecast へ遷移する", () => {
    const race = makeRace({ status: "entries" });
    expect(raceHref(race)).toBe("/races/2026062005010111/forecast");
  });

  it("確定後は pace-analysis へ遷移する", () => {
    const race = makeRace({ status: "result" });
    expect(raceHref(race)).toBe("/races/2026062005010111/pace-analysis");
  });
});

describe("raceNumber", () => {
  it("末尾2桁から R 付きレース番号を取り出す", () => {
    expect(raceNumber("2026062005010111")).toBe("11R");
    expect(raceNumber("2026062005010101")).toBe("1R");
  });

  it("16桁でない場合はそのまま返す", () => {
    expect(raceNumber("SHORT")).toBe("SHORT");
  });
});

describe("formatRaceDate", () => {
  it("ISO 日付を M月D日 へ整形する", () => {
    expect(formatRaceDate("2026-06-20")).toBe("6月20日");
    expect(formatRaceDate("2026-12-01")).toBe("12月1日");
  });

  it("不正な日付はそのまま返す", () => {
    expect(formatRaceDate("not-a-date")).toBe("not-a-date");
  });
});

describe("raceTitle", () => {
  it("競馬場・レース番号・トラック・距離を1行に整形する", () => {
    const race = makeRace({ jyo_cd: "05", track_type: "芝", distance_m: 1600 });
    expect(raceTitle(race)).toBe("東京 11R ・ 芝1600m");
  });
});

describe("raceCondition / raceClassLabel", () => {
  it("コース条件を短く表示する", () => {
    expect(raceCondition(makeRace({ track_type: "ダ", distance_m: 1700 }))).toBe("ダ1700m");
  });

  it("レース名を優先し、特別登録の接尾辞を外して表示する", () => {
    expect(raceClassLabel(makeRace({ grade: "G3", race_class: "函館記念 特別登録" }))).toBe("函館記念");
    expect(raceClassLabel(makeRace({ grade: null, race_class: "3勝" }))).toBe("3勝");
    expect(raceClassLabel(makeRace({ grade: null, race_class: null }))).toBe("一般");
    expect(raceClassLabel(makeRace({ grade: null, race_class: "@" }))).toBe("一般");
    expect(raceClassLabel(makeRace({ grade: "@", race_class: null }))).toBe("一般");
  });
});

describe("raceNumberValue / compareRaceSummary", () => {
  it("レース番号をソート用の数値にする", () => {
    expect(raceNumberValue("2026062005010109")).toBe(9);
    expect(raceNumberValue("SHORT")).toBe(999);
  });

  it("開催日・競馬場・レース番号の順に並べる", () => {
    const races = [
      makeRace({ race_key: "2026062106010111", race_date: "2026-06-21", jyo_cd: "06" }),
      makeRace({ race_key: "2026062005010110", race_date: "2026-06-20", jyo_cd: "05" }),
      makeRace({ race_key: "2026062005010109", race_date: "2026-06-20", jyo_cd: "05" }),
    ];

    expect([...races].sort(compareRaceSummary).map((race) => race.race_key)).toEqual([
      "2026062005010109",
      "2026062005010110",
      "2026062106010111",
    ]);
  });
});

describe("groupRacesByDateAndVenue", () => {
  it("日付ごと、競馬場ごとにまとめ、レース番号順に並べる", () => {
    const races = [
      makeRace({ race_key: "2026062106010111", race_date: "2026-06-21", jyo_cd: "06" }),
      makeRace({ race_key: "2026062009010102", race_date: "2026-06-20", jyo_cd: "09" }),
      makeRace({ race_key: "2026062005010110", race_date: "2026-06-20", jyo_cd: "05" }),
      makeRace({ race_key: "2026062005010109", race_date: "2026-06-20", jyo_cd: "05" }),
    ];

    const groups = groupRacesByDateAndVenue(races);

    expect(groups.map((group) => group.raceDate)).toEqual(["2026-06-20", "2026-06-21"]);
    expect(groups[0]?.venues.map((venue) => venue.venueName)).toEqual(["東京", "阪神"]);
    expect(groups[0]?.venues[0]?.races.map((race) => race.race_key)).toEqual([
      "2026062005010109",
      "2026062005010110",
    ]);
    expect(groups[1]?.venues[0]?.venueName).toBe("中山");
  });
});

describe("raceDates", () => {
  it("重複を除いた開催日を昇順で返す", () => {
    const races = [
      makeRace({ race_date: "2026-06-28" }),
      makeRace({ race_date: "2026-06-27" }),
      makeRace({ race_date: "2026-06-28" }),
    ];

    expect(raceDates(races)).toEqual(["2026-06-27", "2026-06-28"]);
  });
});
