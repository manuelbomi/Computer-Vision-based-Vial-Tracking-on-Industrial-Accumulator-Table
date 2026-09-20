# Vial Tracking Dashboard

A small React + TypeScript web dashboard for the analytics output of the
[Vial Tracking on Industrial Accumulator Table](..) pipeline: a before/after
tracking image, summary stat tiles, an interactive disposition breakdown
chart, a rim-radius distribution histogram, and a sortable/filterable
per-vial table — all reading directly from the CSV `vial_analytics.py`
already writes.

## Running it

```bash
npm install
npm run dev
```

This serves the bundled sample data (generated from the repo's own
`generate_sample_video.py` run) at http://localhost:5173.

## Viewing your own run

After running the main pipeline's Quickstart from the repo root:

```bash
python generate_sample_video.py sample_vials.avi
python vial_persistent_tracker.py sample_vials.avi persistent_tracked.avi
python vial_analytics.py persistent_tracked_tracks.csv --out-dir analytics_output
```

Sync that output into the dashboard's `public/` folder and reload:

```bash
cd dashboard
npm run sync-data
```

`scripts/sync-data.mjs` copies `../analytics_output/vial_disposition.csv`
and the two tracking images from `../docs/images/` into `public/`. Pass
different paths as arguments if your output lives elsewhere:

```bash
npm run sync-data -- ../path/to/analytics_output ../path/to/images
```

## Building for deployment

```bash
npm run build
```

Outputs a static site to `dist/` — deployable to any static host (GitHub
Pages, Netlify, S3, etc.). It's a static SPA with no backend: everything is
computed client-side from the CSV.

## Project layout

```
dashboard/
├── src/
│   ├── components/       # StatTiles, DispositionChart, RadiusHistogram, VialTable
│   ├── lib/loadDispositions.ts  # fetch + parse vial_disposition.csv
│   ├── theme.ts           # colors shared with vial_analytics.py's own charts
│   ├── types.ts
│   └── App.tsx
├── public/data/            # the CSV the app fetches at runtime
├── public/images/          # tracking screenshots shown at the top of the page
└── scripts/sync-data.mjs   # copies a fresh pipeline run into public/
```

Colors for PASS/REVIEW/REJECT/EXCLUDED and the radius histogram match
`vial_analytics.py`'s `COLOR_GOOD` / `COLOR_WARNING` / `COLOR_CRITICAL` /
`COLOR_MUTED` / `COLOR_SEQUENTIAL` constants exactly, so the dashboard and
the static charts in the main README's `docs/images/` never disagree.

## Stack

Vite + React 19 + TypeScript + [Recharts](https://recharts.org/). No CSS
framework, no state-management or data-fetching library — the data is one
CSV loaded once per page load, which doesn't need either.
