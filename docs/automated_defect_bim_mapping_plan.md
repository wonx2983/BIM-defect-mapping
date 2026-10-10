# Automated Mapping of Detected Concrete Defects onto BIM Elements

## Complete Implementation Plan

**Author:** Krishan Jangir, Department of Civil Engineering, IIT Delhi **Supervisor:** Prof. Sahil Garg **Scope:** This plan covers the defect-to-BIM mapping subsystem only. Real-time CCTV ingestion and defect detection (YOLOv11 inference on RTSP streams) are developed separately within the project team. Everything from the point a defect is detected onward, locating it on the correct BIM element, recording it, and resolving conflicts between cameras, is covered here in full implementation detail.

---

## Executive Summary

This subsystem receives a defect detection (class, confidence, camera ID, pixel location, timestamp) and automatically determines which BIM element the defect belongs to, identified by its permanent GlobalId (GUID). It does this without manual effort per camera or per detection, in two stages:

1. **One-time camera calibration**, using a printed fiducial marker whose reference position is drawn directly from coordinates already present in the BIM. This replaces manual point-and-click calibration, which does not scale to a real site with many cameras.
2. **Per-detection raycasting**, which converts a defect's pixel location into a 3D ray using the calibrated camera pose, tests that ray only against the small set of BIM elements the camera can plausibly see, and resolves the nearest intersection as the answer.

The mapped defect is then de-duplicated against existing records and written back into the BIM itself, as a Property Set entry or a BCF (BIM Collaboration Format) topic, rather than into a disconnected external database.

To the best of our knowledge, this specific combination, automatic BIM-anchored marker calibration plus candidate-set-restricted raycasting, applied to concrete defect localization, has not been described in the published literature reviewed. Each individual technique is independently established; Section 6 and Section 7 document exactly what is established versus what appears to be the gap.

---

## 1. Problem Statement

### 1.1 What this subsystem must solve

Given a single defect detection, the subsystem must answer one question precisely: **which BIM element, identified by its GUID, does this defect belong to?** The input contract from the upstream detection subsystem is:

| Field | Description |
| --- | --- |
| `class` | Defect type (crack, honeycombing, scaling, etc.) |
| `confidence` | Detection confidence score |
| `camera_id` | Which camera produced this detection |
| `pixel_location` | Bounding box or mask centroid, in pixel coordinates |
| `timestamp` | When the frame was captured |

The output is a defect record permanently tied to one BIM element, not a loose coordinate or a free-text location description.

### 1.2 Why naive approaches fail

**Binding a whole camera to one element** ("camera 1 = roof") breaks immediately in a real building. A camera pointed at a row of columns sees several of them at once. If a defect appears anywhere in that camera's frame, knowing only which camera saw it gives no information about which specific column it is on.

**Manual per-camera calibration**, clicking six or more matching points between the video feed and the BIM model, once per camera, solves the disambiguation problem correctly but does not scale. A real construction site can have dozens of fixed cameras. Clicking precise point-pairs for each one is slow, error-prone, and has to be repeated every time a camera is replaced or physically nudged. This was raised directly during project review as a concern, and it is a fair one: the proposed method must remove this manual step entirely, not merely describe it as a limitation.

### 1.3 A camera does not realistically see dozens of elements

It is worth being precise about how many elements one camera can plausibly need to disambiguate between, since this bounds how hard the disambiguation problem actually is in practice.

A fixed CCTV lens rarely exceeds roughly 90 to 110 degrees of horizontal field of view before image quality degrades. At a typical monitoring distance of 10 metres, a 90 degree field of view covers approximately 20 metres of width. With a normal structural column spacing of 6 to 9 metres, that works out to **three to five columns**, not dozens, in a single camera's effective view. A camera wide enough to fit dozens of columns in frame would not have enough pixels on any single column to resolve a crack or a honeycomb patch in the first place, since the ground sampling distance degrades proportionally. A scenario requiring one camera to disambiguate among a very large number of elements is therefore not realistic for a defect-detection camera; the method below is designed to handle any number of candidate elements correctly regardless, but this section establishes that the realistic number is small.

---

## 2. Background Concepts

### 2.1 BIM and IFC fundamentals

A BIM model is not a picture of a building. It is a precise, object-based geometric and data description, authored by the engineers who designed the structure, using the IFC (Industry Foundation Classes) open standard (ISO 16739).

