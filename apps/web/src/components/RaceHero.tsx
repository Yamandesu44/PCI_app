import { formatRaceDate, jyoName, raceNumber, statusLabel, statusTone } from "@/lib/races";
import type { RaceDetail } from "@pci/api-client";

interface RaceHeroProps {
  race: RaceDetail;
  mode: "forecast" | "analysis";
}

function optionalLabel(value: string | null | undefined): string {
  return value && value.trim().length > 0 ? value : "未発表";
}

function fmt(value: number | null | undefined): string {
  return value !== null && value !== undefined ? value.toFixed(1) : "-";
}

/** レース詳細ページの冒頭で、予測・分析の前提になる条件をひと目で伝える。 */
export function RaceHero({ race, mode }: RaceHeroProps) {
  const tone = statusTone(race.status);
  const primaryMetric =
    mode === "forecast"
      ? { label: "出走頭数", value: `${race.field_size}頭` }
      : { label: "実績RPCI", value: fmt(race.rpci_actual) };

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
          <dt>PCI3</dt>
          <dd>{fmt(race.pci3_actual)}</dd>
        </div>
      </dl>
    </section>
  );
}
