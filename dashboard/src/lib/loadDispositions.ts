import type { Disposition, VialRow } from "../types";

const BOOLEAN_TRUE = "True";

/**
 * Parses the plain, unquoted CSV written by vial_analytics.py
 * (aggregate_per_vial / classify_vials in vial_analytics.py). No values in
 * that output ever contain a comma, so a full RFC-4180 parser is
 * unnecessary here.
 */
function parseCsv(text: string): VialRow[] {
  const lines = text.trim().split(/\r?\n/);
  const [, ...rows] = lines;

  return rows.map((line) => {
    const [
      vialId,
      framesTracked,
      firstFrame,
      lastFrame,
      dwellTimeSec,
      meanRadius,
      stdRadius,
      pathLengthPx,
      flickerRatio,
      lastX,
      lastY,
      lowConfidence,
      sizeAnomaly,
      unstableRim,
      intermittent,
      jamAlert,
      disposition,
    ] = line.split(",");

    return {
      vialId: Number(vialId),
      framesTracked: Number(framesTracked),
      firstFrame: Number(firstFrame),
      lastFrame: Number(lastFrame),
      dwellTimeSec: Number(dwellTimeSec),
      meanRadius: Number(meanRadius),
      stdRadius: Number(stdRadius),
      pathLengthPx: Number(pathLengthPx),
      flickerRatio: Number(flickerRatio),
      lastX: Number(lastX),
      lastY: Number(lastY),
      lowConfidence: lowConfidence === BOOLEAN_TRUE,
      sizeAnomaly: sizeAnomaly === BOOLEAN_TRUE,
      unstableRim: unstableRim === BOOLEAN_TRUE,
      intermittent: intermittent === BOOLEAN_TRUE,
      jamAlert: jamAlert === BOOLEAN_TRUE,
      disposition: disposition.trim() as Disposition,
    };
  });
}

export async function loadDispositions(csvUrl: string): Promise<VialRow[]> {
  const response = await fetch(csvUrl);
  if (!response.ok) {
    throw new Error(`Failed to load ${csvUrl}: ${response.status} ${response.statusText}`);
  }
  return parseCsv(await response.text());
}