**Spatial hierarchy:**

```
IfcProject
  -> IfcSite
       -> IfcBuilding
            -> IfcBuildingStorey
                 -> IfcElement (IfcWall, IfcSlab, IfcColumn, IfcBeam, ...)
```

**GlobalId (GUID).** Every IFC element carries a permanent, unique identifier. This subsystem binds every defect to an element's GUID, not to a screen position or a shape, so the link survives model re-exports, BIM software changes, and routine model updates.

**Property Sets (Psets).** Elements carry structured, named data fields (for example, `Pset_WallCommon` with `FireRating`, `IsExternal`, `LoadBearing`). A detected defect can be written back as a property on the element itself.

**BCF (BIM Collaboration Format).** The open, standard way issues are already exchanged between BIM authoring tools (Revit, ArchiCAD, Navisworks, and others). A BCF topic bundles an issue description, a camera viewpoint, and a status, and round-trips correctly into tools that already support it. Writing mapped defects as BCF topics, in addition to or instead of Property Sets, means this subsystem produces output that downstream BIM tools can consume natively, without a custom integration.

The critical point for this project: **the BIM file already contains every element's exact 3D position.** The existing BIM viewer already renders Column A and Column B in their correct positions, which is only possible because that position data is already parsed out of the file. Nothing new needs to be built to answer "where is this column"; that question is already answered by the viewer that exists today. The mapping subsystem reuses this same geometry, it does not maintain a separate description of where things are.

### 2.2 The camera model: intrinsics and extrinsics

Turning a 2D pixel into a 3D direction requires two independent pieces of information about the camera:

**Intrinsic parameters** (a property of the lens and sensor, not of where the camera is placed):

- Focal length, expressed in pixels (`fx`, `fy`)
- Principal point, the pixel coordinate of the optical centre (`cx`, `cy`), typically near the image centre
- Field of view, which is just another way of expressing focal length relative to sensor width

**Extrinsic parameters** (a property of where the camera is placed and pointed):

- Position in the BIM's coordinate system (a 3D point)
- Orientation, expressed as a rotation matrix `R` (3x3) or equivalently a rotation vector

Neither is sufficient alone. Intrinsics without extrinsics describes a cone shape floating in no particular place. Extrinsics without intrinsics says where the camera is but not how wide it sees. Both together are called the camera's **pose**.

### 2.3 The pinhole projection formula

Every calculation in this plan, camera calibration and runtime mapping alike, rests on one equation, the pinhole camera model:

```
s * [u, v, 1]^T = K * (R * P + t)
```

Where:

- `P` is a 3D point in the object's own local coordinates (for example, a marker corner relative to the marker's centre)
- `R` is the 3x3 rotation matrix describing the camera's orientation (3 degrees of freedom)
- `t` is the 3x1 translation vector describing the camera's position (3 degrees of freedom)
- `K` is the 3x3 intrinsic matrix, `[[fx, 0, cx], [0, fy, cy], [0, 0, 1]]`
- `s` is the depth of the point, which falls out of the calculation
- `(u, v)` is the resulting pixel coordinate

Expanded, this is simply:

```
u = fx * (X_cam / Z_cam) + cx
v = fy * (Y_cam / Z_cam) + cy
```

where `(X_cam, Y_cam, Z_cam) = R*P + t` is the point after being rotated and shifted into the camera's own reference frame.

This single formula is used in two directions in this project: forward, during calibration, to solve for `R` and `t` given known points (Section 3); and backward, at runtime, to convert a detected pixel into a 3D ray once `R` and `t` are already known (Section 4).

### 2.4 Raycasting

A ray is simply a straight line defined by a starting point (an origin) and a direction. Raycasting means asking: travelling from this origin, in this direction, what solid surface does this line hit first?

This is the mechanism that resolves which element a defect belongs to. Two different pixels in the same camera's frame correspond to two different directions (different `(u, v)` values produce different `(X_cam, Y_cam, Z_cam)` directions through the formula above), so a defect on the left of the frame and one on the right resolve to different elements automatically, purely from geometry, using the BIM's own stored geometry as the source of truth for where every element actually is.

When a ray's path could geometrically cross more than one surface, the **nearest intersection wins**, because in reality the nearer, opaque surface blocks anything behind it. This is the same rule a renderer uses to decide what is visible on screen, applied here to decide which BIM element a detection belongs to.

