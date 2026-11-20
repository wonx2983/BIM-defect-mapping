"""Compare repeat confirmation policies on controlled replays of the saved BIM frames."""

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2

from ml.evaluate_detector import metrics, score_image
from ml.inference.detector import DefectDetector
from ml.inference.video_processor import process_video_file


def evaluate(manifest: Path, weights: Path) -> dict:
    source = json.loads(manifest.read_text())["images"]
    positive, = [entry for entry in source if entry["labels"]]
    clean, = [entry for entry in source if not entry["labels"]]
    positive_frame = cv2.imread(str(manifest.parent / positive["image"]))
    clean_frame = cv2.imread(str(manifest.parent / clean["image"]))
    if positive_frame is None or clean_frame is None or positive_frame.shape != clean_frame.shape:
        raise ValueError("Replay requires readable positive and clean frames of the same size")
    height, width = positive_frame.shape[:2]
    detector = DefectDetector(weights)
    cases = []
    with TemporaryDirectory(prefix="defectsync-replay-") as temp:
        for name, frames, labels in (
            ("repeated_cracks", [positive_frame] * 4, positive["labels"]),
            ("cracks_in_one_sample", [positive_frame] + [clean_frame] * 3, positive["labels"]),
            ("clean_replay", [clean_frame] * 4, clean["labels"]),
        ):
            path = Path(temp) / f"{name}.avi"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 4, (width, height))
            try:
                if not writer.isOpened():
                    raise RuntimeError("MJPEG writer unavailable")
                for frame in frames:
                    writer.write(frame)
            finally:
                writer.release()
            result = process_video_file(str(path), detector, frame_skip=1,
                                        generate_annotated=False, fixed_camera=True)
            policies = {}
            for minimum in (1, 2):
                result.minimum_sightings = minimum
                tracks = result.review_tracks
                predictions = [
                    {**track.summary(), "bbox_pixels": track.best_detection.bbox_pixels}
                    for track in tracks
                ]
                scored = score_image(predictions, labels, 0.50)
                policies[str(minimum)] = {
                    "saved_candidates": len(tracks),
                    **metrics(len(scored["matches"]), len(scored["false_positives"]), len(scored["misses"])),
                    "matched_confirmation_delay_ms": [
                        match["prediction"]["second_seen_ms"] - match["prediction"]["first_seen_ms"]
                        for match in scored["matches"]
                        if minimum == 2
                    ],
                }
            cases.append({
                "case": name, "sampled_frames": result.processed_frames,
                "frame_detections": result.total_detections,
                "policies_by_minimum_sightings": policies,
                "tracks": [track.summary() for track in result.tracks],
            })
    return {
        "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "fps": 4, "codec": "MJPG", "frame_skip": 1,
        "confidence_threshold": detector.confidence_threshold,
        "matching_iou": 0.50, "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--weights", type=Path, default=Path("ml/models/defect_detector.pt"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.manifest, args.weights)
    with args.out.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    for case in report["cases"]:
        print(case["case"], case["policies_by_minimum_sightings"])


if __name__ == "__main__":
    main()
