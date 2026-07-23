"""
vial_analytics.py
==================

Post-tracking analytics on the CSV produced by vial_persistent_tracker.py.

WHAT THIS FILE IS
-------------------
vial_persistent_tracker.py writes one row per (frame, vial) observation:

    frame, time_sec, vial_id, x, y, radius

That "long format" table is raw tracking telemetry -- on its own it doesn't
tell a line operator anything actionable. This script turns it into
per-vial summaries and three kinds of decision an accumulator-table
operator actually cares about:

  1. THROUGHPUT  -- how many distinct vials were seen, how long each one
                    dwelled in frame, overall counting/rate stats.
  2. PROCESS ALERTS ("jams") -- vials whose position barely changed across
                    a long stretch of frames, i.e. physically stuck on the
                    table. This is a mechanical/line-flow problem, not a
                    product-quality problem, so it is reported separately
                    from the disposition below.
  3. QUALITY DISPOSITION -- classify each vial as PASS / REVIEW / REJECT
                    using proxy signals available from tracking geometry
                    alone (rim radius consistency vs. the rest of the
                    batch, and how stable a single vial's own radius
                    reading is frame to frame).

===========================================================================
READ THIS BEFORE USING THE "DISPOSITION" OUTPUT ON A REAL LINE
===========================================================================
The only data this script has to work with is what the tracker measured:
a circle position and radius per vial per frame, from a single top-down
camera. That is NOT the same thing as a certified visual-inspection defect
detector. It can plausibly flag:
  - a vial whose rim reads a noticeably different size than the rest of
    the batch (SIZE_ANOMALY) -- could be a chipped/broken rim, could be a
    genuinely different SKU mixed in, could just be glare/occlusion noise.
  - a vial whose own radius reading wobbles a lot frame to frame
    (UNSTABLE_RIM) -- could be a rocking/tilted/deformed vial, could just
    be a vial sitting at the edge of two overlapping neighbors confusing
    the detector.
It CANNOT see cracks, chips too small to change the rim's outer silhouette,
cloudy/discolored glass, foreign particulate, fill-level, or stopper/cap
problems -- those require dedicated imaging (raking/side lighting to catch
surface defects, backlighting tuned for particulate, a fill-level line-scan
camera, etc.) and, typically, a trained defect-classification model, not
raw circle geometry.

Treat PASS/REVIEW/REJECT here as "worth a second look by a real inspection
station or a person" vs. "nothing geometrically unusual" -- a triage
signal, not a certified pass/fail. See the README's "Extending this to
real defect detection" section for how to fold a genuine defect-classifier
score into this same pipeline (short version: use the x, y, radius in this
CSV to crop each vial out of the source frames, run the crops through a
defect classifier, and merge the resulting defect_score column into
classify_vials() below).
===========================================================================
"""

import argparse
import os

import matplotlib
matplotlib.use("Agg")  # headless-safe: write PNG files, don't try to open a GUI window
import matplotlib.pyplot as plt
import pandas as pd

# ---------------------------------------------------------------------------
# Palette (validated for colorblind-safety / contrast; see project README).
# Status colors are reserved for exactly this kind of PASS/REVIEW/REJECT
# state and are never reused for anything else in these charts.
# ---------------------------------------------------------------------------
COLOR_GOOD = "#0ca30c"       # PASS
COLOR_WARNING = "#fab219"    # REVIEW
COLOR_CRITICAL = "#d03b3b"   # REJECT
COLOR_MUTED = "#898781"      # EXCLUDED / low-confidence, and muted chrome
COLOR_SEQUENTIAL = "#2a78d6"  # single-hue "magnitude" color, radius histogram
COLOR_SURFACE = "#fcfcfb"
COLOR_GRID = "#e1e0d9"
COLOR_TEXT_PRIMARY = "#0b0b0b"
COLOR_TEXT_SECONDARY = "#52514e"