---

## 3. Camera Calibration: PnP and Fiducial Markers

### 3.1 The PnP problem, formally

PnP stands for Perspective-n-Point. It is the problem of recovering a camera's full pose, rotation `R` and translation `t`, given a set of points whose 3D coordinates are already known and whose corresponding pixel positions have been measured in an image. Using the projection formula from Section 2.3, each known point contributes two equations (one for `u`, one for `v`). `R` and `t` together represent six unknowns (three rotation angles, three position coordinates), so in principle four points (eight equations) are enough to solve the system.

In practice, three points (the P3P case) can yield up to four distinct mathematically valid solutions, an inherent ambiguity in that minimal configuration. A fourth point resolves the ambiguity. Using more points than the minimum, which is the normal case here, turns the problem into an over-determined system solved by minimising **reprojection error**: for a candidate `(R, t)`, project every known 3D point through the formula in Section 2.3, compare each predicted pixel to the pixel actually measured, and sum the squared differences. The true pose is the `(R, t)` that minimises this total. `solvePnP` (OpenCV) solves this using an initial approximate estimate (methods such as EPnP) followed by iterative non-linear refinement (Levenberg-Marquardt), and `solvePnPRansac` additionally discards outlier correspondences, a single bad point match, automatically.

### 3.2 Why this matters here: the manual-clicking problem

In the simplest implementation, the known 2D-3D point correspondences for PnP come from a person manually clicking matching points in the camera's video feed and the BIM model, at least six pairs per camera. This works, but it is the exact bottleneck identified in Section 1.2: it does not scale to a real site with many cameras, and must be redone whenever a camera moves.

**The fix is not a new algorithm, it is a different, automatic source of correspondences.** Section 3.3 describes how a fiducial marker supplies these correspondences without any person clicking anything.

### 3.3 Fiducial marker-based calibration

A fiducial marker (ArUco or AprilTag) is a small, high-contrast printed pattern engineered specifically to be detected reliably by simple, fast, classical computer vision, not a trained model. Each printed marker encodes a unique ID as part of its pattern, so two different markers are never confused with each other; a detector reports not just "a marker was found" but "marker ID 7 was found, at these four corner pixels." Detection is a handful of lines using OpenCV's `cv2.aruco` module, running in milliseconds with no training data and no dataset.

Because a marker is a flat square of known physical size, its four corners supply exactly the kind of known 2D-3D correspondences PnP needs:

- The marker's four corners have known positions relative to its own centre (for example, plus-or-minus 10 cm on each axis for a 20 cm marker).
- The marker's centre has a known position in the BIM's coordinate system (Section 3.4).
- The four corners' pixel positions come directly from the automatic marker detector.

Feeding these four correspondences into `solvePnP` yields the camera's full pose, position and orientation together, automatically, the moment the camera can see the marker.

**Why no separate distance measurement is needed.** A single point in an image cannot reveal real-world distance (a large object far away looks identical in a photo to a small object close up). A square of *known real size*, however, can: how large the marker appears in the image directly reveals how far away it is. For a marker of known width `W`, measured apparent width `w` pixels, and focal length `fx` pixels, distance follows directly from the same projection formula:

```
distance = (W/2 * fx) / (w/2)
```

This distance calculation and the orientation calculation are not two separate steps; they both fall out of the same `solvePnP` call simultaneously, because asymmetry between the marker's four corners in the image reveals tilt at the same time that overall size reveals distance.

### 3.4 The marker registry: how the system learns where each marker is

This is a one-time, per-marker administrative step, not a per-camera or per-detection step.

**Who does it, and when:** whoever physically installs a marker tapes it at a point that is already a known coordinate in the BIM, for example, the top-left corner of a specific column. In the platform, they select that same point on the BIM model, the same interface already used for click-to-place defect mapping. The system reads that point's coordinates directly out of the BIM, the same way the BIM viewer already knows where every column is (Section 2.1), and stores it against that marker's unique ID.

**The registry itself** is a small lookup table:

| Marker ID | Placed at (BIM reference) | Coordinate |
| --- | --- | --- |
| 1 | Column A12, top-left corner | (12.40, 3.20, 8.10) |
| 2 | Column B7, base corner | (18.90, 0.00, 8.10) |

A handful of markers, each registered once, can serve an entire camera network: markers do not need to be placed one per camera or one per element, only densely enough that every camera can see at least one marker somewhere in its frame.

