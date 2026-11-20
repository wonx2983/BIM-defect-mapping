"""Score application detections at a fixed operating point on labelled images."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from importlib.metadata import version
from pathlib import Path
from platform import python_version
from statistics import median

from ml.inference.video_tracks import box_iou


def score_image(predictions: list[dict], labels: list[dict], min_iou: float) -> dict:
    """Match in confidence order to the best still-unmatched same-class label."""
    remaining = set(range(len(labels)))
    matched = []
    false_alerts = []
    for prediction in sorted(predictions, key=lambda item: -item["confidence"]):
        candidates = [
            (box_iou(prediction["bbox_pixels"], labels[index]["bbox_pixels"]), index)
            for index in sorted(remaining)
            if prediction["defect_class"] == labels[index]["defect_class"]
        ]
        overlap, best = max(candidates, default=(0, -1), key=lambda pair: pair[0])
        if best != -1 and overlap >= min_iou:
            remaining.remove(best)
            matched.append({"prediction": prediction, "label": labels[best], "iou": overlap})
        else:
            false_alerts.append(prediction)
    return {
        "matches": matched,
        "false_positives": false_alerts,
        "misses": [labels[index] for index in sorted(remaining)],
    }


def metrics(tp: int, fp: int, fn: int) -> dict:
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None,
    }


def summarize(rows: list[dict], classes: list[str]) -> dict:
    counts = defaultdict(Counter)
    for row in rows:
        for match in row["matches"]:
            counts[match["label"]["defect_class"]]["tp"] += 1
        for key, outcome in (("false_positives", "fp"), ("misses", "fn")):
            for item in row[key]:
                counts[item["defect_class"]][outcome] += 1
    totals = sum(counts.values(), Counter())
    negatives = [row for row in rows if not row["labels"]]
    return {
        "images": len(rows),
        "capture_sessions": len({row["session"] for row in rows}),
        "overall": metrics(*(totals[key] for key in ("tp", "fp", "fn"))),
        "by_class": {
            name: metrics(*(counts[name][key] for key in ("tp", "fp", "fn"))) for name in classes
        },
        "clean_images": len(negatives),
        "clean_images_with_alerts": sum(bool(row["false_positives"]) for row in negatives),
        "clean_false_positives": sum(len(row["false_positives"]) for row in negatives),
        "median_inference_ms": median(row["inference_ms"] for row in rows),
    }


def evaluate(manifest: Path, weights: Path, confidence: float, min_iou: float, device: str,
             evaluated_classes: list[str] | None = None) -> dict:
    from PIL import Image
    from ml.inference.detector import CLASS_NAMES, DefectDetector

    manifest_bytes = manifest.read_bytes()
    entries = json.loads(manifest_bytes)["images"]
    if not entries:
        raise ValueError("The manifest must contain at least one labelled image")
    weight_hash = hashlib.sha256(weights.read_bytes()).hexdigest()
    detector = DefectDetector(weights, device=device, confidence_threshold=confidence)
    classes = list(CLASS_NAMES.values())
    if evaluated_classes:
        unknown = set(evaluated_classes) - set(classes)
        if unknown:
            raise ValueError(f"Unknown evaluation classes: {sorted(unknown)}")
        classes = [name for name in classes if name in evaluated_classes]
    seen_hashes = set()
    rows = []
    for entry in entries:
        path = (manifest.parent / entry["image"]).resolve()
        session = entry["session"]
        if not isinstance(session, str) or not session.strip():
            raise ValueError(f"Missing capture session for {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen_hashes:
            raise ValueError(f"Duplicate image in manifest: {path}")
        seen_hashes.add(digest)
        labels = entry["labels"]
        if evaluated_classes:
            labels = [label for label in labels if label["defect_class"] in classes]
        with Image.open(path) as image:
            for label in labels:
                box = label["bbox_pixels"]
                if (label["defect_class"] not in classes
                        or not 0 <= box["x1"] < box["x2"] <= image.width
                        or not 0 <= box["y1"] < box["y2"] <= image.height):
                    raise ValueError(f"Invalid label in {path}: {label}")
            result = detector.predict(image.convert("RGB"))
        predictions = [
            {"defect_class": item.defect_class, "confidence": item.confidence,
             "bbox_pixels": item.bbox_pixels}
            for item in result.detections if item.defect_class in classes
        ]
        rows.append({
            "image": entry["image"], "session": session, "image_sha256": digest,
            "labels": labels, "inference_ms": result.inference_time_ms,
            "width": result.image_width, "height": result.image_height,
            **score_image(predictions, labels, min_iou),
        })
    return {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "weights_sha256": weight_hash,
        "confidence_threshold": confidence,
        "matching_iou_threshold": min_iou,
        "device": device,
        "evaluated_classes": classes,
        "runtime": {"python": python_version(), "torch": version("torch"),
                    "ultralytics": version("ultralytics")},
        "summary": summarize(rows, classes),
        "images": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--weights", type=Path, default=Path("ml/models/defect_detector.pt"))
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--match-iou", type=float, default=0.5)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--class", dest="evaluated_classes", action="append",
                        help="Score only this annotated class; may be repeated")
    args = parser.parse_args()
    if not (0 < args.confidence <= 1 and 0 < args.match_iou <= 1):
        parser.error("Thresholds must be in (0, 1]")
    report = evaluate(args.manifest, args.weights, args.confidence, args.match_iou, args.device, args.evaluated_classes)
    with args.out.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
