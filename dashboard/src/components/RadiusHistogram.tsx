import {
  Bar,
  BarChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { VialRow } from "../types";
import { SEQUENTIAL_HUE, INK } from "../theme";

const BIN_COUNT = 20;
// Mirrors vial_analytics.py's DEFAULT_SIZE_SIGMA (the size-anomaly band is
// +/- this many standard deviations from the population mean radius).
const SIZE_SIGMA = 2.0;

interface RadiusHistogramProps {
  rows: VialRow[];
}

function mean(values: number[]): number {
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

function stdDev(values: number[], populationMean: number): number {
  const variance = mean(values.map((v) => (v - populationMean) ** 2));
  return Math.sqrt(variance) || 1e-6;
}

export function RadiusHistogram({ rows }: RadiusHistogramProps) {
  const radii = rows.map((r) => r.meanRadius);
  // Population stats come from "confident" tracks only, matching
  // classify_vials() in vial_analytics.py (excludes low_confidence tracks).
  const confidentRadii = rows.filter((r) => !r.lowConfidence).map((r) => r.meanRadius);
  const popMean = mean(confidentRadii);
  const popStd = stdDev(confidentRadii, popMean);

  const min = Math.min(...radii);
  const max = Math.max(...radii);
  const binWidth = (max - min) / BIN_COUNT || 1;

  const bins = Array.from({ length: BIN_COUNT }, (_, i) => {
    const lo = min + i * binWidth;
    const hi = lo + binWidth;
    return {
      mid: lo + binWidth / 2,
      lo,
      hi,
      count: radii.filter((r) => (i === BIN_COUNT - 1 ? r >= lo && r <= hi : r >= lo && r < hi)).length,
    };
  });

  return (
    <div>
      <h3>Rim radius distribution</h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={bins} margin={{ top: 24, right: 16, bottom: 8, left: 0 }}>
          <XAxis
            type="number"
            dataKey="mid"
            domain={[min, max]}
            tickFormatter={(v: number) => v.toFixed(0)}
            tickLine={false}
            axisLine={{ stroke: INK.grid }}
            tick={{ fill: INK.secondary, fontSize: 11 }}
            label={{ value: "Mean radius (px)", position: "insideBottom", offset: -4, fill: INK.secondary, fontSize: 12 }}
          />
          <YAxis hide />
          <Tooltip
            cursor={{ fill: INK.grid, opacity: 0.4 }}
            contentStyle={{ borderColor: INK.grid, fontSize: 13 }}
            labelFormatter={(_, payload) => {
              const p = payload?.[0]?.payload as { lo: number; hi: number } | undefined;
              return p ? `${p.lo.toFixed(1)}–${p.hi.toFixed(1)} px` : "";
            }}
            formatter={(value) => [value, "Vials"]}
          />
          <ReferenceArea
            x1={popMean - SIZE_SIGMA * popStd}
            x2={popMean + SIZE_SIGMA * popStd}
            fill={SEQUENTIAL_HUE}
            fillOpacity={0.08}
            ifOverflow="extendDomain"
          />
          <ReferenceLine
            x={popMean}
            stroke={INK.secondary}
            strokeDasharray="4 4"
            label={{ value: "batch mean", position: "top", fill: INK.secondary, fontSize: 12 }}
          />
          <Bar dataKey="count" fill={SEQUENTIAL_HUE} radius={[2, 2, 0, 0]} barSize={16} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
