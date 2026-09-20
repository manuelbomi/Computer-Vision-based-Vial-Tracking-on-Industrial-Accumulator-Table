export type Disposition = "PASS" | "REVIEW" | "REJECT" | "EXCLUDED";

export interface VialRow {
  vialId: number;
  framesTracked: number;
  firstFrame: number;
  lastFrame: number;
  dwellTimeSec: number;
  meanRadius: number;
  stdRadius: number;
  pathLengthPx: number;
  flickerRatio: number;
  lastX: number;
  lastY: number;
  lowConfidence: boolean;
  sizeAnomaly: boolean;
  unstableRim: boolean;
  intermittent: boolean;
  jamAlert: boolean;
  disposition: Disposition;
}
