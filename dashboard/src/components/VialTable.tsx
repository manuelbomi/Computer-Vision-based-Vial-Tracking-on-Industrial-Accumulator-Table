import { useMemo, useState } from "react";
import type { Disposition, VialRow } from "../types";
import { STATUS_COLOR } from "../theme";
import "./VialTable.css";

type SortKey = keyof Pick<
  VialRow,
  "vialId" | "framesTracked" | "dwellTimeSec" | "meanRadius" | "pathLengthPx" | "disposition"
>;

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: "vialId", label: "Vial ID", numeric: true },
  { key: "disposition", label: "Disposition" },
  { key: "framesTracked", label: "Frames tracked", numeric: true },
  { key: "dwellTimeSec", label: "Dwell (s)", numeric: true },
  { key: "meanRadius", label: "Mean radius (px)", numeric: true },
  { key: "pathLengthPx", label: "Path length (px)", numeric: true },
];

const FILTERS: (Disposition | "ALL")[] = ["ALL", "PASS", "REVIEW", "REJECT", "EXCLUDED"];

function DispositionBadge({ disposition }: { disposition: Disposition }) {
  return (
    <span className="disposition-badge">
      <span className="disposition-dot" style={{ background: STATUS_COLOR[disposition] }} aria-hidden />
      {disposition}
    </span>
  );
}

interface VialTableProps {
  rows: VialRow[];
}

export function VialTable({ rows }: VialTableProps) {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("ALL");
  const [sortKey, setSortKey] = useState<SortKey>("vialId");
  const [sortAsc, setSortAsc] = useState(true);

  const visibleRows = useMemo(() => {
    const filtered = filter === "ALL" ? rows : rows.filter((r) => r.disposition === filter);
    const sorted = [...filtered].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === "number" && typeof bv === "number") return av - bv;
      return String(av).localeCompare(String(bv));
    });
    return sortAsc ? sorted : sorted.reverse();
  }, [rows, filter, sortKey, sortAsc]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortAsc((asc) => !asc);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  }

  return (
    <div>
      <div className="table-toolbar">
        <h3>Per-vial disposition table</h3>
        <div className="table-filters" role="group" aria-label="Filter by disposition">
          {FILTERS.map((f) => (
            <button
              key={f}
              className={f === filter ? "filter-chip active" : "filter-chip"}
              onClick={() => setFilter(f)}
              type="button"
            >
              {f} {f !== "ALL" && `(${rows.filter((r) => r.disposition === f).length})`}
            </button>
          ))}
        </div>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {COLUMNS.map((col) => (
                <th key={col.key} onClick={() => toggleSort(col.key)}>
                  {col.label}
                  {sortKey === col.key ? (sortAsc ? " ↑" : " ↓") : ""}
                </th>
              ))}
              <th>Jam alert</th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => (
              <tr key={row.vialId}>
                <td className="numeric">{row.vialId}</td>
                <td>
                  <DispositionBadge disposition={row.disposition} />
                </td>
                <td className="numeric">{row.framesTracked}</td>
                <td className="numeric">{row.dwellTimeSec.toFixed(2)}</td>
                <td className="numeric">{row.meanRadius.toFixed(2)}</td>
                <td className="numeric">{row.pathLengthPx.toFixed(1)}</td>
                <td>{row.jamAlert ? "Yes" : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