**What is a genuinely manual input, and what is not:**

- Manual, one-time, per marker: selecting which BIM point the marker is taped to.
- Manual, one-time, fixed per project: the marker's physical size (decided when it is printed, entered once as a configuration value, since this cannot be inferred from an image alone).
- Never manual: the camera's position, orientation, or distance from the marker. These are always computed outputs of `solvePnP`, never inputs.

Since a marker is a flat object, full registration technically requires its orientation (which way it faces) as well as its reference point. In practice this is free: the marker is taped flush against a known BIM surface (a column face, a wall), and that surface's orientation already exists in the BIM geometry, so no additional manual measurement is required beyond selecting the point and the face.

### 3.5 Worked PnP example

Marker: 20 cm x 20 cm, corners at plus-or-minus 10 cm from its centre. Camera intrinsics: `fx = fy = 800` pixels, `cx = 400`, `cy = 300`. For clarity this example assumes the camera is not tilted (`R` = identity), so only position `t` is solved by hand; in the real system `R` is solved simultaneously using the same numerical optimisation described in Section 3.1.

Suppose the marker-detection software reports these measured corner pixels from an actual frame:

| Corner | Real offset from marker centre (m) | Measured pixel |
| --- | --- | --- |
| Top-left | (-0.10, +0.10) | (416.7, 316.7) |
| Top-right | (+0.10, +0.10) | (483.3, 316.7) |

**Step 1, distance:**

```
apparent_width = 483.3 - 416.7 = 66.6 px
real_width = 0.20 m
Z = (real_width * fx) / apparent_width = (0.20 * 800) / 66.6 = 2.40 m
```

**Step 2, horizontal position, using the top-left corner:**

```
416.7 = 400 + 800 * (X / 2.40)
X = (416.7 - 400) * 2.40 / 800 = 0.05
```

This is the corner's X; since the corner sits at -0.10 from the marker's centre, the camera-relative centre X is `0.05 + 0.10 = 0.15`.

**Step 3, vertical position, same method:** yields a centre Y of -0.05 m.

**Result:** `t = (0.15, -0.05, 2.40)` metres, recovered entirely from four measured pixels plus the marker's known size. When rotation is also unknown, the same measured pixels are used, but `R` and `t` are solved together through the iterative optimisation in Section 3.1 rather than by this kind of direct substitution, since position and orientation become mathematically entangled once tilt is introduced.

### 3.6 Camera intrinsics: where they come from

Intrinsics (`fx`, `fy`, `cx`, `cy`) are needed for both calibration and runtime raycasting. Two sources, in order of preference:

1. **From the camera's datasheet.** Most CCTV specification sheets state horizontal field of view directly, from which `fx` follows as `fx = (image_width / 2) / tan(FOV_horizontal / 2)`. Sufficient for element-level localisation.
2. **From a one-time formal calibration**, holding a printed checkerboard pattern in front of the camera and running `cv2.calibrateCamera`. Produces tighter intrinsics, including lens distortion coefficients, at the cost of one extra one-time procedure per camera model.

### 3.7 Fallback: manual calibration

Manual point-clicking (Section 3.2) is retained only as a fallback for the rare camera with no marker visible in its frame at all. It is never the primary calibration path.

---

## 4. Runtime Defect-to-Element Mapping Pipeline

Once a camera is calibrated (Section 3), every detection that arrives from the upstream detection subsystem is processed the same way, automatically, with no human involvement.

### 4.1 Interface contract

This is the exact boundary of this subsystem's responsibility. It receives:

| Field | Source |
| --- | --- |
| `class` | Upstream YOLOv11 detector |
| `confidence` | Upstream YOLOv11 detector |
| `camera_id` | Upstream detection subsystem |
| `pixel_location` | Bounding box or mask centroid, upstream |
| `timestamp` | Frame capture time |

And it produces a defect record bound to a BIM element GUID (Section 4.6). Errors in the upstream detector, missed or false detections, are out of scope here and cannot be corrected by this subsystem; this interface should be agreed with the detection team early.

### 4.2 The five-step pipeline

**Step 1, receive detection.** The record above arrives.

**Step 2, pixel to 3D ray.** Using the calibrated camera's stored pose (`R`, `t`) and intrinsics (`fx`, `fy`, `cx`, `cy`), the pixel `(u, v)` is converted to a ray. This reuses the projection formula from Section 2.3 in reverse:

```
x = (u - cx) / fx
y = (v - cy) / fy
direction_camera_space = (x, y, 1)
direction_world = normalize(R_inverse * direction_camera_space)
ray = { origin: camera_position, direction: direction_world }
```

**Step 3, raycast into the BIM.** The ray is tested for intersection only against the elements in this camera's candidate set (Section 4.3), not the entire BIM model. This is both a correctness measure (it rules out geometrically impossible or occluded false matches) and a performance measure (far fewer elements to test per detection).

**Step 4, nearest hit equals element.** Where the ray's path crosses more than one candidate element's geometry, the nearest intersection is taken, since the nearer, opaque surface would block anything behind it in reality. The winning element's GUID is the answer.

**Step 5, record and write back.** The result is checked against existing defect records (Section 4.5) before being written into the BIM (Section 4.6).

### 4.3 Candidate-set restriction, in full

This is the mechanism that answers the recurring question of how one camera's detections are correctly assigned among several visible elements, and it is addressed here with full detail since it was previously under-specified.

**What it is.** Each camera is bound not to one element, but to a *set* of elements it can plausibly see. This set only narrows which elements the raycast in Step 3 is tested against; the raycast itself, not the candidate set, resolves the exact element. A loosely or even slightly over-inclusive candidate set still produces a correct result, since the geometry in Step 4 does the real disambiguation.

**How the set is built: automatically, by the system, immediately after calibration.** Once calibration (Section 3) produces the camera's exact position and orientation, and given the camera's field of view (already known, Section 3.6), the system has the camera's complete view frustum, the pyramid-shaped volume of space the camera can see. The system queries the BIM geometry directly: which elements' geometry falls inside that frustum? Everything found becomes the candidate set. No manual selection step is required; this falls out of the same calibration data already computed, at the same point in time that calibration completes.

**Where a manual override still has a place.** A pure frustum test knows about angles and distance but not occlusion: it could include an element that is technically inside the cone but is actually hidden behind something else (a wall in front of a column, for example). A light, optional manual step, excluding one element from a camera's candidate set, is a reasonable fallback for this edge case, in the same relationship to automatic candidate-set generation that manual point-clicking has to marker-based calibration: automatic by default, manual override only for the exception.

**When this happens, restated plainly:** immediately after Section 3's calibration completes for a given camera, before any live defect detection begins.

### 4.4 Restricting the BIM material tested also improves reliability

Separately from candidate-set restriction by camera, filtering which BIM material a ray is tested against (for example, concrete-only elements) has been shown elsewhere to reduce false matches; prior work combining aerial imagery with BIM material semantics as a filter reduced false-discovery rate from 70.8 percent to 56.8 percent. The same principle, applied here through the candidate-set restriction, is the justification for Step 3 being restricted rather than tested against the full model.

### 4.5 De-duplication

A static defect, once it exists, is likely to be detected repeatedly across many video frames and potentially by more than one camera. Without de-duplication this would create one record per frame, not one record per real defect.

**Rule:** before inserting a new defect record, check for an existing record with the same element GUID, the same defect class, and a 3D position within a small tolerance of the new detection's hit point (Section 4.2, Step 4).

- If a match exists, update it (refresh last-seen timestamp, update confidence if higher, track growth over time if relevant to the defect class).
- If no match exists, create a new record.

This keeps the defect registry at one entry per real-world defect, growing only when genuinely new defects appear.

### 4.6 Writing results back into the BIM

Mapped, de-duplicated defects are written back using standard BIM interoperability mechanisms (Section 2.1), not a disconnected external database:

- **Property Set (Pset) entry**, attached directly to the element's GUID, containing defect class, confidence, first-seen and last-seen timestamps, and status.
- **BCF (BIM Collaboration Format) topic**, bundling the same information as an issue with a camera viewpoint, so it round-trips into any BIM authoring tool that already supports BCF (Revit, ArchiCAD, Navisworks, and others), without a custom integration being required on the recipient's side.

Either mechanism, or both together, keeps defect data permanently and queryably tied to the exact structural element, satisfying Objective 2 (Section 1).

### 4.7 Multi-camera conflict resolution

When two cameras both have a given element in their candidate set and both report a detection that resolves to it, a simple resolution rule is applied:

- Prefer the detection with the higher confidence score.
- If both detections are low-confidence, require agreement from both cameras before accepting either, rather than acting on either alone.

This mirrors the approach used in the closest related system found in the literature (Hsieh et al., ISARC 2024), which resolves multi-camera disagreement for construction-progress detections using confidence, phase, or detection frequency as the deciding factor.

---

## 5. Why This Is Practical at Real-Site Scale

- **No new hardware.** Existing fixed CCTV cameras are sufficient. A fiducial marker is a printed sheet of paper.
- **Proven to scale.** Automatic, marker-based calibration of camera networks well beyond a handful of cameras has been demonstrated directly: approximately 40 fixed cameras across an 800 square metre area were registered automatically using a single marker carried by a robot, with zero manual clicking per camera. A separate study achieved 3 cm calibration accuracy across a 6-camera industrial network, fully automatically, at distances up to 9.45 metres.
- **Self-checking.** Because a marker can be left in place after calibration, the system can periodically re-detect it and confirm the stored pose still matches, catching a bumped or replaced camera automatically rather than silently drifting out of calibration.
- **The downstream pipeline never changes.** However a camera's pose is obtained (marker, manual fallback, or a reused site-survey point), Section 4's raycasting pipeline is identical. Improving the calibration method later never requires redesigning the mapping logic.
- **Consistent with the direction of the field.** Independent research on registering cameras to BIM without manual correspondence reports large reductions in manual effort; one study reports a 95.8 percent reduction in time spent on camera pose alignment compared to a fully manual process, using only a small number of reference points.

---

## 6. Literature Review and Gap Analysis

| Author | Year | Contribution | Limitation |
| --- | --- | --- | --- |
| Mishra et al. | 2022 | Auto-calibrated approximately 40 cameras across 800 square metres using a single fiducial marker | Marker position established independently (by a robot), not drawn from an existing BIM |
| Sensors (industrial RGB-D network) | 2019 | Automatic calibration of a 6-camera network using retroreflective fiducial markers, 3 cm accuracy at up to 9.45 m | Marker positions independently surveyed, not BIM-anchored |
| Hsieh et al. | ISARC 2024 | Raycasts multi-camera detections onto a BIM | Targets construction progress stages, not surface defects |
| Chen, Lu and Lou | 2023 | Maps aerial defect images onto a BIM using material semantics as a filter | Aerial imagery only, not fixed CCTV; no per-element GUID resolution shown |
| Asadi and Han | 2018 | Real-time image-to-BIM registration using point correspondences | Manual point-clicking; does not scale |
| BIMCaP | 2024 | LiDAR-camera pose refinement against a BIM | Requires LiDAR hardware, not camera-only |
| Kaden and Clemen | 2017 | Establishes that construction sites already use geodetic coordinate reference systems tied to the BIM for layout surveying | Not applied to camera calibration or defect localisation |
| SLAM-to-BIM (JCEM) | 2026 | Reports a 95.8 percent reduction in manual camera-pose alignment effort using reference-point bundle adjustment | General visual SLAM registration, not raycasting-based defect localisation |

**Research gap.** No openly documented system was found that combines automatic, marker-based camera calibration anchored to coordinates already present in the BIM with per-detection raycasting, restricted to a candidate set of elements, to localise concrete surface defects onto a specific BIM element GUID. This is stated as "to the best of our knowledge" and is bounded by the limits of this review: searches used general web search rather than Scopus or Web of Science, and most sources were read from their abstracts rather than their full text. Proprietary solutions within construction firms may exist without being described in published literature.

---

## 7. Novelty Statement

**What is established, and should not be claimed as new:**

- Fiducial-marker-based automatic camera calibration itself, well established in robotics, AR, and industrial sensor networks.
- Raycasting a fixed camera's detections onto a BIM, demonstrated for construction progress monitoring and for general indoor camera localisation against a BIM.
- PnP-based camera pose estimation and BIM registration by matching image points to a model, both established, including automatic and semi-automatic variants.
- Property Sets and BCF as the standard mechanism for attaching data and issues to BIM elements, part of the IFC and buildingSMART standards.

**What appears to be the specific gap:**

