# DefectSync project audit — 18 November 2026

## Verdict

This is a substantial B.Tech prototype with real detector weights, a sensible separation of API/ML/frontend code, and working geometry components. It is **not currently ready for dependable unattended field inspection or automatic defect-to-BIM mapping**. Confirmed integration, calibration, authorization, and build defects prevent that conclusion. Fixing software defects will still leave the separate question of accuracy on independently collected site data.

This review changed no application code or configuration. It adds this report and an offline reproduction script. No live database migrations, live camera access, or real-site accuracy evaluation were performed. The configured database is remote; its contents and deployed schema were not inspected. Existing local dependencies were used rather than installing a fresh environment. A complete production build, browser interaction test, dependency vulnerability audit, and PDF layout audit were not performed. Generated/vendor JavaScript and WASM were inventoried rather than audited line by line.

## Verification actually performed

| Check | Observed result |
|---|---|
| Parse backend Python source | 65 Python files parsed without syntax errors |
| Import FastAPI app | Successful; 48 routes registered |
| Existing synthetic suite | 9 passed, 3 pytest return-value warnings; 15.25 seconds reported by pytest |
| Actual calibration orchestrator on the same synthetic scene | Returned success despite **9.5234 m** camera-position error and **21.687 px** reprojection error |
| Camera response schema with stored candidate GUID list | Pydantic rejects list because schema requires dictionary |
| Frontend TypeScript | Failed: four missing Three.js declaration errors and one missing `fov` field error |
| Frontend lint | Did not complete a lint check; asked interactively to configure ESLint and exited 1 |
| Bundled detector loading | Real YOLO model loaded on configured CPU; all seven class names match code |
| Three blank-image predictions at 640×480 | Zero detections each; first prediction 7.192 s, warm predictions 0.178 s and 0.238 s |
| Detector provenance | SHA-256 of bundled detector matches `weights/best.pt` inside local `backend/ml/runs.zip` |
| Sample IFC extraction | Both provided IFC samples extracted 5 elements / 60 triangles each |
| Password hash/verify smoke test | Passed; Passlib emitted a bcrypt version compatibility warning |
| Secret configuration hygiene | Root `.env` is not tracked; active JWT secret differs from the shipped default; no secrets reproduced here |

The blank-image timing is a tiny inference smoke test, not a video FPS benchmark. It excludes decoding, network transfer, annotation, persistence, raycasting, and concurrency. Ultralytics also reported denied writes to its user-profile settings/cache during the smoke tests; model loading and predictions nevertheless completed.

Reproduce the key offline failures from the root with `python docs/reproduce_audit_findings.py`. Run the existing suite from `backend` with `python -m pytest tests/test_phase2_synthetic_e2e.py -q --tb=short`. Run `./node_modules/.bin/tsc.cmd --noEmit --incremental false` from `frontend` on Windows.

## Highest-priority confirmed findings

### 1. Automatic mapping uses the wrong bounding-box format — P1

`backend/app/api/v1/calibration.py:381–390` chooses `det.bbox_pixels` then reads `x/y/w/h`. The detector produces `x1/y1/x2/y2` for this field. All lookups default to zero, so every detection gets centroid `(0,0)`. Example: a box from `(900,500)` to `(1020,580)` should produce `(960,540)`.

Impact: rays miss or hit unrelated geometry; unrelated defects can collapse onto the same point. Fix the adapter explicitly using `(x1+x2)/2`, `(y1+y2)/2`, and validate image dimensions against the calibration. Test through the actual API path with known detector output.

### 2. Production calibration differs from the passing test path — P1

`backend/ml/calibration/camera_calibrator.py:112–118` takes only the first matching marker. The synthetic PnP tests combine corners from multiple markers. The production function only logs excessive reprojection error (`:178–183`) and still returns success.

The audit passed the existing synthetic frame and its correct registry to `calibrate_camera_from_frame`. It returned success with 21.687 px reprojection error and a 9.5234 m camera-position error. This directly disproves the current success flag as a reliable calibration acceptance check.

Use all valid correspondences, reject unacceptable fits, test planar-pose ambiguity/physical plausibility, and refine on accepted inliers. `pose_solver.py:219` currently refines against all points after RANSAC. Add tests against the orchestrator, not just `solve_pnp`.

### 3. Marker registration UI supplies invented coordinates — P1

`frontend/src/app/(dashboard)/viewer/page.tsx:1155–1165` sends every marker with `world_x=world_y=world_z=0`. It does not send the surface normal, leaving `(0,0,1)` as the backend default. Selecting an element GUID does not determine the marker's actual centre or orientation.

