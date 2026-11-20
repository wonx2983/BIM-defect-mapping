# Deployment and acceptance

The application now includes software hardening, but deployment approval requires passing the checks below. The bundled detector has not been re-trained or independently field-validated. Its stored validation metrics are documented in the audit. Automated severity is an estimate, not an engineering measurement.

## Install and verify

Use Python 3.11 and Node 22.13 or newer. Install backend dependencies into a dedicated virtual environment, not the system Python environment. Install `requirements-dev.txt` for tests. Use `npm ci` for the frontend.

Run backend `pytest tests -q`, frontend `npm run typecheck`, `npm run lint`, and `npm run build`. Tests override the remote database configuration; API tests default to in-memory SQLite and support a disposable local PostgreSQL URL in `TEST_DATABASE_URL`. Never point it at a database containing real data: fixtures recreate the schema.

## Database upgrade

Back up the database and verify restoration before a live upgrade. Review `20261118_hardening`: it adds marker rotation, BIM model identity on defects, camera scheduling leases, and append-only defect change history. Existing pre-calibration camera rows receive an `uncalibrated` default. Historical water-seepage defects remain readable. Existing mapped defects have no model ID: review and remap them to an explicit model version; do not guess which model they belong to.

Run `alembic upgrade head` in the backend environment during a controlled maintenance window. No migration has been applied to the user's remote database by this task. The `/ready` endpoint returns 503 until the expected migration and model are available; `/health` is a liveness endpoint only.

## Hosting

`compose.production.yml` packages frontend, backend, and a separate scheduled camera worker. Copy `.env.production.example` to `.env.production`, populate actual connection settings and a randomly generated JWT secret, and configure HTTPS origins and exact allowed camera hosts. S3 mode is deliberately rejected: this release supports private local storage on the shared persistent volume. External database TLS uses certificate verification.

The frontend port binds to loopback. Put it behind an HTTPS reverse proxy with an upload ceiling (500 MB maximum), authentication rate limits, a connection limit, and timeouts appropriate to bounded video requests (up to ten minutes). Do not expose backend port 8000 publicly. Set a restrictive network egress policy so the worker can reach only the database and approved camera addresses; hostname allowlisting alone is not a network isolation boundary. Keep RTSP credentials in a restricted deployment and rotate them if previously exposed.

Build with `docker compose -f compose.production.yml build`. Review the image and dependency scan results before starting it. Docker builds and a live HTTPS deployment are separate acceptance checks; source files alone do not prove them successful. The internal backend URL is baked into Next.js rewrites during the build.

## Cameras and calibration

Register one or more visible markers against the same BIM model. Enter surveyed IFC-world coordinates in metres, surface normals, and printed-marker rotation. The default local marker basis is constructed in `pose_solver.transform_object_points_to_world`; rotation is around the outward normal. Use measured lens intrinsics/distortion for quantitative work. FOV-derived intrinsics are approximate. Verify independent surveyed checkpoints across the entire image, not only marker reprojection error.

Calibration rejects fits above two pixels and insufficient marker evidence. Source/model/FOV/resolution changes invalidate calibration and disable scheduling. A scheduled worker must actually be running; enabling a camera flag alone does not start a process. The worker uses persisted claims, retries on the configured interval, and records failure status. It performs finite inspection batches, not a low-latency continuous stream. Confirm reconnection, movement, stale-frame, multiple-camera, and prolonged outage behavior on actual hardware.

## Evidence and retention

Uploads are project-scoped and authorized. Browser asset requests use an HttpOnly read-only media cookie; API mutations require a bearer token. New video result manifests survive backend restarts and expire after seven days. Uploaded evidence is not automatically deleted: set an explicit retention policy and back up the persistent volume alongside the database. Monitor disk capacity; do not delete files referenced by retained inspections. Failed/aborted jobs can leave unreferenced evidence, which must be reviewed by retention tooling before deletion.

The CSV report exports observations and includes formula-injection protection. Defect mutations are recorded transactionally in the audit table. Audit rows use the same database, so use a database role that restricts direct alteration and external backups if tamper evidence is required. BCF export remains outside this release; the UI no longer promises it as an available action.

## Required field acceptance

1. Freeze a representative test set split by site/capture session, including negative concrete images, shadows, joints, cables, stains, blur, and varied lighting. Report per-class precision/recall/AP and false alarms.
2. Verify model provenance, threshold selection, and camera resolution. Keep the stronger earlier training CSV row separate from the actual bundled checkpoint's metrics.
3. Measure correct-element assignment, mapping error distributions, duplicate behavior, and failures against surveyed ground truth. Include nearby distinct defects and boxes crossing structural edges.
4. Measure end-to-end latency and memory/disk growth under the intended number of simultaneous cameras, including a multi-hour run and network interruptions.
5. Verify authorization with two organizations, backup restoration, TLS, HTTPS cookie behavior, migration recovery, and the production container build.

Do not call the installation production-validated until these checks have documented acceptance results.

## Verification record (2026-11-20)

The local frontend production build completed successfully. Subsequent lint and TypeScript checks passed after the last unused-variable cleanup. The npm production dependency audit reported zero known vulnerabilities; its snapshot is `npm-audit-runtime.json`.

Fresh PostgreSQL migrations and an upgrade containing an existing pre-calibration camera row passed on a disposable local PostgreSQL 17 instance. No remote database was migrated. The final regression suite passed all 34 tests against PostgreSQL with the patched Python packages, including password and JWT validation. The bundled YOLO model also loaded and processed a 640 x 480 blank image successfully (zero detections); this verifies execution, not detection accuracy.

The direct Python runtime dependency scan, including Starlette, Cryptography and AnyIO, reported no known vulnerabilities after patching (`python-audit-runtime.json`). This is not a full transitive dependency or container scan. Unpinned package entries were checked at their locally installed versions; reproduce scans after resolving a clean deployment environment. Python packages for verification were installed in an isolated project directory; unrelated global packages were not upgraded. New passwords use PBKDF2-SHA256 without bcrypt's input truncation, while existing bcrypt hashes remain verifiable. JWTs now use PyJWT and require expiration, subject and token type.

Still unverified: a fresh full dependency installation in the production container, HTTPS deployment, browser interaction across all workflows, real RTSP hardware, multi-camera soak tests, and independent site accuracy. The bundled checkpoint's recorded recall is approximately 51%; severity remains heuristic without a trained checkpoint. These are release acceptance gaps, not claims that software regression tests can resolve.
