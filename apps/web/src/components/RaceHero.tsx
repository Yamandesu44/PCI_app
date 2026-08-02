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
  const resultSpeed = paceSpeedFromIndex(race.rpci_actual, race.track_type);
  const pci3Speed = paceSpeedFromIndex(race.pci3_actual, race.track_type);
  const primaryMetric =
    mode === "forecast"
      ? { label: "出走頭数", value: `${race.field_size}頭` }
      : { label: "実績ペース", value: `${resultSpeed.symbol} ${resultSpeed.label}` };
  const statusClass = tone === "confirmed"
    ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
    : "border-sky-400/30 bg-sky-400/10 text-sky-300";

  return (
    <section className="relative overflow-hidden rounded-lg border border-[#20312b] bg-[#111816] p-6 text-white shadow-lg md:p-8">
      <span className="absolute inset-x-0 top-0 h-1 bg-emerald-500" />
      <div className="grid gap-7 lg:grid-cols-[minmax(0,1.2fr)_minmax(360px,0.8fr)] lg:items-center">
        <div className="min-w-0">
          <span className={`inline-flex rounded-md border px-2.5 py-1 text-xs font-semibold ${statusClass}`}>
            {statusLabel(race.status)}
          </span>
          <p className="mb-2 mt-5 text-xs font-semibold uppercase text-emerald-400">
            Race review
          </p>
          <h1 className="m-0 text-3xl font-semibold leading-tight tracking-normal md:text-4xl">
          {jyoName(race.jyo_cd)} {raceNumber(race.race_key)}
          </h1>
          <p className="m-0 mt-3 text-sm font-medium text-slate-400">
          {formatRaceDate(race.race_date)} ・ {race.track_type}
          {race.distance_m}m
          {race.grade ? ` ・ ${race.grade}` : ""}
          {race.race_class ? ` ・ ${race.race_class}` : ""}
          </p>
        </div>

        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-white/10 bg-white/10">
          {[
            { label: primaryMetric.label, value: primaryMetric.value },
            { label: "天候", value: optionalLabel(race.weather) },
            { label: "馬場", value: optionalLabel(race.track_condition) },
            { label: "上位3頭の傾向", value: `${pci3Speed.symbol} ${pci3Speed.label}` },
          ].map((item) => (
            <div key={item.label} className="min-w-0 bg-[#17201d] p-4">
              <dt className="text-xs font-semibold text-slate-400">{item.label}</dt>
              <dd className="m-0 mt-1 truncate text-base font-semibold text-white">{item.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
