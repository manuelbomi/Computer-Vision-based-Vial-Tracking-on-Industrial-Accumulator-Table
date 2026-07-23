"""
vial_persistent_tracker.py
===========================
------------------------------------------
  1. CentroidTracker below assigns each vial an integer ID *once*, then
     re-uses that same ID for as long as it can keep matching that vial
     from frame to frame (based on how close its new detected position is
     to its last known position).
  2. Each ID gets a deterministic display color (color_for_id) instead of a
     random one, so the same vial is drawn in the same color in every
     frame -- you can visually follow one vial through the whole clip.
  3. Every (frame, vial_id, x, y, radius) observation is written to a CSV
     file as it happens. That CSV is the raw material for all of the
     downstream analytics in vial_analytics.py (defect flags, jam
     detection, throughput counts, etc.) -- see that file and the README
     for how it gets used.

DETECTION BACKENDS
--------------------
Two interchangeable detectors are provided; both return the same
list[(x, y, radius)] shape so the tracker doesn't care which one produced
them:

  detect_vials()          
                             Hough Circle Transform. Fast, simple, works
                             well on isolated/well-separated vials. Tends
                             to miss vials that are touching or heavily
                             overlapping (their rim only shows a partial
                             arc, which weakens the Hough vote).

  detect_vials_watershed()  (defined below)
                             Distance-transform + marker-controlled
                             watershed segmentation. Slower and needs more
                             tuning, but recovers touching/clustered vials
                             that Hough misses, by finding one seed point
                             per vial *inside* a merged blob and letting
                             each seed "claim" its own territory.

Select the backend with the --watershed CLI flag.

LIMITATIONS OF THE TRACKER (be aware of these before relying on it)
-----------------------------------------------------------------------
CentroidTracker is intentionally the simplest correct multi-object tracker:
nearest-centroid matching with a distance gate. It has no motion model, so
it will struggle with:
  - Fast-moving vials where the frame-to-frame displacement approaches
    max_distance (it may swap identities between two vials passing close
    together).
  - Long occlusions: an ID is permanently retired after max_disappeared
    consecutive missed frames, and a re-appearing vial gets a brand-new ID
    rather than recovering its old one.
For a busier or faster line, upgrade the matching step to the Hungarian
algorithm (scipy.optimize.linear_sum_assignment gives an exact optimal
assignment instead of this file's greedy nearest-neighbor loop) and/or add
a Kalman filter per track to predict where a vial *should* be next frame
even through a brief occlusion -- that combination is essentially the
classic SORT algorithm. See the README's algorithm-comparison section.
"""

import argparse
import csv
import os
from collections import OrderedDict

import cv2
import numpy as np
from scipy import ndimage as ndi

from vial_detection import detect_vials


def color_for_id(object_id):
    """Map a track ID to a stable, visually-distinct BGR color.

    The color is a pure function of object_id (no randomness, no stored
    state), so the SAME vial ID is always drawn in the SAME color on every
    frame it appears in -- that's what lets you visually follow one vial
    across the whole clip.

    Implementation: walk the HSV hue wheel (0-179 in OpenCV) in steps of 47.
    47 was picked because gcd(47, 180) == 1, so consecutive integer ids
    (0, 1, 2, 3...) land on hues that are spread far apart around the wheel
    instead of drifting slowly through neighboring shades -- important
    because dozens of vials can be on screen at once and near-identical
    colors on adjacent vials would defeat the purpose. Saturation/value are
    fixed high (220, 255) so every color stays bright and easy to read
    against the gray conveyor belt.
    """
    hue = (object_id * 47) % 180
    hsv_pixel = np.uint8([[[hue, 220, 255]]])
    bgr_pixel = cv2.cvtColor(hsv_pixel, cv2.COLOR_HSV2BGR)[0][0]
    return tuple(int(c) for c in bgr_pixel)