- Systems that raycast camera detections onto a BIM target construction progress or safety, not surface defects; applying the same mechanism specifically to concrete defect localisation, with a per-camera candidate-set restriction, was not found.
- The fiducial-marker calibration literature reviewed establishes a marker's reference position independently, by a separate calibration robot, a checkerboard, or manual survey, rather than by anchoring the marker to a coordinate that already exists inside the target BIM itself. Reusing the BIM's own coordinates as the marker's ground truth, so that no independent surveying step is needed at all, appears to be a small but genuine refinement not explicitly described in the sources found.

**Candidate novelty statement:** An automatic, marker-based calibration workflow, where the fiducial marker's reference position is drawn directly from existing BIM coordinates rather than independently surveyed, combined with per-detection raycasting restricted to camera-bound candidate elements, to map concrete defects onto their exact BIM element without manual per-camera or per-detection intervention.

---

## 8. Limitations and Risks

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| Marker gets dirty, damaged, or occluded on an active site | Detection fails silently if unnoticed | Periodic automatic re-detection; alert if a calibrated camera stops seeing its marker; manual fallback kept ready |
| BIM does not exactly match as-built geometry | A correctly computed ray can still land on the wrong or no element | Bounded by the model's Level of Development; add a tolerance band and snap-to-nearest-bound-element logic |
| Camera physically moves or is replaced | Stored pose becomes wrong | Automatic marker re-detection flags and corrects this (Section 5) |
| Candidate-set frustum test does not account for occlusion | An element technically inside the view cone but actually hidden could be wrongly included | Manual override to exclude a specific element from a camera's candidate set (Section 4.3) |
| Subsystem quality is bounded by upstream detection accuracy | Errors in detection (missed or false positives) cannot be corrected downstream | Out of scope for this subsystem; interface contract (Section 4.1) should be agreed with the detection team early |

---

## 9. Evaluation Plan

| Metric | What it tests |
| --- | --- |
| Calibration time per camera | Marker-based approach versus manual point-clicking, measured directly |
| Correct-element assignment rate | Percentage of test defects mapped to the true element, using surveyed ground truth |
| Localisation error (cm) | Distance between the computed hit point and the true position on the element |
| Robustness to marker condition | Detection success rate under dust, partial occlusion, and varied lighting |
| De-duplication precision and recall | Whether repeated frames of the same defect create one record, not many |
| Multi-camera conflict behaviour | Whether the resolution rule in Section 4.7 gives the correct answer in a 2-camera test |

If real site footage is not available during evaluation, a scaled mock-up wall with introduced defects (for example, cast test panels with honeycomb-like voids) and a fixed camera is a defensible substitute, provided this limitation is stated when reporting results.

---

## 10. Implementation Roadmap

### 10.1 Milestone 1: Fiducial marker calibration

- Integrate `cv2.aruco` marker detection against live or recorded camera frames.
- Build the marker registry UI: extend the existing click-to-place interface so a user can select a BIM point and associate it with a marker ID (Section 3.4).
- Implement `solvePnP` with RANSAC using detected marker corners and the registry's stored coordinates as input.
- Implement the reprojection-error sanity check (Section 3.1): re-project known points through the solved pose and confirm pixel error is small before accepting a calibration.
- Store the resulting pose (`R`, `t`) and intrinsics against the camera's ID.

### 10.2 Milestone 2: Automated raycasting pipeline

- Implement the pixel-to-ray conversion (Section 4.2, Step 2).
- Implement ray-mesh intersection against BIM geometry. Two implementation options, chosen to match the existing backend language:
- If the backend is Node.js: reuse the same `THREE.Raycaster` already used by the existing click-to-place viewer, pointed at a virtual camera built from the calibrated pose, rather than the viewer's own camera.
- If the backend is Python: use `trimesh` (optionally accelerated with `pyembree`) for ray-mesh intersection against BIM geometry exported from IFC.
- Implement nearest-hit selection (Section 4.2, Step 4).

### 10.3 Milestone 3: Candidate-set binding

- Compute each calibrated camera's view frustum from its pose and field of view.
- Query BIM element geometry for intersection with that frustum; store the resulting candidate set per camera (Section 4.3).
- Build the manual override interface for excluding an occluded element from a camera's candidate set.

### 10.4 Milestone 4: De-duplication logic

- Design the defect registry schema (Section 10.6).
- Implement the match-or-create rule from Section 4.5.
- Add growth tracking for defect classes where size change over time is meaningful (for example, crack width).

### 10.5 Milestone 5: BCF and Property Set write-back

- Implement Property Set writing against the element's GUID.
- Implement BCF topic export (topic, viewpoint, status) for interoperability with external BIM tools.

