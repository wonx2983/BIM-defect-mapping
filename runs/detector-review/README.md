# Detector and inspection evidence

## Input-size comparison on real crack images

The same bundled checkpoint and confidence threshold (0.25) were used for both input sizes. The comparison used a reproducible random sample of 48 image/mask pairs from the authors' 237-image DeepCrack test split, with one warm-up per size. The boxes were scored in the original image coordinates. A hit here means at least one predicted crack box overlaps at least one annotated crack pixel.

| Detector input | Images with a crack-mask hit | Median share of annotated crack pixels covered | Median share of image covered by crack boxes | Median CPU inference |
| --- | ---: | ---: | ---: | ---: |
| 640 px | 40/48 | 96.9% | 45.2% | 123 ms |
| 960 px | 28/48 | 38.0% | 16.0% | 260 ms |

Keep 640 px as the application default. This is a paired input-size experiment, with no weight changes. Large boxes can score high on mask coverage. The sample contains crack-positive images only, so the experiment measures neither false-alert rates on real clean images nor seven-class performance. Training overlap could not be checked against the missing training manifest. These metrics also differ from box IoU and mAP.

[DeepCrack dataset and citation](https://github.com/yhlleo/DeepCrack) · [Per-image measurements](deepcrack.json)

## Crack-negative check on real concrete crops

The 640 px application detector at confidence 0.25 emitted **zero crack boxes on 64 crops** from the METU dataset's crack-negative class. The evaluation covers crack alerts only because the dataset does not label the other six defect classes. The crop set comes from a different source than the DeepCrack positives. Keep the two results separate when reporting performance. The original training manifest and the sampled crops' capture-session assignments were unavailable.

To reproduce, use version 2 of the authors' archive (SHA-256 `08d7dc505a4f5a0330cee2fa2a1ae4b5b4f98bcffd0549b774caf7959bb1f02f`). Sort the 20,000 `Negative/*.jpg` member names, select 64 with `random.Random(20261121).sample(names, 64)`, and sort the selection. Create an evaluator manifest with those member paths relative to the manifest, `labels: []`, and session `metu-negative-source-sessions-unknown` for each. Run `python -m ml.evaluate_detector --manifest <manifest> --class crack --out <new-output-path>` from `backend`. The report lists every sampled image and hash.

[METU dataset and citation](https://data.mendeley.com/datasets/5y9wdsg2zt/2) · [Per-image measurements](metu-crack-negative.json)

## Repeat confirmation on controlled video

Fixed-camera upload has an optional rule that requires a group to appear in two sampled frames before the app saves it to the project. The result keeps the raw frame evidence and the groups that did not qualify. Same-class association is based on box overlap. The two-second window is based on video time, and frames spaced farther apart cannot qualify.

The same bundled checkpoint processed each replay once. The two policies used the same detections and compared the best frame from each eligible group with the known labels at same-class IoU ≥0.50.

| Four-frame replay at 4 fps | Save after one sighting | Save after two sightings |
| --- | --- | --- |
| Two cracks visible throughout | 2 matches, 6 false candidates | 2 matches, 3 false candidates |
| Two cracks visible in one sample | 1 match, 7 false candidates, 1 miss | 0 matches, 5 false candidates, 2 misses |
| Clean control throughout | 9 false candidates | 5 false candidates |

Repeat confirmation delayed eligibility by 250 ms of video time for each matched crack in the sustained case. This value describes the sample interval, not wall-clock alert latency. Some false candidates appeared repeatedly, and brief true detections can be withheld. The option defaults off. The replay uses repeated synthetic frames and should be followed by testing on fixed site cameras.

[Replay measurements](video-confirmation.json) · [Ground-truth frame labels](../bim-simulation/detector-evaluation-manifest.json)

## Reproduce

Use the application Python environment. Obtain the DeepCrack archive from the authors' repository and compare its SHA-256 with the stored report. Run from `backend`, choosing new output paths each time.

```bash
python -m ml.evaluate_crack_masks \
  --archive /path/to/DeepCrack.zip --sample-count 48 \
  --out /tmp/defectsync-deepcrack-results.json

python -m ml.evaluate_video_confirmation \
  --manifest ../runs/bim-simulation/detector-evaluation-manifest.json \
  --out /tmp/defectsync-confirmation-results.json
```

## Inspection handoff

A manually triggered calibrated camera scan now saves evidence for a ray miss as an unmapped observation. The record is linked to the camera's IFC model and appears under **Unmapped**, where a reviewer can inspect the frame before placing a pin. Scheduled scans continue to save mapped results and count ray misses without automatically creating unmapped records.