# ---------------------------------------------------------------------------
# Tunable thresholds. These are deliberately exposed as function arguments
# (not baked-in constants) because the "right" values depend on your vial
# size, camera noise level, and how strict you want triage to be -- start
# with these defaults, then look at a week of real disposition output and
# adjust until REVIEW/REJECT rates match what a human inspector agrees with.
# ---------------------------------------------------------------------------
DEFAULT_MIN_TRACK_FRAMES = 3     # tracks shorter than this are detector noise, not real vials
DEFAULT_SIZE_SIGMA = 2.0         # size anomaly: |vial radius - batch mean| > N standard deviations
DEFAULT_CV_THRESHOLD = 0.12      # rim instability: std(radius)/mean(radius) within one vial's own track
DEFAULT_JAM_MIN_FRAMES = 8       # a track must be at least this long to even be eligible for a jam alert
DEFAULT_JAM_MAX_PATH_PX = 15.0   # ...and travel less than this many total pixels over that whole span
DEFAULT_FLICKER_THRESHOLD = 0.3  # fraction of frames within a track's span where the vial wasn't detected


def load_tracks(csv_path):
    """Load the raw per-frame tracking CSV written by vial_persistent_tracker.py."""
    df = pd.read_csv(csv_path)
    required = {"frame", "time_sec", "vial_id", "x", "y", "radius"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path} is missing expected columns: {missing}")
    return df


def infer_fps(df):
    """Recover the source video's frame rate from the frame/time_sec columns,
    rather than requiring the caller to pass it in separately (the CSV
    already encodes it: time_sec = frame / fps)."""
    nonzero = df[df["frame"] > 0]
    if nonzero.empty:
        return 10.0  # arbitrary safe fallback if the whole video was 1 frame
    row = nonzero.iloc[0]
    return float(row["frame"] / row["time_sec"])


def aggregate_per_vial(df, fps):
    """Collapse the long-format per-frame CSV into one summary row per vial_id.

    This is the key transformation: analytics and disposition decisions are
    made per *vial*, not per *frame*, so everything downstream works off
    this aggregated table.

    Columns produced
    -----------------
    frames_tracked      how many frames this vial was actually detected in
    first_frame/last_frame
                         the span of frames this vial's ID was alive for
    dwell_time_sec       wall-clock time between first and last detection
    mean_radius/std_radius
                         this vial's own rim-radius statistics across its track
    path_length_px        total wandering distance: the sum of frame-to-frame
                         center movements. This is deliberately NOT the same
                         as net displacement (start-to-end distance) -- a
                         vial that jitters back and forth would have a small
                         net displacement but a large path length, and only
                         path length correctly says "this vial has not
                         actually been moving."
    flicker_ratio         fraction of frames *within this vial's own span*
                         where it was NOT detected (present in the tracker's
                         memory via max_disappeared, but missing from this
                         frame's Hough/watershed output). A high flicker
                         ratio means the detector struggled with this vial
                         specifically -- worth a second look on its own.
    """
    rows = []
    for vial_id, track in df.groupby("vial_id"):
        track = track.sort_values("frame")
        frames_tracked = len(track)
        first_frame, last_frame = track["frame"].iloc[0], track["frame"].iloc[-1]
        span_frames = last_frame - first_frame + 1

        xy = track[["x", "y"]].to_numpy()
        # Consecutive frame-to-frame step distances, summed = total path length.
        steps = ((xy[1:] - xy[:-1]) ** 2).sum(axis=1) ** 0.5 if len(xy) > 1 else [0.0]
        path_length_px = float(sum(steps))

        rows.append({
            "vial_id": vial_id,
            "frames_tracked": frames_tracked,
            "first_frame": first_frame,
            "last_frame": last_frame,
            "dwell_time_sec": round(span_frames / fps, 3),
            "mean_radius": round(track["radius"].mean(), 2),
            "std_radius": round(track["radius"].std(ddof=0), 3) if frames_tracked > 1 else 0.0,
            "path_length_px": round(path_length_px, 1),
            "flicker_ratio": round(1 - frames_tracked / span_frames, 3),
            "last_x": int(track["x"].iloc[-1]),
            "last_y": int(track["y"].iloc[-1]),
        })
    return pd.DataFrame(rows)