Impact: ordinary wall-mounted markers cannot produce the correct world pose through this UI. Collect the surveyed marker centre, surface orientation, and printed-marker rotation. Surface normal alone leaves rotation around that normal unspecified; the current arbitrary basis in `pose_solver.py` assumes one fixed marker alignment.

### 4. Calibrated cameras cannot be serialized correctly — P1

Calibration stores a list of candidate GUIDs (`backend/app/api/v1/calibration.py:183`). `CameraResponse.candidate_element_guids` is `dict | None` (`backend/app/schemas/bim.py:105`). Pydantic rejects a list, including an empty list. Consequently camera list/detail responses can fail after calibration. Align model annotations, response schemas, and frontend types with `list[str]`.

### 5. Cross-organization access checks are missing — P1

Authentication exists, but authorization is inconsistent:

- Camera detail/update/delete and the uncalibrated detection path load arbitrary camera IDs without verifying project ownership (`backend/app/api/v1/cameras.py:99` onward).
- BIM list/detail/delete/mapped-defect endpoints similarly omit ownership checks (`backend/app/api/v1/bim.py:90` onward).
- Image/batch/video detection accepts a project ID and saves results without verifying it belongs to the caller (`detection.py`, `video.py`).
- Calibration status omits the check used by calibrate and auto-detect (`calibration.py:224` onward).
- Video result/download caches do not store or check owner/project.
- `/uploads` is mounted as unauthenticated static content (`backend/app/main.py:60`), so knowledge of an uploaded asset URL bypasses project permissions.

Knowing another resource ID can therefore permit unauthorized reads or writes; camera details include RTSP URLs, potentially containing credentials. Centralize project-scoped authorization, validate related model/user IDs, protect assets, and add two-organization API tests. No attack was performed against the remote database.

### 6. Missing/broken weights silently generate fabricated defects — P1

`backend/ml/inference/detector.py:142,191,328` catches model-loading errors and generates fixed demo detections with randomized severity. The normal image/video persistence paths can save these as inspection records. The bundled model did load during this audit, but a deployment failure would activate this behavior.

Fail closed in normal operation. Require an explicit demo setting, label demo responses visibly, and prohibit saving demo output as real inspection evidence.

### 7. Frontend type checking fails — P1

Three.js types are absent from declared dev dependencies. `viewer/page.tsx:638` resets camera form state without the required `fov`. Fix both and rerun type checking and a production build. `npm run lint` currently launches configuration rather than an established repeatable lint check. There is no frontend test script although `Makefile` calls `npm run test`.

### 8. De-duplication refers to nonexistent records — P1

`backend/app/services/auto_mapper.py:257` creates a random placeholder UUID when matching earlier detections in the same batch. That ID is unrelated to the database ID eventually generated. The save loop queries it, finds no defect, and still increments the duplicate count (`calibration.py:424–437`). A later higher-confidence observation can therefore fail to update the saved record.

Resolve intra-batch observations to a stable record/key before persistence. Higher-confidence updates must update severity label as well as score: currently only confidence and score change. Concurrent requests also need transactional duplicate handling; a prior read followed by independent inserts is not sufficient.

### 9. Migration can fail on an existing populated installation — P1

`backend/alembic/versions/513e82a138f3_add_fiducial_markers_and_camera_.py:52` adds a non-null `calibration_status` column without a server default or backfill. Existing camera rows make this upgrade invalid. Use a staged/defaulted migration and test both an empty database and one with pre-Phase-2 data.

The old schema also admits `WATER_SEEPAGE`, while the current Python enum does not. The later migration adds new values but does not migrate any existing water-seepage rows. Such rows would need an explicit migration policy; their existence in the remote DB was not checked.

## Other correctness and operational findings