class CentroidTracker:
    """Minimal multi-object tracker: match new detections to existing tracks
    by nearest centroid distance, frame over frame.

    This is the standard "centroid tracking" recipe (popularized by
    pyimagesearch's OpenCV tutorials): it does not use appearance/shape
    information at all, only (x, y) position, and it assumes an object
    can't move farther than `max_distance` pixels between two consecutive
    frames. That assumption is reasonable here because the accumulator
    table moves vials slowly and the camera runs at ~10-12 fps.

    Parameters
    ----------
    max_disappeared : int
        How many consecutive frames a track is allowed to go undetected
        (e.g. briefly occluded by a neighboring vial, or missed by a
        marginal Hough vote) before its ID is retired for good.
    max_distance : int
        Maximum allowed pixel distance between an existing track's last
        known position and a new detection for them to be considered the
        same physical vial. Set this a bit larger than the typical
        frame-to-frame motion of a vial, but smaller than the typical
        spacing between two different vials -- otherwise identities can
        swap between neighbors.
    """

    def __init__(self, max_disappeared=5, max_distance=40):
        self.next_id = 0
        self.objects = OrderedDict()      # id -> (x, y, r) most recent detection
        self.disappeared = OrderedDict()  # id -> consecutive frames since last matched
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance

    def register(self, centroid):
        """Start tracking a brand-new object and hand it the next free ID."""
        self.objects[self.next_id] = centroid
        self.disappeared[self.next_id] = 0
        self.next_id += 1

    def deregister(self, object_id):
        """Stop tracking an object permanently (its ID is never re-used)."""
        del self.objects[object_id]
        del self.disappeared[object_id]

    def update(self, detections):
        """Advance the tracker by one frame.

        Parameters
        ----------
        detections : list[tuple[int, int, int]]
            (x, y, radius) tuples for everything detected in the current
            frame, e.g. the output of detect_vials().

        Returns
        -------
        OrderedDict[int, tuple[int, int, int]]
            The current set of live track IDs mapped to their (x, y, radius)
            in this frame. This is exactly self.objects.
        """
        # Case 1: nothing was detected this frame at all. Every existing
        # track just becomes one frame "older" without a match; anything
        # that's been missing too long gets dropped.
        if len(detections) == 0:
            for object_id in list(self.disappeared.keys()):
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)
            return self.objects

        # Case 2: we have detections but no existing tracks (e.g. the very
        # first frame). Every detection becomes a brand-new track.
        if len(self.objects) == 0:
            for det in detections:
                self.register(det)
            return self.objects

        # Case 3: the general case -- match existing tracks to this frame's
        # detections. Build an (existing_tracks x new_detections) matrix of
        # Euclidean distances between every pair, using only the (x, y)
        # center -- radius is tracked but not used for matching.
        object_ids = list(self.objects.keys())
        object_centroids = np.array([o[:2] for o in self.objects.values()])
        input_centroids = np.array([d[:2] for d in detections])

        dist_matrix = np.linalg.norm(
            object_centroids[:, None, :] - input_centroids[None, :, :], axis=2
        )

        # Greedy nearest-neighbor matching: for each existing track, find
        # its closest detection, and process tracks in order of "how
        # confident" that closest match is (smallest minimum distance
        # first). This is a greedy approximation of the optimal assignment
        # problem -- fast and good enough at this vial density/speed, but
        # NOT guaranteed globally optimal. If you see ID swaps between
        # nearby vials, replace this with
        # scipy.optimize.linear_sum_assignment(dist_matrix) for the exact
        # optimal (Hungarian algorithm) matching.
        rows = dist_matrix.min(axis=1).argsort()
        cols = dist_matrix.argmin(axis=1)[rows]

        used_rows, used_cols = set(), set()
        for row, col in zip(rows, cols):
            # Each existing track and each new detection can only be used
            # in one match; skip anything already claimed this frame.
            if row in used_rows or col in used_cols:
                continue
            # Reject matches that are too far apart to plausibly be the
            # same physical vial -- better to start a new track than to
            # silently jump an ID to an unrelated vial.
            if dist_matrix[row, col] > self.max_distance:
                continue
            object_id = object_ids[row]
            self.objects[object_id] = detections[col]
            self.disappeared[object_id] = 0
            used_rows.add(row)
            used_cols.add(col)

        # Existing tracks that found no acceptable match this frame: age
        # them, and retire them if they've been gone too long.
        unused_rows = set(range(dist_matrix.shape[0])) - used_rows
        for row in unused_rows:
            object_id = object_ids[row]
            self.disappeared[object_id] += 1
            if self.disappeared[object_id] > self.max_disappeared:
                self.deregister(object_id)

        # Detections that matched no existing track: treat as newly
        # appeared vials (e.g. just entered the frame, or a re-appearance
        # after too long an occlusion) and register them as new IDs.
        unused_cols = set(range(dist_matrix.shape[1])) - used_cols
        for col in unused_cols:
            self.register(detections[col])

        return self.objects