### 10.6 Data model sketch

**`cameras` table**

| Field | Description |
| --- | --- |
| `camera_id` | Unique identifier |
| `rtsp_url` | Stream source |
| `intrinsics` | `fx`, `fy`, `cx`, `cy` |
| `pose_rotation` | `R`, from calibration |
| `pose_position` | `t`, from calibration |
| `candidate_elements` | List of bound element GUIDs (Section 4.3) |

**`markers` table (the registry from Section 3.4)**

| Field | Description |
| --- | --- |
| `marker_id` | Decoded from the printed pattern |
| `bim_point_ref` | The BIM point the marker is taped to |
| `coordinate` | Read from the BIM for that point |
| `size` | Physical size, fixed per project |

**`defects` table**

| Field | Description |
| --- | --- |
| `defect_id` | Unique identifier |
| `element_guid` | The BIM element this defect belongs to |
| `class` | Defect type |
| `confidence` | From upstream detection |
| `position` | 3D hit point from raycasting |
| `first_seen` / `last_seen` | Timestamps |
| `camera_ids` | Which camera(s) have observed this defect |
| `status` | Open, resolved, etc. |

### 10.7 Technology components summary

| Component | Tool / library | Status |
| --- | --- | --- |
| Marker detection | OpenCV `cv2.aruco` | New, small |
| Pose solving | OpenCV `solvePnP` with RANSAC | New, small, well documented |
| Ray-mesh intersection | `THREE.Raycaster` (reused) or `trimesh` | New, but reuses existing viewer logic where possible |
| IFC parsing / GUID access | `IfcOpenShell` (Python) or `web-ifc` (JS), whichever the existing viewer already uses | Reused |
| BIM viewer, click-to-place UI | Existing codebase | Already built |
| RTSP ingestion, YOLOv11 inference | Existing, separate subsystem | Already built, outside this scope |
| Defect registry, de-duplication | New database tables (Section 10.6) | New |
| Property Set / BCF write-back | Standard IFC / buildingSMART mechanisms | New, small |

---

## 11. References

1. OpenCV. *Real Time pose estimation of a textured object* (PnP with RANSAC tutorial). docs.opencv.org
2. Mishra, S. et al. (2022). *Look Both Ways: Bidirectional Visual Sensing for Automatic Multi-Camera Registration.* arXiv:2208.07362
3. *Automatic Calibration of an Industrial RGB-D Camera Network Using Retroreflective Fiducial Markers.* Sensors 19(7):1561 (2019). DOI 10.3390/s19071561
4. Kaden, R. and Clemen, C. (2017). *Applying Geodetic Coordinate Reference Systems in Building Information Modeling (BIM).* FIG Working Week 2017.
5. Chen, J., Lu, W., and Lou, J. (2023). *Automatic concrete defect detection and reconstruction by aligning aerial images onto semantic-rich building information model.* Computer-Aided Civil and Infrastructure Engineering 38(8). DOI 10.1111/mice.12928
6. Hsieh, C.-C. et al. (2024). *Integration of Construction Progress Monitoring Results using AI Image Recognition from Multiple Cameras onto a BIM.* Proc. 41st ISARC, Lille, France.
7. *Toward Automated SLAM-to-BIM for Digital Twin Applications.* Journal of Construction Engineering and Management 152(10) (2026). DOI 10.1061/JCEMD4.COENG-18279
8. *Multi-Camera Extrinsic Calibration for Real-Time Tracking in Large Outdoor Environments.* Journal of Sensor and Actuator Networks 11(3):40 (2022). DOI 10.3390/jsan11030040
9. *Fusion of fiducial marker and point cloud data for reliable multi-camera tracking in robotic assembly of construction elements.* Construction Robotics (2026). DOI 10.1007/s41693-026-00183-3
10. *BIMCaP: BIM-based AI-supported LiDAR-Camera Pose Refinement.* arXiv:2412.03434 (2024)
11. Karsch, K., Golparvar-Fard, M., and Forsyth, D. (2014). *ConstructAide: Analyzing and Visualizing Construction Sites through Photographs and Building Models.* arXiv:1912.11567
12. Asadi, K. and Han, K. (2018). *Real-Time Image-to-BIM Registration Using Perspective Alignment for Automated Construction Monitoring.* Construction Research Congress 2018, ASCE.