| Priority | Finding and consequence | Location |
|---|---|---|
| P1 when enabling S3 | Non-local storage recursively calls the same function with unchanged settings; no actual fallback or S3 upload occurs | `backend/app/services/ml_service.py:117–121` |
| P1 for deployment | PostgreSQL TLS certificate and hostname verification are disabled | `backend/app/db/session.py:29–30` |
| P1 for continuous operation | RTSP exceptions are swallowed and responses say `completed`; uncalibrated camera detection also sets the camera ACTIVE after failure | `video.py:239–250`, `cameras.py:206–272`, `calibration.py:317–321` |
| P2 | No implemented scheduler consumes `auto_detect_enabled` / interval fields, despite the UI showing automatic intervals | `cameras.py`, `viewer/page.tsx:963`; repository-wide scheduler search |
| P2 | RTSP analysis is a finite batch response, not ongoing SSE/live processing; no reconnect/backoff/cancellation policy | `video.py:197–252`, `video_processor.py:267` onward |
| P2 | Calibration open timeout is set after opening; continuous processor lacks explicit open/read timeouts | `marker_detector.py:133` onward, `video_processor.py` |
| P2 | `frame_skip=0` is accepted and causes modulo-by-zero; frame counts and several calibration parameters lack useful bounds | video form parameters, camera/calibration schemas |
| P2 | 500 MB video limit is declared but never enforced; IFC upload has no size ceiling; complete files are read into memory | `video.py:34,69`, `bim.py:64` |
| P2 | Image inference is blocking work inside async request functions; simultaneous camera jobs share one mutable detector without an explicit queue/ownership policy | `ml_service.py:57–86`, `video.py`, `calibration.py` |
| P2 | Webcam submits every two seconds without an in-flight guard and ignores frame errors. Even `auto_save=false` still writes original and annotated image files | `frontend/.../video/page.tsx:202–238`, `backend/app/api/v1/detection.py:77–89` |
| P2 | Video de-duplication compares pixel boxes across the entire video. Moving cameras can merge different physical defects at the same screen location or count the same defect repeatedly | `video_processor.py:128–142` |
| P2 | Results and geometry caches have no eviction; video results disappear on restart and are not shared across workers | `_video_results`, `_mesh_cache` |
| P2 | Creating cameras drops provided FOV/resolution fields. Updating camera source/model or markers does not invalidate the old pose/candidate set | `cameras.py:78–92,126–128`, `markers.py` |
| P2 | Ray construction ignores distortion even when stored calibration includes it; changed stream dimensions/zoom are not checked | `raycaster.py:56–99`, `calibration.py` |
| P2 | Uncalibrated `/auto-detect` returns the old camera response shape despite declaring `AutoMappingResult`; calibrated camera UI still reads the old `unique_defects_saved` field | `calibration.py:263,294`, `viewer/page.tsx:1077` |
| P2 | Camera-origin evidence is recorded as `camera://name` without a persisted snapshot. Later reviewers cannot inspect the frame behind the defect | `cameras.py:232`, `calibration.py:401` |
| P2 | BIM files are marked READY without parsing; `.ifczip` is accepted but viewer passes raw downloaded bytes to IFC parsing without explicit unzip | `bim.py:30,76`, viewer IFC loader |
| P2 | Defect records lack BIM model/version identity; project-wide mapped defects can be displayed against a different selected model | `models/defect.py`, `bim.py:get_mapped_defects`, viewer |
| P2 | Project/model relations can reference resources outside the selected project unless explicitly checked; role helper exists but write endpoints do not use it | camera/marker creation and update, `api/deps.py:75` onward |

Arbitrary camera URLs also need a deployment-specific allowed-network/protocol policy: the server currently passes caller-supplied strings directly to OpenCV. Preserve authorized access to site cameras while preventing unrelated internal service/file access. Logs and responses should redact embedded RTSP passwords.

## ML quality and scientific validity

The deployed checkpoint's embedded training metrics are:

| Metric | Value |
|---|---:|
| Precision | 59.57% |
| Recall | 51.326% |
| mAP@0.50 | 54.742% |
| mAP@0.50:0.95 | 29.695% |

These match the final row of the archived CSV. They are stored validation metrics, not an independently rerun benchmark and not a real-site guarantee. The archive contains 100 CSV rows with repeated epoch numbering and an earlier stronger row: precision 86.567%, recall 75.055%, mAP50 83.192%, mAP50–95 65.505% at an epoch labeled 46. Do not quote that earlier row as the bundled checkpoint's verified performance. Reconcile training/resume history, dataset versions, and checkpoint selection, then re-evaluate frozen weights on a clean held-out set.

The source dataset itself is not in this folder. Split independence, duplicate leakage, annotation quality, class balance, and site diversity could not be verified. The merge script drops images with no remapped labels (`download_dataset.py:177–179`), removing normal/background examples; preserve verified negative images and evaluate false alarms on intact concrete, joints, shadows, cables, stains, and formwork.

There is **no bundled severity classifier checkpoint**. Active grading is a hand-written weighted function of class, image-area ratio, detector confidence, aspect ratio, and image-edge proximity. Its output changes with framing and distance. Dimensions are bounding-box pixels, not measured crack width/depth or physical dimensions. No independent engineering severity validation is present.

There is also a latent severity-training label bug: `ImageFolder` assigns alphabetical indices (`critical`, `high`, `low`, `medium`), but the script saves `classes=[low,medium,high,critical]`, and inference uses weights in that assumed order. Fix index mapping and save/use the actual mapping before training or deploying that classifier. This does not affect the currently active heuristic, but would affect a checkpoint trained using this script.

