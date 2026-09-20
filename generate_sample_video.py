"""
generate_sample_video.py
=========================

Synthesizes a short top-down, backlit accumulator-table video so the rest
of this pipeline (vial_detection.py, vial_persistent_tracker.py,
vial_analytics.py) can be run and demonstrated end to end without a real
camera or proprietary factory footage. Swap in your own camera recording
for a real deployment -- see README > Usage.

The simulated vials are bright filled circles on a dark background, the
same high-contrast silhouette a real backlit, global-shutter, monochrome
camera produces (see the README's camera & lighting section), with:

  - normal drift + jitter for most vials, so tracking has something to do,
  - a handful of vials nudged into a touching/overlapping cluster, so the
    watershed detector path (--watershed) has something real to recover,
  - one deliberately near-stationary vial, so vial_analytics.py's jam
    alert has a real example to report,
  - two deliberately mis-sized vials, so vial_analytics.py's
    SIZE_ANOMALY / REVIEW / REJECT disposition has real examples to flag.
"""

import argparse

import cv2
import numpy as np

BACKGROUND_GRAY = 25   # dark background level, matches a backlit rig
VIAL_GRAY = 235         # bright vial silhouette level
NOISE_SIGMA = 4.0       # per-pixel sensor-noise stand-in


def _make_vials(rng, n_vials, width, height, min_radius, max_radius):
    vials = []
    for i in range(n_vials):
        radius = rng.uniform(min_radius, max_radius)
        if i == 0:
            radius = min_radius * 0.55   # deliberately undersized -> SIZE_ANOMALY
        elif i == 1:
            radius = max_radius * 1.35   # deliberately oversized -> SIZE_ANOMALY
        x = rng.uniform(radius + 2, width - radius - 2)
        y = rng.uniform(radius + 2, height - radius - 2)
        vx, vy = rng.uniform(-1.2, 1.2, size=2)
        jam = i == 2                      # one deliberately near-stationary vial
        if jam:
            vx, vy = 0.0, 0.0
        vials.append({"x": x, "y": y, "vx": vx, "vy": vy, "r": radius, "jam": jam})

    # Nudge a few vials into a touching cluster so the watershed detector
    # path has something real to demonstrate.
    if n_vials >= 6:
        cx, cy = width * 0.35, height * 0.65
        for k, v in enumerate(vials[3:6]):
            angle = k * 2.1
            v["x"] = cx + 0.9 * v["r"] * np.cos(angle)
            v["y"] = cy + 0.9 * v["r"] * np.sin(angle)
            v["vx"] *= 0.2
            v["vy"] *= 0.2
    return vials


def generate(out_path, width=640, height=640, n_frames=60, fps=12,
             n_vials=40, min_radius=16, max_radius=26, seed=7):
    rng = np.random.default_rng(seed)
    vials = _make_vials(rng, n_vials, width, height, min_radius, max_radius)

    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"MJPG"), fps, (width, height))

    for _ in range(n_frames):
        frame = np.full((height, width), BACKGROUND_GRAY, dtype=np.uint8)

        for v in vials:
            if not v["jam"]:
                v["x"] += v["vx"] + rng.normal(0, 0.15)
                v["y"] += v["vy"] + rng.normal(0, 0.15)
                # Bounce off the table edges like vials nudging against the rail.
                if v["x"] < v["r"] or v["x"] > width - v["r"]:
                    v["vx"] *= -1
                if v["y"] < v["r"] or v["y"] > height - v["r"]:
                    v["vy"] *= -1
                v["x"] = float(np.clip(v["x"], v["r"], width - v["r"]))
                v["y"] = float(np.clip(v["y"], v["r"], height - v["r"]))
            cv2.circle(frame, (int(v["x"]), int(v["y"])), int(v["r"]), VIAL_GRAY, -1, cv2.LINE_AA)

        noise = rng.normal(0, NOISE_SIGMA, size=frame.shape)
        frame = np.clip(frame.astype(np.float32) + noise, 0, 255).astype(np.uint8)
        writer.write(cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))

    writer.release()
    print(f"Wrote {n_frames} frames ({width}x{height} @ {fps}fps) -> {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", default="sample_vials.avi")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=640)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--n-vials", type=int, default=40)
    parser.add_argument("--min-radius", type=int, default=16)
    parser.add_argument("--max-radius", type=int, default=26)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    generate(
        args.output, width=args.width, height=args.height, n_frames=args.frames,
        fps=args.fps, n_vials=args.n_vials, min_radius=args.min_radius,
        max_radius=args.max_radius, seed=args.seed,
    )