def detect_vials_watershed(gray_frame, min_radius=8, max_radius=35, min_peak_distance=14):
    """Alternative detector for touching/overlapping vials.

    Hough Circle Transform (detect_vials in vial_detection.py) votes based
    on edge-pixel geometry, so a vial whose rim is mostly hidden behind its
    neighbors (only a small arc of edge is visible) often fails to
    accumulate enough votes and gets missed entirely. This function takes a
    different approach that's specifically good at splitting up *touching*
    round objects -- the classic technique used for separating touching
    coins/cells/bubbles in an image:

    Step-by-step:
      1. Otsu threshold -> a binary mask of "vial" (bright) vs "conveyor
         belt background" (dark). Otsu automatically picks the threshold
         value that best separates the image's two intensity populations,
         so we don't have to hardcode a brightness cutoff.
      2. Morphological opening -> erode-then-dilate to remove small noise
         specks from the mask without shrinking the vial blobs overall.
      3. Distance transform -> for every foreground (vial) pixel, compute
         its distance to the nearest background pixel. Pixels deep in the
         middle of a single vial score highest; pixels near a rim or near
         the touching-point between two vials score low. This turns each
         blob into a little "hill" per vial, even when several vials are
         fused into one connected blob in the binary mask.
      4. Local maxima of that distance transform = one seed point per vial
         (found with a maximum filter: a pixel is a peak if it's the
         largest value in its own neighborhood). This is what lets two
         touching vials -- which formed a *single* connected blob in step 1
         -- still produce two separate seeds here, because each vial's
         "hill" has its own peak.
      5. Marker-controlled watershed (cv2.watershed) floods outward from
         each seed and stops where two floods meet, carving the original
         merged blob into one region per vial along the natural boundary
         between them.
      6. Fit a minimum enclosing circle to each resulting region and keep
         it only if its radius falls in the expected [min_radius,
         max_radius] range (filters out watershed slivers/artifacts).

    Tuning notes:
      - min_peak_distance should be roughly the minimum expected
        center-to-center spacing between two real, distinct vials -- too
        small and one vial can produce two seeds (over-segmentation); too
        large and two touching vials can collapse back into one seed.
      - This function uses a single global Otsu threshold, which assumes
        fairly even lighting across the frame. If your camera setup has
        strong vignetting or uneven illumination (dimmer at frame edges),
        swap step 1 for `cv2.adaptiveThreshold` instead, which computes a
        local threshold per image region.
    """
    _, thresh = cv2.threshold(gray_frame, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = np.ones((3, 3), np.uint8)
    opened = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=2)

    dist = cv2.distanceTransform(opened, cv2.DIST_L2, 5)

    # A pixel is a "peak" if it equals the max value in its own
    # min_peak_distance-sized neighborhood (i.e. nothing nearby is higher).
    # The extra mean-based threshold discards tiny, noisy peaks that sit on
    # the background or on thin slivers of foreground, keeping only peaks
    # that plausibly sit near the center of an actual vial.
    local_max = ndi.maximum_filter(dist, size=min_peak_distance) == dist
    if np.any(opened):
        local_max &= dist > 0.3 * dist[opened > 0].mean()
    else:
        local_max &= False
    peak_labels, _ = ndi.label(local_max)

    # Build the marker image cv2.watershed expects:
    #   0        = unknown territory, to be flooded/assigned by watershed
    #   1        = sure background (everything outside the vial mask)
    #   2..N+1   = one distinct seed label per detected vial peak
    # NOTE: it is important that "unknown" foreground pixels (inside a
    # vial blob, but not exactly on a peak) are left at 0, NOT lumped in
    # with the background label -- otherwise watershed has nothing left to
    # flood and every vial's interior gets swallowed by the background
    # region instead of being carved up per-seed.
    markers = np.zeros_like(dist, dtype=np.int32)
    markers[opened == 0] = 1
    markers[peak_labels > 0] = peak_labels[peak_labels > 0] + 1

    # cv2.watershed needs a 3-channel image to compute gradients from, even
    # though our source is grayscale.
    color = cv2.cvtColor(gray_frame, cv2.COLOR_GRAY2BGR)
    markers = cv2.watershed(color, markers)

    detections = []
    for label in np.unique(markers):
        # label -1 is the watershed boundary lines themselves, label 1 is
        # the sure-background region -- neither is a vial.
        if label <= 1:
            continue
        mask = np.uint8(markers == label)
        points = cv2.findNonZero(mask)
        if points is None:
            continue
        (x, y), r = cv2.minEnclosingCircle(points)
        if min_radius <= r <= max_radius:
            detections.append((int(x), int(y), int(r)))
    return detections


