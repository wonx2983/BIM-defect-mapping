# DefectSync simulation evidence

Open [index.html](index.html) locally for the report, or play [simulation.mp4](simulation.mp4) for the captioned walkthrough. Keep the files together so the report can load the original camera frames and the video.

The experiment renders a fixed virtual camera view from the uploaded Schependomlaan IFC. It shows one virtual ArUco marker and two simulated wall cracks, C3 and C4. The experiment records the YOLO outputs separately from the BIM mapper's results. Both cracks were detected in this selected demonstration. General detection accuracy requires a separate evaluation on representative site data. The clean control has the same geometry, viewpoint and marker without the simulated cracks.

- `execution.txt` records the completed run.
- `results.json` contains the IFC and weights SHA-256 hashes, camera and marker geometry, calibration results, YOLO boxes, and matched IFC locations.
- `mapping.csv` gives the reference and recovered world positions, IFC GUIDs, and error per reference point.
- The numbered PNGs are the inputs and output overlays. The MP4 is assembled from these saved frames as a presentation. It is not a CCTV recording.

From the repository's `backend` directory, with its Python dependencies installed, run:

```powershell
python run_mapping_simulation.py --ifc "<path to your Schependomlaan IFC>" --out ../runs/bim-simulation --crack-ids C3 C4
python present_mapping_simulation.py ../runs/bim-simulation
```

The presentation script uses FFmpeg and Windows Segoe UI fonts. The experimental result is software evidence from one simulated viewpoint. Live transport, physical calibration tolerances, and field detection accuracy need separate tests.

## Detector evaluation on the saved frames

[Detector evaluation](detector-evaluation.json) reruns the bundled application detector on the original positive and clean frames. Its [label manifest](detector-evaluation-manifest.json) contains the two crack boxes from the simulation ground truth and an empty label list for the clean frame. At confidence 0.25 and matching IoU 0.50, the evaluator recorded 2 true positives, 5 false positives and 0 misses across the two images. All five false positives were classified as efflorescence, including three on the clean frame. These results cover one virtual viewpoint and one labelled defect class.

From `backend`, rerun against a new output path:

```bash
python -m ml.evaluate_detector \
  --manifest ../runs/bim-simulation/detector-evaluation-manifest.json \
  --out /tmp/defectsync-simulation-evaluation.json
```

A separate video smoke test encoded four copies of the positive frame at 4 fps as an MJPEG clip and ran the bundled detector on every frame. It produced 22 frame detections and eight fixed-camera sighting groups with the default two-second gap and 0.50 IoU. This checks decoding and repeat grouping. Some groups contain false detections, so the group count cannot be interpreted as the physical crack count.
