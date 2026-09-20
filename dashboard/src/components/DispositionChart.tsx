import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { VialRow, Disposition } from "../types";
import { STATUS_COLOR, INK } from "../theme";

const ORDER: Disposition[] = ["PASS", "REVIEW", "REJECT", "EXCLUDED"];

interface DispositionChartProps {
  rows: VialRow[];
}

export function DispositionChart({ rows }: DispositionChartProps) {
  const data = ORDER.map((disposition) => ({
    disposition,
    count: rows.filter((r) => r.disposition === disposition).length,
  }));

  return (
    <div>
      <h3>Vial disposition breakdown</h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 24, right: 16, bottom: 8, left: 0 }}>
          <XAxis
            dataKey="disposition"
            tickLine={false}
            axisLine={{ stroke: INK.grid }}
            tick={{ fill: INK.secondary, fontSize: 13 }}
          />
          <YAxis hide />
          <Tooltip
            cursor={{ fill: INK.grid, opacity: 0.4 }}
            contentStyle={{ borderColor: INK.grid, fontSize: 13 }}
            formatter={(value) => [value, "Vials"]}
          />
          <Bar
            dataKey="count"
            radius={[4, 4, 0, 0]}
            maxBarSize={64}
            label={{ position: "top", fill: INK.primary, fontSize: 13, fontWeight: 600 }}
          >
            {data.map((d) => (
              <Cell key={d.disposition} fill={STATUS_COLOR[d.disposition]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
