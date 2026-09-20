import type { VialRow } from "../types";
import { STATUS_COLOR } from "../theme";
import "./StatTiles.css";

interface StatTilesProps {
  rows: VialRow[];
}

export function StatTiles({ rows }: StatTilesProps) {
  const total = rows.length;
  const countOf = (disposition: VialRow["disposition"]) =>
    rows.filter((r) => r.disposition === disposition).length;
  const jamCount = rows.filter((r) => r.jamAlert).length;

  const tiles: { label: string; value: number; color?: string }[] = [
    { label: "Total vial tracks", value: total },
    { label: "PASS", value: countOf("PASS"), color: STATUS_COLOR.PASS },
    { label: "REVIEW", value: countOf("REVIEW"), color: STATUS_COLOR.REVIEW },
    { label: "REJECT", value: countOf("REJECT"), color: STATUS_COLOR.REJECT },
    { label: "EXCLUDED", value: countOf("EXCLUDED"), color: STATUS_COLOR.EXCLUDED },
    { label: "Jam alerts", value: jamCount, color: jamCount > 0 ? STATUS_COLOR.REVIEW : undefined },
  ];

  return (
    <div className="stat-tiles" role="list">
      {tiles.map((tile) => (
        <div className="stat-tile" role="listitem" key={tile.label}>
          <div className="stat-tile-label">{tile.label}</div>
          <div className="stat-tile-value" style={tile.color ? { color: tile.color } : undefined}>
            {tile.value}
          </div>
        </div>
      ))}
    </div>
  );
}