Bounding-box centre raycasting assumes the centre lies on the defective surface. A box crossing an opening, edge, or multiple elements violates that assumption. No uncertainty gate, segmentation-based surface selection, or visibility evidence currently resolves this. The 0.5 m duplicate radius can also merge genuinely distinct nearby defects. Treat these as experimental design limitations requiring measured validation.

## Folder structure, documentation, and unfinished features

- API routes, models, schemas, services, inference, calibration, and training are sensibly separated. Database migration history and shared taxonomy exist. This is a useful foundation, not an empty mock-up.
- The 1,200+ line viewer combines model rendering, picking, defect management, camera forms, calibration, and markers. Split these responsibilities after stabilizing behavior and contracts.
- Reports/BCF export and settings are placeholder pages. No audit-event history or inspection-creation API is implemented, although the README advertises lifecycle audit/report functionality. The dashboard counts non-null inspection IDs, but normal detection paths do not create/link inspections.
- Docker Compose provisions infrastructure only. It does not package/start frontend/backend. Redis/Celery/MinIO dependencies do not establish a working queue, scheduler, or S3 integration.
- `Makefile` has a seed target for nonexistent `app.db.seed`, a frontend test target without a package script, and a `clean` target that deletes Docker volumes.
- `.gitignore` contains 21 NUL bytes in its final appended archive rule; `backend/ml/runs.zip` remains untracked. Repair encoding and intentionally decide which artifacts are versioned. Both `runs.zip` and `backend/test_synthetic_frame.png` were already untracked before this audit.
- Generated IFC WASM/worker assets appear in several public directories. Verify the runtime JS/WASM versions match and keep only needed distribution paths. No binary compatibility claim was established here.
- Requirements include broad, unbounded ML packages; the installed environment contains both OpenCV wheel variants. Capture a tested environment and validate installation in isolation. The current global environment's successful imports are not a clean-install guarantee.
- The README and test runner say “production-ready”; the evidence does not support this. Synthetic accuracy measurements are not field accuracy measurements. Test 6 even permits a no-hit branch without failing, and the suite bypasses API conversion, database persistence, real IFC loading, and RTSP.
- `backend/test_setup.py` performs live registration/project creation at import time. Do not collect it unintentionally against a real database; isolate integration fixtures and put script execution behind a main guard.

## Practical readiness by use case

| Use case | Assessment |
|---|---|
| Demonstrate image detection with curated examples | Plausible now; real model loads, but UI/API workflow still needs integration verification |
| Uploaded video detection | Implemented in principle; input bounds, evidence handling, de-duplication, and browser video playback need testing |
| Webcam detection preview | Implemented as sampled image requests; no automatic BIM mapping or saved defect records in that mode |
| Finite RTSP analysis | Implemented, but connection failures are misleading and stream recovery is incomplete |
| Reliable calibrated camera-to-BIM mapping | Blocked by confirmed centroid, calibration, marker-registration, and schema issues |
| Continuous multi-camera unattended monitoring | Not implemented robustly; scheduler, recovery, concurrency controls, retention, and load evidence absent |
| Engineering severity/physical measurement | Not validated; current output is heuristic and pixel-based |

## Repair and acceptance order

1. Fix centroid conversion, marker coordinates/orientation, calibration acceptance, candidate-list schema, and de-duplication persistence. Add integration tests that traverse the real API adapter and storage layer.
2. Fix frontend types and contracts, migration backfill, project authorization, protected media, TLS verification, and explicit model failure behavior. Verify two-organization isolation and fresh/populated migrations in a disposable database.
3. Implement bounded inference jobs, stream failure states, open/read timeouts, reconnect/cancellation, frame freshness checks, stable result storage, and upload/retention limits. Either implement scheduled detection or remove the promise from the UI.
4. Establish model provenance and an independent test set from different structures/sites/capture sessions. Report per-class precision/recall/AP, missed defects, and false alarms on negative frames. Freeze thresholds before final evaluation.
5. Validate calibration with measured intrinsics/distortion, surveyed markers, and independent checkpoints across the image. Report correct-element assignment and 3D error distributions, including failures, edges, occlusions, changed resolution, and camera movement. Verify frontend/backend coordinate transforms on a real IFC model.
6. Run the complete workflow on representative camera hardware. Measure end-to-end latency, analyzed frames per second, RAM/GPU/disk growth, reconnect behavior, and duplicate counts. Include a sustained multi-hour run and simultaneous camera requests.
7. Set acceptance targets appropriate to the B.Tech claim before testing. Use separate targets for detector recall/false alarms, mapping success/error, and runtime availability. Document limitations and retain human review of defect severity.

After these steps, a controlled academic demonstration is a realistic target. A dependable real-site inspection system requires the measured evidence above; successful synthetic tests or a visually convincing UI cannot substitute for it.
