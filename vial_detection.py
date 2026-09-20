"""
vial_detection.py
==================

Per-frame vial detection using the Hough Circle Transform.

Vials imaged top-down under backlighting show up as bright circular
silhouettes against a dark background, so detection is fundamentally a
round-object localization problem -- the same family of problem as
counting coins, cells, or bubbles. This module is the fast, default
detector used by vial_persistent_tracker.py: no training data, three
tunable parameters, real-time on CPU.

It works well when vials are isolated or loosely packed. For a table
dense enough that vials routinely touch or overlap, use the
distance-transform + watershed detector in vial_persistent_tracker.py
(--watershed flag) instead -- see the README's detection-algorithm
comparison table for the tradeoffs between the two.
"""

import argparse

import cv2
import numpy as np


def detect_vials(gray_frame, min_radius=8, max_radius=35, min_dist=18,
                  param1=60, param2=22, blur_ksize=5):
    """Detect circular vials in a single grayscale frame.

    Parameters
    ----------
    gray_frame : np.ndarray
        Single-channel (grayscale) frame.
    min_radius, max_radius : int
        Expected vial rim radius range in pixels. Measure a handful of
        vials in your own footage and set these with a few pixels of
        margin on each side.
    min_dist : int
        Minimum center-to-center distance between two accepted circles.
        Set close to (but not below) the true minimum vial spacing, or a
        single vial can be reported twice.
    param1 : int
        Upper Canny edge-detector threshold used internally by
        cv2.HoughCircles (the lower threshold is fixed at param1 / 2).
    param2 : int
        Accumulator vote threshold: how many edge pixels must "agree" on
        a circle for it to be reported. Lower = more detections (more
        false positives on belt texture/glare); higher = fewer, stricter
        detections (more missed vials, especially touching ones).
    blur_ksize : int
        Median blur kernel size applied before Hough, to suppress
        pixel-level sensor noise that would otherwise register as
        spurious edges.

    Returns
    -------
    list[tuple[int, int, int]]
        (x, y, radius) for each detected vial, in pixels.
    """
    blurred = cv2.medianBlur(gray_frame, blur_ksize)
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT, dp=1, minDist=min_dist,
        param1=param1, param2=param2, minRadius=min_radius, maxRadius=max_radius,
    )
    if circles is None:
        return []
    return [(int(x), int(y), int(r)) for x, y, r in np.round(circles[0]).astype(int)]


def annotate_frame(frame, detections):
    """Draw each detection's ring and center dot in-place, for quick visual QA."""
    for x, y, r in detections:
        cv2.circle(frame, (x, y), r, (0, 255, 0), 2)
        cv2.circle(frame, (x, y), 2, (0, 0, 255), -1)
    return frame


def process_video(in_path, out_path, **detect_kwargs):
    """Run detect_vials() over every frame of a video and write an
    annotated copy.

    This has no notion of object identity across frames -- every frame is
    detected independently, so the same physical vial has no guarantee of
    getting the same treatment from one frame to the next. Use
    vial_persistent_tracker.py when you need a stable ID per vial.
    """
    cap = cv2.VideoCapture(in_path)
    if not cap.isOpened():
        raise IOError(f"Could not open {in_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 10
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        detections = detect_vials(gray, **detect_kwargs)
        annotate_frame(frame, detections)
        writer.write(frame)
        frame_count += 1

    cap.release()
    writer.release()
    print(f"Processed {frame_count} frames -> {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--min-radius", type=int, default=8)
    parser.add_argument("--max-radius", type=int, default=35)
    parser.add_argument("--min-dist", type=int, default=18)
    parser.add_argument("--param1", type=int, default=60)
    parser.add_argument("--param2", type=int, default=22)
    args = parser.parse_args()
    process_video(
        args.input, args.output,
        min_radius=args.min_radius, max_radius=args.max_radius,
        min_dist=args.min_dist, param1=args.param1, param2=args.param2,
    )