def classify_vials(agg, min_track_frames=DEFAULT_MIN_TRACK_FRAMES,
                    size_sigma=DEFAULT_SIZE_SIGMA, cv_threshold=DEFAULT_CV_THRESHOLD,
                    jam_min_frames=DEFAULT_JAM_MIN_FRAMES, jam_max_path_px=DEFAULT_JAM_MAX_PATH_PX,
                    flicker_threshold=DEFAULT_FLICKER_THRESHOLD):
    """Add anomaly flags, a jam alert, and a PASS/REVIEW/REJECT disposition
    to the per-vial summary table produced by aggregate_per_vial().

    See the module docstring for what these labels do and don't mean.
    Batch statistics (population mean/std radius) are computed from each
    vial's *own mean radius* -- one number per vial -- rather than every
    raw per-frame radius reading, so a vial that happened to be tracked for
    many frames doesn't get extra weight in what "normal" looks like.
    """
    agg = agg.copy()

    confident = agg[agg["frames_tracked"] >= min_track_frames]
    pop_mean_radius = confident["mean_radius"].mean()
    pop_std_radius = confident["mean_radius"].std(ddof=0) or 1e-6  # guard against /0

    agg["low_confidence"] = agg["frames_tracked"] < min_track_frames
    agg["size_anomaly"] = (agg["mean_radius"] - pop_mean_radius).abs() > size_sigma * pop_std_radius
    agg["unstable_rim"] = (agg["std_radius"] / agg["mean_radius"].replace(0, 1e-6)) > cv_threshold
    agg["intermittent"] = agg["flicker_ratio"] > flicker_threshold
    agg["jam_alert"] = (
        (agg["frames_tracked"] >= jam_min_frames) & (agg["path_length_px"] < jam_max_path_px)
    )

    def disposition(row):
        if row["low_confidence"]:
            return "EXCLUDED"  # likely a detector blip, not a real vial -- not a quality judgment
        if row["size_anomaly"] and row["unstable_rim"]:
            return "REJECT"    # two independent geometric anomalies agreeing is a strong signal
        if row["size_anomaly"] or row["unstable_rim"] or row["intermittent"]:
            return "REVIEW"    # one anomaly present -- route to secondary/manual inspection
        return "PASS"

    agg["disposition"] = agg.apply(disposition, axis=1)
    agg.attrs["pop_mean_radius"] = pop_mean_radius
    agg.attrs["pop_std_radius"] = pop_std_radius
    return agg


def print_summary(agg):
    """Print an operator-readable summary to stdout."""
    total = len(agg)
    counts = agg["disposition"].value_counts()
    jams = agg[agg["jam_alert"]]

    print("=" * 60)
    print("VIAL TRACKING ANALYTICS SUMMARY")
    print("=" * 60)
    print(f"Total distinct vial tracks : {total}")
    print(f"  PASS      : {counts.get('PASS', 0)}")
    print(f"  REVIEW    : {counts.get('REVIEW', 0)}  (route to secondary/manual inspection)")
    print(f"  REJECT    : {counts.get('REJECT', 0)}  (divert before downstream filling/labeling)")
    print(f"  EXCLUDED  : {counts.get('EXCLUDED', 0)}  (too few frames to trust -- detector noise)")
    print(f"Population rim radius       : mean={agg.attrs['pop_mean_radius']:.2f}px, "
          f"std={agg.attrs['pop_std_radius']:.2f}px")
    print(f"Average dwell time in frame : {agg['dwell_time_sec'].mean():.2f}s")

    if len(jams):
        print(f"\nJAM ALERTS ({len(jams)} vial(s) barely moved while tracked -- "
              f"possible physical jam on the table):")
        for _, r in jams.iterrows():
            print(f"  vial_id={r['vial_id']:<5} last seen near (x={r['last_x']}, y={r['last_y']}), "
                  f"tracked {r['frames_tracked']} frames, moved only {r['path_length_px']:.1f}px total")
    else:
        print("\nNo jam alerts.")
    print("=" * 60)


