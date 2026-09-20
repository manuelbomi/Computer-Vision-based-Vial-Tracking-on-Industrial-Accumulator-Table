import type { Disposition } from "./types";

/**
 * Colors mirror the validated palette used by vial_analytics.py's own
 * matplotlib charts (COLOR_GOOD / COLOR_WARNING / COLOR_CRITICAL /
 * COLOR_MUTED / COLOR_SEQUENTIAL), so the dashboard and the static charts
 * in the README always agree. Status colors are reserved for disposition
 * state only and never reused for anything else in this app.
 */
export const STATUS_COLOR: Record<Disposition, string> = {
  PASS: "#0ca30c",
  REVIEW: "#fab219",
  REJECT: "#d03b3b",
  EXCLUDED: "#898781",
};

export const SEQUENTIAL_HUE = "#2a78d6";

export const INK = {
  primary: "#0b0b0b",
  secondary: "#52514e",
  muted: "#898781",
  grid: "#e1e0d9",
  surface: "#fcfcfb",
};