def draw_track(frame, object_id, x, y, r):
    """Draw one tracked vial's ring and a legible ID label on `frame`.

    The label gets a solid black backing rectangle behind the text (sized
    exactly to the text with a small margin via cv2.getTextSize) so it
    stays readable regardless of what's directly behind it in the image --
    plain colored text alone tended to disappear against the gray,
    textured conveyor belt or against bright vial reflections.
    """
    color = color_for_id(object_id)
    cv2.circle(frame, (x, y), r, color, 2)

    label = f"ID {object_id}"
    font, scale, thickness = cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
    (tw, th), baseline = cv2.getTextSize(label, font, scale, thickness)
    tx, ty = x - tw // 2, y - r - 10

    cv2.rectangle(frame, (tx - 4, ty - th - 4), (tx + tw + 4, ty + baseline + 2),
                  (0, 0, 0), -1)
    cv2.putText(frame, label, (tx, ty), font, scale, color, thickness, cv2.LINE_AA)


def process_video(in_path, out_path, use_watershed=False, csv_path=None):
    """Run detection + tracking over every frame of a video file, writing
    both an annotated video and a per-frame tracking-data CSV.

    Parameters
    ----------
    in_path : str
        Source video (e.g. pre_tracking_vials.avi).
    out_path : str
        Where to write the annotated output video.
    use_watershed : bool
        If True, use detect_vials_watershed() instead of the default
        Hough-based detect_vials().
    csv_path : str or None
        Where to write the tracking-data CSV. Defaults to
        "<out_path without extension>_tracks.csv".

    The CSV has one row per (frame, vial) observation:
        frame, time_sec, vial_id, x, y, radius
    This "long format" (one row per observation rather than one row per
    vial) is what pandas groupby()/plotting expects, and is what
    vial_analytics.py consumes to compute per-vial trajectories, dwell
    times, and defect/disposition flags after the fact.
    """
    cap = cv2.VideoCapture(in_path)
    if not cap.isOpened():
        raise IOError(f"Could not open {in_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 10
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*'MJPG'), fps, (w, h))

    if csv_path is None:
        csv_path = os.path.splitext(out_path)[0] + "_tracks.csv"
    csv_file = open(csv_path, "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["frame", "time_sec", "vial_id", "x", "y", "radius"])

    tracker = CentroidTracker(max_disappeared=5, max_distance=40)
    total_ever_seen = set()  # every ID that was ever registered, for a running count
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        detections = detect_vials_watershed(gray) if use_watershed else detect_vials(gray)

        objects = tracker.update(detections)
        total_ever_seen.update(objects.keys())

        for object_id, (x, y, r) in objects.items():
            draw_track(frame, object_id, x, y, r)
            csv_writer.writerow([frame_idx, round(frame_idx / fps, 3), object_id, x, y, r])

        cv2.putText(frame, f"Total vials seen: {len(total_ever_seen)}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2, cv2.LINE_AA)

        writer.write(frame)
        frame_idx += 1

    cap.release()
    writer.release()
    csv_file.close()
    print(f"Total distinct vials tracked: {len(total_ever_seen)} -> {out_path}")
    print(f"Per-frame tracking data -> {csv_path}")


if __name__ == "__main__":
    # Command-line entry point, e.g.:
    #   python vial_persistent_tracker.py pre_tracking_vials.avi persistent_tracked.avi
    #   python vial_persistent_tracker.py pre_tracking_vials.avi out.avi --watershed --csv tracks.csv
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--watershed", action="store_true",
                         help="Use watershed segmentation instead of Hough circles")
    parser.add_argument("--csv", default=None,
                         help="Path to write per-frame tracking data (default: <output>_tracks.csv)")
    args = parser.parse_args()
    process_video(args.input, args.output, use_watershed=args.watershed, csv_path=args.csv)
