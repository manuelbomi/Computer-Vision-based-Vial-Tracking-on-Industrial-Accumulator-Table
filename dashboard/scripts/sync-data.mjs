// Copies the latest pipeline output into public/, so the dashboard shows
// your own run instead of the bundled sample data.
//
// Usage (from dashboard/):
//   node scripts/sync-data.mjs [path-to-analytics_output] [path-to-docs/images]
import { copyFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const dashboardRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const analyticsDir = resolve(dashboardRoot, process.argv[2] ?? "../analytics_output");
const imagesDir = resolve(dashboardRoot, process.argv[3] ?? "../docs/images");

function copy(src, destRelative) {
  if (!existsSync(src)) {
    console.warn(`skip (not found): ${src}`);
    return;
  }
  const dest = join(dashboardRoot, "public", destRelative);
  copyFileSync(src, dest);
  console.log(`${src} -> public/${destRelative}`);
}

copy(join(analyticsDir, "vial_disposition.csv"), "data/vial_disposition.csv");
copy(join(imagesDir, "before_after_tracking.png"), "images/before_after_tracking.png");
copy(join(imagesDir, "persistent_tracking_frame.png"), "images/persistent_tracking_frame.png");
