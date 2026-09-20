# Vial Tracking on Industrial Accumulator Table

Computer-vision pipeline that detects, tracks, and triages glass vials moving
across an accumulator table conveyor, reconstructed from two lost-source-code
video artifacts using OpenCV, and extended into a production-style tracking +
analytics pipeline.

![Persistent tracking with legible per-vial IDs and colors](docs/images/persistent_tracking_frame.png)

## Table of contents

- [Background](#background)
- [What's in this repo](#whats-in-this-repo)
- [How the original overlay was reverse-engineered](#how-the-original-overlay-was-reverse-engineered)
- [Pipeline architecture](#pipeline-architecture)
- [Installation](#installation)
- [Usage](#usage)
- [Detection algorithm comparison](#detection-algorithm-comparison-how-do-you-find-a-vial-in-a-frame)
- [Tracking algorithm comparison](#tracking-algorithm-comparison-how-do-you-keep-an-id-on-a-vial)
- [Post-tracking analytics](#post-tracking-analytics-from-a-csv-to-a-disposition-decision)
- [Industrial applications](#industrial-applications)
- [Camera & lighting hardware for this application](#camera--lighting-hardware-for-this-application)
- [Known limitations & future work](#known-limitations--future-work)
- [Repository structure](#repository-structure)
- [License](#license)

## Background

This project started from two video files and no source code:

| File | Contents |
|---|---|
| `pre_tracking_vials.avi` | Raw top-down camera feed of glass vials on an accumulator table conveyor. 1080x1080, 12 fps, 30 frames. |
| `post_tracking_vials.avi` | The same feed with a detection overlay (circles + ID labels) burned in. 1080x1080, 10 fps, 30 frames. |

The code that produced `post_tracking_vials.avi` was lost. Everything in
this repository was rebuilt from scratch by analyzing the two videos
pixel-by-pixel, reproducing the detection overlay, verifying the
reconstruction against the real footage, and then deliberately going
*beyond* what the original apparently did — because forensic analysis
turned up an important finding: **the original overlay was not actually
tracking anything.** See the next section for how that was established, and
[`vial_persistent_tracker.py`](vial_persistent_tracker.py) for the real
tracker built to replace it.

## What's in this repo

| File | Purpose |
|---|---|
| [`vial_detection.py`](vial_detection.py) | Per-frame vial **detection** only (Hough Circle Transform). Faithfully reproduces the look of the original, lost `post_tracking_vials.avi`, including its cosmetic, non-persistent random ID labels. |
| [`vial_persistent_tracker.py`](vial_persistent_tracker.py) | Real multi-object **tracking**: same detector, plus a centroid tracker that keeps a stable ID and a stable color on each vial across frames, and streams every observation to a CSV. |
| [`vial_analytics.py`](vial_analytics.py) | Post-processing on that CSV: throughput counts, jam/stall alerts, and a PASS / REVIEW / REJECT quality-triage disposition per vial, plus summary charts. |
| `pre_tracking_vials.avi`, `post_tracking_vials.avi` | The two original source videos this project was reconstructed from. |
| `docs/images/` | Reference screenshots used in this README. |

## How the original overlay was reverse-engineered

1. **Confirmed both videos share the same underlying footage.** Diffing
   non-overlay pixels between the first frame of each video gave a mean
   absolute difference of **1.9** (out of 255) — essentially just
   re-encoding noise. `post_tracking_vials.avi` is `pre_tracking_vials.avi`
   with graphics drawn on top, not a separately captured clip.
2. **Sampled the overlay's exact pixel colors.** Every ring pixel turned out
   to be pure `(random 15-255, 0, 0)` in BGR — a random *shade of blue only*
   — which is why some rings in the original footage look bright blue and
   others look almost black: same hue, different brightness. Center dots
   were fully random RGB.
3. **Read the ID label format directly off zoomed crops.** Labels like
   `772otw`, `999bcp`, and `4dar` decompose cleanly into an unpadded random
   integer (1-3 digits, no leading zeros) followed by exactly 3 random
   lowercase letters — i.e. `f"{random.randint(1,999)}{3 random letters}"`.
4. **Checked whether the label followed a given vial across frames — it does
   not.** Comparing consecutive frames, the same physical vial gets a
   completely different random label every frame. So despite the project
   being called "vial tracking," the original overlay only performed
   *detection* (find circles in this one frame) with a cosmetic label — it
   had no memory of "this is the same vial I saw a moment ago." This is why
   the repo contains both `vial_detection.py` (a faithful reproduction of
   that original, limited behavior) and `vial_persistent_tracker.py` (an
   upgrade with real object permanence).
5. **Validated the reconstruction visually.** Running `cv2.HoughCircles` on
   the real `pre_tracking_vials.avi` with tuned parameters and applying the
   overlay logic above produced an image that matches the real
   `post_tracking_vials.avi` almost pixel-for-pixel in style and detection
   coverage (including the same failure mode — missed detections in dense,
   touching vial clusters):

| Original (lost-code) output | This project's reconstruction |
|---|---|
| ![original post-tracking frame](docs/images/post_tracking_original.png) | ![reconstructed frame](docs/images/reconstruction_match.png) |

## Pipeline architecture

```mermaid
flowchart TD
    A[pre_tracking_vials.avi<br/>raw camera feed] --> B[Grayscale + median blur]
    B --> C{Detector}
    C -->|Hough Circle Transform<br/>vial_detection.detect_vials| D[per-frame circles<br/>x, y, radius]
    C -->|Distance transform + watershed<br/>detect_vials_watershed| D
    D --> E[CentroidTracker<br/>vial_persistent_tracker.py]
    E --> F[Annotated video<br/>stable ID + color per vial]
    E --> G[tracks.csv<br/>frame, time_sec, vial_id, x, y, radius]
    G --> H[vial_analytics.py]
    H --> I[vial_disposition.csv<br/>PASS / REVIEW / REJECT / EXCLUDED]
    H --> J[Jam / stall alerts]
    H --> K[Summary charts]
```

## Installation

```bash
python -m pip install opencv-python numpy scipy pandas matplotlib
```

Tested on Python 3.10 with `opencv-python 4.12`, `scipy 1.15`, `pandas 2.3`,
`matplotlib 3.10`.

## Usage

**1. Reproduce the original (detection-only, non-persistent) overlay:**

```bash
python vial_detection.py pre_tracking_vials.avi reconstructed_post.avi
```

**2. Run real persistent tracking (recommended for any actual use):**

```bash
python vial_persistent_tracker.py pre_tracking_vials.avi persistent_tracked.avi
# or, for heavily touching/overlapping vials:
python vial_persistent_tracker.py pre_tracking_vials.avi persistent_tracked.avi --watershed
```

This writes `persistent_tracked.avi` (annotated video) and
`persistent_tracked_tracks.csv` (raw per-frame tracking data).

**3. Turn that CSV into throughput / jam / quality-triage analytics:**

```bash
python vial_analytics.py persistent_tracked_tracks.csv --out-dir analytics_output
```

This writes `analytics_output/vial_disposition.csv`,
`analytics_output/disposition_breakdown.png`, and
`analytics_output/radius_distribution.png`, and prints an operator-readable
summary to the console.

## Detection algorithm comparison: how do you find a vial in a frame?

Vials seen top-down are circles, so this is fundamentally a round-object
detection problem — the same family of problem as counting coins, cells, or
bubbles. Several classical and modern techniques apply; this project
implements the first two and documents the rest for when you outgrow them.

| Method | How it works | Strengths | Weaknesses | Used here? |
|---|---|---|---|---|
| **Hough Circle Transform** (`vial_detection.py`) | Edge pixels vote for the circle centers/radii they're consistent with; peaks in the vote accumulator are reported as circles. | Simple, fast, no training data needed, works well on well-separated/isolated objects. Parameters map directly to physical vial size. | Vote strength depends on having enough visible edge arc — touching/overlapping vials (partial rim visible) are frequently missed. Sensitive to `param2` tuning; too loose = false positives on belt texture, too strict = missed vials. | **Yes**, default detector. |
| **Otsu threshold + distance transform + watershed** (`vial_persistent_tracker.py`, `--watershed`) | Binarize bright vials vs. dark background, then use the distance-to-background transform to find one seed per vial *even inside a fused blob*, and flood-fill outward from each seed until floods meet. | Specifically designed to split touching/overlapping round objects — the classic technique for the same problem in coin/cell counting. Recovers vials Hough misses in dense clusters. | Needs a foreground/background mask that separates cleanly (struggles under very uneven illumination unless you swap in adaptive thresholding). More parameters to tune (peak spacing, blur, morphology kernel). Slower per frame. | **Yes**, opt-in via `--watershed`. |
| **Contour detection + circularity filter** (`cv2.findContours` + `4*pi*area/perimeter^2` check) | Threshold, find each connected blob's outline, keep the ones whose shape is close enough to a circle. | Very simple to reason about and tune; gives you the actual blob mask (useful if you also want area/shape features, not just a circle fit). | Same touching-object weakness as Hough unless combined with watershed; circularity threshold is a blunt instrument compared to Hough's model-based voting. | No (subsumed by the watershed path, which already starts from a similar threshold step). |
| **`cv2.SimpleBlobDetector`** | Threshold at multiple levels, group stable blobs across those levels, filter by area/circularity/convexity/inertia. | Built into OpenCV, handles some brightness variation better than a single fixed threshold, easy blob-shape filtering knobs. | Tuning six-plus filter parameters is fiddly; still fundamentally a single-object-per-blob method, so touching vials remain a problem. | No. |
| **Template matching** | Slide a reference vial-rim image over the frame, score by normalized cross-correlation. | Trivial to implement; no calibration of geometric parameters needed if you have a good template. | Not rotation/scale invariant without generating many template variants; slow at high resolution; poor with partial occlusion — a bad fit for a dense, jumbled accumulator table. | No. |
| **Deep learning instance segmentation** (e.g. YOLOv8-seg, Mask R-CNN) | A CNN trained on labeled vial images directly predicts a mask/box per vial, learning what occlusion, glare, and clutter look like. | By far the most robust to touching/overlapping/partially-occluded vials, varying lighting, and even non-circular defects (a model can be trained to also flag chips/cracks directly). This is what real high-throughput inspection lines increasingly use. | Needs a labeled training set and a training/maintenance workflow; needs a GPU (or a well-optimized edge accelerator) to hit real-time frame rates; far more moving parts to deploy and validate than a parameter-tuned classical CV method. | No — out of scope for a from-two-videos reconstruction, but the natural next step for a real deployment; see [Known limitations](#known-limitations--future-work). |

**Practical takeaway:** start with Hough (fast, zero training data, easy to
reason about). If your accumulator table runs dense enough that vials
routinely touch — which the source footage in this repo does, in its
denser clusters — add the watershed path for those regions, or budget for a
trained segmentation model if missed/merged detections are costing you
real accuracy.

## Tracking algorithm comparison: how do you keep an ID on a vial?

Detecting circles frame-by-frame is necessary but not sufficient for
"tracking" — you also need to decide which circle in frame *N+1*
corresponds to which circle in frame *N*.

| Method | Idea | Strengths | Weaknesses | Used here? |
|---|---|---|---|---|
| **None (relabel every frame)** | What the original, lost code apparently did — assign a fresh random label to every detection, every frame. | Trivial to implement. | Not actually tracking: can't count unique objects, can't measure dwell time, can't detect a jam. This is the behavior `vial_detection.py` faithfully reproduces, for reference. | Yes, in `vial_detection.py` only (as a historical/compatibility reproduction). |
| **Centroid tracker (greedy nearest-neighbor)** | Match each existing track to the closest new detection within a distance gate; age out unmatched tracks; register unmatched detections as new tracks. | Simple, fast, no extra dependencies, easy to understand and debug. Works well when objects move slowly relative to the frame rate (true here — this table moves vials slowly). | Greedy matching isn't globally optimal — can swap identities between two vials that pass close together. No motion model, so a brief full occlusion (more frames missed than `max_disappeared`) permanently loses the ID. | **Yes**, `CentroidTracker` in `vial_persistent_tracker.py`. |
| **Hungarian-algorithm matching** (`scipy.optimize.linear_sum_assignment`) | Same idea as the centroid tracker, but solves the assignment problem exactly instead of greedily. | Globally optimal match for a given frame — removes the identity-swap failure mode of greedy matching, same distance-only cost model otherwise. | Still no motion prediction, so long occlusions still break tracks. Marginally more compute (still trivial at this scale). | No — noted as the first upgrade to make if ID swaps are observed; the swap-in point is clearly marked in `CentroidTracker.update()`. |
| **Kalman filter per track + Hungarian matching (SORT)** | Each track predicts its next position (constant-velocity model) before matching, so matching is done against *predicted* position, not last-seen position, and a track can survive a few frames of no detection while still "believing" where the object should be. | Handles brief occlusions and faster motion much better than a bare centroid tracker; industry-standard baseline for real-time MOT. | More code/state per track; still no appearance model, so it can still swap identities between two similar, closely-spaced objects if their motion is ambiguous. | No — natural next upgrade for a faster or more crowded line; see [Known limitations](#known-limitations--future-work). |
| **DeepSORT / ByteTrack (appearance + motion)** | Adds a learned appearance embedding per detection, so matching considers "does this look like the same vial" as well as "is this where I predicted it to be." | Most robust to occlusion and crowding; the standard choice for dense, fast real-world multi-object tracking (retail, traffic, sports analytics). | Needs a feature-extraction model (more compute, another dependency), and identical glass vials give a much weaker appearance signal than, say, distinct people or vehicles — the benefit over motion-only SORT is smaller for this specific object type. | No — likely overkill for this object type/line speed; listed for completeness. |

**Practical takeaway:** a plain centroid tracker is a reasonable, honest
baseline for a slow accumulator table, which is why it's what's implemented
here — but it is *not* the last word for a faster or denser line. The
upgrade path (Hungarian matching, then a Kalman filter/SORT) is
incremental, is called out directly in the `CentroidTracker` docstring, and
doesn't require throwing away the detector or the CSV schema.

## Post-tracking analytics: from a CSV to a disposition decision

`vial_persistent_tracker.py` writes one row per `(frame, vial)` observation:

```
frame,time_sec,vial_id,x,y,radius
0,0.0,0,547,191,27
0,0.0,1,511,401,29
...
```

`vial_analytics.py` turns that raw telemetry into three things a line
operator actually acts on:

**1. Throughput.** Group by `vial_id` to get a total distinct-vial count and
per-vial dwell time in frame — the basic "how many vials, how fast" metric.

**2. Jam / stall alerts (a process signal, not a quality signal).** A vial
whose total *path length* (sum of frame-to-frame movement, not net
start-to-end displacement — see the docstring for why that distinction
matters) stays near zero over many consecutive frames is very likely
physically stuck. This is reported separately from product-quality
disposition below, because a jam is a line-mechanics problem, not a defect
in the vial itself. The output includes the jammed vial's last known
`(x, y)`, so an operator knows where to look.

**3. Quality disposition (PASS / REVIEW / REJECT).** Using only the
geometry the tracker measured — a vial's own rim radius consistency across
its track, and how its average radius compares to the rest of the batch —
each vial is classified as:

- **PASS** — nothing geometrically unusual.
- **REVIEW** — one anomaly flag tripped (unusual size vs. the batch, an
  unstable/wobbly radius reading across its own track, or a high rate of
  "invisible for a frame then re-detected"). Route to secondary/manual
  inspection.
- **REJECT** — *two* independent anomaly flags agree (unusual size **and**
  an unstable rim). Divert before the vial reaches downstream
  filling/labeling.
- **EXCLUDED** — track too short to trust (almost certainly a detector
  blip, not a real vial); not counted as a quality judgment either way.

```bash
python vial_analytics.py persistent_tracked_tracks.csv --out-dir analytics_output
```

```
Total distinct vial tracks : 280
  PASS      : 162
  REVIEW    : 116  (route to secondary/manual inspection)
  REJECT    : 2    (divert before downstream filling/labeling)
  EXCLUDED  : 0    (too few frames to trust -- detector noise)
Population rim radius       : mean=23.58px, std=3.69px
Average dwell time in frame : 1.26s

JAM ALERTS (57 vials barely moved while tracked -- possible physical jam on the table)
```

![Disposition breakdown](docs/images/disposition_breakdown.png)
![Radius distribution with the size-anomaly band shaded](docs/images/radius_distribution.png)

> **On that 57-vial jam-alert count:** an accumulator table's entire job is
> to *buffer* vials in a holding pattern before the next machine pulls them
> in, so a lot of near-zero movement in any short clip is expected, normal
> behavior, not evidence of 57 real jams. The 30-frame (~2.5s) sample clip
> in this repo is too short to tell "normal buffering" apart from "actually
> stuck" — on a real line, tune `--jam-min-frames` / `--jam-max-path-px`
> against several *minutes* of footage, where a truly jammed vial (stuck for
> tens of seconds) stands out from vials cycling through the buffer in the
> ordinary way.

> **On what "quality disposition" does and doesn't mean here:** this
> pipeline sees one thing — a circle's position and radius from a single
> top-down camera. That genuinely can hint at a chipped/broken rim
> (SIZE_ANOMALY, UNSTABLE_RIM) or a wrong-SKU vial mixed into the batch, but
> it **cannot** see cracks that don't change the outer silhouette, cloudy or
> discolored glass, foreign particulate in the fill, fill-level, or
> stopper/cap seating — those need dedicated imaging (raking/dark-field
> light for surface defects, particulate-tuned backlighting, a fill-level
> line-scan camera) and typically a trained defect classifier, not raw
> circle geometry. **Treat this disposition as a triage signal** — "worth a
> second look" vs. "nothing geometrically unusual" — not a certified
> pass/fail, especially in a regulated environment like pharmaceutical vial
> filling.

**Extending this to real defect detection.** The CSV already has everything
needed to plug in genuine defect features: for every `(frame, vial_id, x, y,
radius)` row, crop that region out of the corresponding source frame, run
the crop through a trained defect classifier (chip/crack/discoloration/etc.
— e.g. a small CNN fine-tuned on a labeled defect dataset), and merge the
resulting `defect_score` column into `classify_vials()` in
`vial_analytics.py` alongside the existing geometric flags. The
PASS/REVIEW/REJECT routing logic doesn't need to change — only the signals
feeding it.

## Industrial applications

Round-object detection + tracking + count/triage on a conveyor or
accumulator table is a common building block well beyond this one clip:

- **Pharmaceutical vial/ampoule filling lines.** Accumulator tables are a
  standard buffer stage between filling/stoppering and downstream
  capping/inspection/labeling machines. Vision at this stage is used for
  throughput counting, jam detection (a stalled accumulator table can back
  up or crash an upstream filler), and early triage before a vial reaches a
  certified visual-inspection station. This is a validated-process,
  regulated environment (cGMP, 21 CFR Part 211) where visible-particulate
  and container/closure integrity inspection follow standards like USP
  &lt;790&gt;/&lt;1790&gt; — worth knowing as context for why this repo is
  explicit that its disposition logic is a triage aid, not a certified
  inspection system.
- **Beverage / cosmetics / food bottling and jarring lines.** The same
  top-down, backlit, round-container counting problem applies directly to
  bottles, jars, and cans on accumulation tables and turntables.
- **Discrete-parts counting on general conveyors.** Any process that needs
  "how many parts passed" or "is anything stuck" — including non-round
  parts, once you swap the detector for one suited to that shape — reuses
  the same detect → track → analyze skeleton in this repo.
- **Semiconductor wafer/die and small-parts counting.** Structurally the
  same problem (many small, roughly uniform round/rectangular objects,
  need an accurate count and outlier flags) at a different physical scale.
- **Line monitoring / OEE (Overall Equipment Effectiveness) integration.**
  The throughput and jam-alert outputs here are exactly the kind of signal
  that feeds an OEE dashboard or a SCADA/MES alarm — see the
  connectivity notes in the next section.

## Camera & lighting hardware for this application

The source footage in this repo is monochrome, high-contrast, and clearly
**backlit** (vial rims read as bright rings against a darker, evenly-lit
background — that's precisely the illumination style that makes Hough
Circle Transform and Otsu thresholding work well with minimal tuning). If
you're specifying camera hardware for a real deployment of this kind of
system, here's what matters and why:

### Interface / bus standard

| Standard | Typical use | Notes |
|---|---|---|
| **GigE Vision** | Most common choice for fixed inspection stations. | Cable runs up to ~100m without a repeater, standard Ethernet infrastructure, easy to integrate with PLC networks; bandwidth (~1 Gbps, or 5/10 GigE variants for higher throughput) can bottleneck very high frame-rate/resolution setups. |
| **USB3 Vision** | Compact setups, shorter cable runs (~a few meters without an active extender). | Very high bandwidth, low latency, lower cost, but less common in a cabinet-to-camera-far-away layout on a large machine. |
| **CoaXPress** | High-speed / high-resolution line-scan or very fast area-scan applications. | Long cable runs at very high bandwidth over coax; higher cost, more specialized frame-grabber hardware. |

A 1080x1080-class monochrome area-scan camera at 10-30 fps (roughly what
this project's source footage looks like) comfortably fits well within
GigE or USB3 bandwidth — no need for CoaXPress at this scale unless line
speed increases substantially.

### Shutter type: global, not rolling

**Global shutter is a hard requirement**, not a nice-to-have, for vials
moving on a conveyor: a rolling shutter exposes each row of the sensor at a
slightly different instant, which skews/smears a moving round rim into an
egg shape and directly corrupts the radius measurements this whole pipeline
depends on. Any industrial camera marketed for machine vision defaults to
global shutter; just make sure a candidate sensor is explicitly specified
as such.

### Monochrome vs. color

**Monochrome is the right choice here**, matching the source footage. A
monochrome sensor has no Bayer color filter array, so it has higher
effective spatial resolution and better light sensitivity per pixel than a
color sensor of the same physical resolution — and color information isn't
useful for detecting a clear-glass rim's silhouette against a backlight
anyway. Reserve color for a downstream station that specifically needs to
judge liquid color/clarity or a printed label.

### Lens: consider a telecentric lens

A standard fixed-focal-length lens has perspective error: an object's
apparent size and center position shift slightly depending on its exact
height and its position relative to the lens's optical axis. For a system
whose whole output is "this vial's radius," that error directly becomes
noise in the SIZE_ANOMALY signal in `vial_analytics.py`. A **telecentric
lens** (common in machine vision metrology) keeps magnification constant
regardless of object distance/position within its working range, which is
exactly what you want when the measured quantity *is* the size. It costs
more and has a fixed working distance/field of view, so it's a
deliberate trade — recommended if disposition decisions in
production actually hinge on precise size measurement; a standard lens is
fine if the vision system is mainly doing presence/position/counting.

### Illumination

| Style | What it's good for | Relevant here? |
|---|---|---|
| **Backlighting** (light source behind/below the object, camera looking through it) | Crisp, high-contrast silhouettes — exactly what this repo's source footage shows, and what makes simple thresholding/Hough work well. | Yes — matches the existing footage and pipeline. |
| **Diffuse dome / ring lighting** (even illumination from many angles) | Reduces glare/hot-spots on curved glass; better for seeing surface features (labels, fill level) than a pure silhouette. | Complementary — useful if you add a defect-detection station downstream. |
| **Coaxial / dark-field lighting** | Makes surface defects (scratches, chips) stand out via how they scatter light differently than an intact surface. | Needed if you extend to real optical defect detection (see the analytics section above). |
| **Polarized lighting/filters** | Cuts specular glare/reflections off curved glass, which otherwise show up as spurious bright spots a naive detector can mistake for edges. | Worth adding if glare is causing false detections. |
| **Strobed/pulsed illumination synced to camera exposure** | Freezes motion with a very short effective exposure without needing a very fast (noisy) shutter speed. | Worth it if line speed increases and standard exposure starts showing motion blur. |

### Example industrial camera families (for specification purposes)

- **Basler ace2 / boost** (GigE / USB3, global shutter monochrome variants)
- **Teledyne FLIR Blackfly S** (GigE / USB3)
- **Teledyne Dalsa Genie Nano**
- **Keyence CV-X / XG series** (very common in pharma/vial visual-inspection
  systems specifically; typically sold as a full smart-camera + lighting +
  software package)
- **Cognex In-Sight** (smart camera — onboard processing, good fit if you
  want detection logic to live on the camera itself rather than a separate
  PC)
- **IDS uEye / Allied Vision Alvium** (compact, cost-effective options for
  smaller integrations)

**Smart camera vs. PC + frame grabber:** a smart camera (Cognex In-Sight,
Keyence CV-X) runs detection logic on the camera itself and outputs
results/alarms directly, which simplifies integration but limits you to
that vendor's software environment. A standard industrial camera feeding an
industrial PC (or an edge device like an **NVIDIA Jetson** for on-site GPU
inference) gives you the flexibility this repo assumes — full Python/OpenCV
control, easy to extend with a custom trained model later — at the cost of
managing that PC/edge box yourself.

### Environment & integration

- **IP67 / washdown-rated housings** if the camera is anywhere near a
  cleanroom washdown or wet-clean process, common in pharma/food/beverage
  filling areas.
- **Hardware trigger from the line's PLC** (rather than free-running or
  software-triggered capture) minimizes frame-to-frame timing jitter,
  which matters once you're measuring motion (path length, dwell time) as
  precisely as this project's analytics does.
- **OPC-UA or MQTT** as the integration layer to push throughput counts,
  jam alerts, and disposition summaries from `vial_analytics.py` into a
  plant's MES/SCADA/OEE system, rather than treating this as a standalone
  offline tool.

## Known limitations & future work

- **Detection:** Hough Circle Transform misses vials in dense, heavily
  touching clusters (visible in this repo's own sample footage); the
  watershed alternative recovers more of them but needs illumination
  tuning of its own. A trained segmentation model is the most robust fix,
  at the cost of needing labeled training data.
- **Tracking:** `CentroidTracker` uses greedy nearest-neighbor matching
  with no motion model, so it can swap IDs between close, similarly-moving
  vials and permanently loses a track after `max_disappeared` consecutive
  missed frames (no recovery from a longer occlusion). See the
  [tracking comparison](#tracking-algorithm-comparison-how-do-you-keep-an-id-on-a-vial)
  table for the concrete upgrade path (Hungarian matching, then a Kalman
  filter/SORT).
- **Analytics/disposition:** built entirely from tracked circle geometry —
  it is a triage signal, not a certified defect-inspection system. See the
  "what quality disposition does and doesn't mean" callout above and the
  extension path to a real trained defect classifier.
- **Jam-alert thresholds** were tuned by eye against one ~2.5 second sample
  clip and should be re-tuned against real, longer footage before being
  trusted operationally (see the jam-alert callout above).
- **Camera assumptions:** the whole pipeline assumes a fixed, top-down,
  backlit, global-shutter monochrome camera. A different camera geometry
  or lighting style will need re-tuned (or different) detection parameters.

## Repository structure

```
.
├── vial_detection.py              # Hough-based per-frame detection (reproduces the original overlay)
├── vial_persistent_tracker.py     # Real multi-object tracking + CSV export
├── vial_analytics.py              # CSV -> throughput / jam alerts / quality disposition + charts
├── pre_tracking_vials.avi         # Original raw source footage
├── post_tracking_vials.avi        # Original (lost-code) detection-overlay footage
└── docs/
    └── images/                    # Screenshots used in this README
```

Running the scripts (see [Usage](#usage)) will also produce, alongside the
originals: `reconstructed_post.avi`, `persistent_tracked.avi` (+ its
`_tracks.csv`), `persistent_tracked_watershed.avi` (+ its `_tracks.csv`),
and an `analytics_output/` directory.

## License

MIT



---


### Thank you for reading

#### Please consider giving a star if you find the repo useful. Thank you.

---

### **AUTHOR'S BACKGROUND**
### Author's Name:  Emmanuel Oyekanlu
```
Skillset:   I have experience spanning several years in data science, enterprise AI architecture and solutions, developing scalable enterprise data pipelines,
enterprise solution architecture, architecting enterprise systems data and AI applications,
software and AI solution design and deployments, data engineering, industrial intelligent vision systems, high performance computing (GPU, CUDA), machine learning,
NLP, Agentic-AI and LLM applications as well as deploying scalable solutions (apps) on-prem and in the cloud.

I can be reached through: manuelbomi@yahoo.com

Publications:  https://scholar.google.com/citations?user=S-jTMfkAAAAJ&hl=en
LinkedIn:  https://www.linkedin.com/in/emmanuel-oyekanlu-6ba98616
Github:  https://github.com/manuelbomi

```
[![Icons](https://skillicons.dev/icons?i=aws,azure,gcp,scala,mongodb,redis,cassandra,kafka,anaconda,matlab,nodejs,django,py,c,anaconda,git,github,mysql,docker,kubernetes&theme=dark)](https://skillicons.dev)