def plot_disposition_breakdown(agg, out_path):
    """Status-colored bar chart of PASS / REVIEW / REJECT / EXCLUDED counts.

    Uses the reserved status palette (never used for anything else in this
    project) because this is literally state data, not an arbitrary
    category -- and always pairs color with a direct text label (the
    category name on the x-axis, the count above each bar) so the
    distinction is never carried by color alone.
    """
    order = ["PASS", "REVIEW", "REJECT", "EXCLUDED"]
    colors = [COLOR_GOOD, COLOR_WARNING, COLOR_CRITICAL, COLOR_MUTED]
    counts = agg["disposition"].value_counts().reindex(order, fill_value=0)

    fig, ax = plt.subplots(figsize=(6, 4.2), facecolor=COLOR_SURFACE)
    ax.set_facecolor(COLOR_SURFACE)
    bars = ax.bar(order, counts.values, color=colors, width=0.6, zorder=3)

    for bar, count in zip(bars, counts.values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3, str(count),
                ha="center", va="bottom", color=COLOR_TEXT_PRIMARY, fontsize=11, fontweight="bold")

    ax.set_title("Vial disposition breakdown", color=COLOR_TEXT_PRIMARY, fontsize=13, pad=14)
    ax.set_ylabel("Vials", color=COLOR_TEXT_SECONDARY)
    ax.tick_params(colors=COLOR_TEXT_SECONDARY)
    ax.grid(axis="y", color=COLOR_GRID, zorder=0)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(COLOR_GRID)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_radius_distribution(agg, out_path):
    """Histogram of per-vial mean rim radius, with the size-anomaly cutoff
    band overlaid, so it's visually obvious why any given vial landed in
    the SIZE_ANOMALY bucket.

    Single-hue sequential blue, since this is one continuous magnitude
    (radius in pixels), not a set of categories.
    """
    mean_r = agg.attrs["pop_mean_radius"]
    std_r = agg.attrs["pop_std_radius"]

    fig, ax = plt.subplots(figsize=(6.5, 4.2), facecolor=COLOR_SURFACE)
    ax.set_facecolor(COLOR_SURFACE)
    ax.hist(agg["mean_radius"], bins=20, color=COLOR_SEQUENTIAL, zorder=3)

    ax.axvline(mean_r, color=COLOR_TEXT_SECONDARY, linestyle="--", linewidth=1.5, zorder=4)
    ax.axvspan(mean_r - 2 * std_r, mean_r + 2 * std_r, color=COLOR_SEQUENTIAL, alpha=0.08, zorder=1)
    ax.text(mean_r, ax.get_ylim()[1] * 0.95, " batch mean", color=COLOR_TEXT_SECONDARY,
            fontsize=9, va="top")

    ax.set_title("Per-vial rim radius distribution", color=COLOR_TEXT_PRIMARY, fontsize=13, pad=14)
    ax.set_xlabel("Mean radius (px)", color=COLOR_TEXT_SECONDARY)
    ax.set_ylabel("Vials", color=COLOR_TEXT_SECONDARY)
    ax.tick_params(colors=COLOR_TEXT_SECONDARY)
    ax.grid(axis="y", color=COLOR_GRID, zorder=0)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(COLOR_GRID)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def run(csv_path, out_dir, fps=None, **threshold_kwargs):
    df = load_tracks(csv_path)
    fps = fps or infer_fps(df)

    agg = aggregate_per_vial(df, fps)
    agg = classify_vials(agg, **threshold_kwargs)

    os.makedirs(out_dir, exist_ok=True)
    disposition_csv = os.path.join(out_dir, "vial_disposition.csv")
    agg.to_csv(disposition_csv, index=False)

    plot_disposition_breakdown(agg, os.path.join(out_dir, "disposition_breakdown.png"))
    plot_radius_distribution(agg, os.path.join(out_dir, "radius_distribution.png"))

    print_summary(agg)
    print(f"\nPer-vial disposition table -> {disposition_csv}")
    print(f"Charts -> {out_dir}/disposition_breakdown.png, {out_dir}/radius_distribution.png")
    return agg


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", help="Per-frame tracking CSV from vial_persistent_tracker.py")
    parser.add_argument("--out-dir", default="analytics_output",
                         help="Directory to write the disposition CSV and charts into")
    parser.add_argument("--fps", type=float, default=None,
                         help="Override the auto-detected frame rate")
    parser.add_argument("--min-track-frames", type=int, default=DEFAULT_MIN_TRACK_FRAMES)
    parser.add_argument("--size-sigma", type=float, default=DEFAULT_SIZE_SIGMA)
    parser.add_argument("--cv-threshold", type=float, default=DEFAULT_CV_THRESHOLD)
    parser.add_argument("--jam-min-frames", type=int, default=DEFAULT_JAM_MIN_FRAMES)
    parser.add_argument("--jam-max-path-px", type=float, default=DEFAULT_JAM_MAX_PATH_PX)
    parser.add_argument("--flicker-threshold", type=float, default=DEFAULT_FLICKER_THRESHOLD)
    args = parser.parse_args()

    run(
        args.csv, args.out_dir, fps=args.fps,
        min_track_frames=args.min_track_frames, size_sigma=args.size_sigma,
        cv_threshold=args.cv_threshold, jam_min_frames=args.jam_min_frames,
        jam_max_path_px=args.jam_max_path_px, flicker_threshold=args.flicker_threshold,
    )
