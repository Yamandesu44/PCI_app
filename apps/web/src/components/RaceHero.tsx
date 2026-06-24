import { formatRaceDate, jyoName, raceNumber, statusLabel, statusTone } from "@/lib/races";
import { paceSpeedFromIndex } from "@/lib/pace";
import type { RaceDetail } from "@pci/api-client";

interface RaceHeroProps {
  race: RaceDetail;
  mode: "forecast" | "analysis";
}

function optionalLabel(value: string | null | undefined): string {
  return value && value.trim().length > 0 ? value : "未発表";
}

/** レース詳細ページの冒頭で、予測・分析の前提になる条件をひと目で伝える。 */
export function RaceHero({ race, mode }: RaceHeroProps) {
  const tone = statusTone(race.status);
  const resultSpeed = paceSpeedFromIndex(race.rpci_actual);
  const pci3Speed = paceSpeedFromIndex(race.pci3_actual);
  const primaryMetric =
    mode === "forecast"
      ? { label: "出走頭数", value: `${race.field_size}頭` }
      : { label: "実績ペース", value: `${resultSpeed.symbol} ${resultSpeed.label}` };

  return (
    <section className={`race-hero race-hero-${tone}`}>
      <div className="race-hero-main">
        <span className={`race-status ${tone}`}>{statusLabel(race.status)}</span>
        <h1>
          {jyoName(race.jyo_cd)} {raceNumber(race.race_key)}
        </h1>
        <p className="race-hero-sub">
          {formatRaceDate(race.race_date)} ・ {race.track_type}
          {race.distance_m}m
          {race.grade ? ` ・ ${race.grade}` : ""}
          {race.race_class ? ` ・ ${race.race_class}` : ""}
        </p>
      </div>

      <dl className="race-hero-metrics">
        <div>
          <dt>{primaryMetric.label}</dt>
          <dd>{primaryMetric.value}</dd>
        </div>
        <div>
          <dt>天候</dt>
          <dd>{optionalLabel(race.weather)}</dd>
        </div>
        <div>
          <dt>馬場</dt>
          <dd>{optionalLabel(race.track_condition)}</dd>
        </div>
        <div>
          <dt>上位3頭ペース</dt>
          <dd style={{ color: pci3Speed.color }}>
            {pci3Speed.symbol} {pci3Speed.label}
          </dd>
        </div>
      </dl>
    </section>
  );
}
