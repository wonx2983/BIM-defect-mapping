"""Compare detector input sizes on a deterministic sample of the DeepCrack test split."""

import argparse
import hashlib
import io
import json
import random
from importlib.metadata import version
from pathlib import Path
from statistics import median
from zipfile import ZipFile

import numpy as np
from PIL import Image

from ml.inference.detector import DefectDetector


def compare(archive_path: Path, weights: Path, sample_count: int, device: str) -> dict:
    image_sizes = (640, 960)
    detector = DefectDetector(weights, device=device)
    with ZipFile(archive_path) as archive:
        files = sorted(name for name in archive.namelist()
                       if name.startswith("test_img/") and name.lower().endswith((".jpg", ".png")))
        if len(files) < sample_count:
            raise ValueError(f"Expected at least {sample_count} test images")
        selected = sorted(random.Random(20261121).sample(files, sample_count))
        rows = []
        for name in selected:
            mask_name = f"test_lab/{Path(name).stem}.png"
            with Image.open(io.BytesIO(archive.read(name))) as source:
                image = source.convert("RGB")
            with Image.open(io.BytesIO(archive.read(mask_name))) as annotation:
                mask = np.asarray(annotation.convert("L")) > 127
            if mask.shape != (image.height, image.width):
                raise ValueError(f"Image and mask dimensions differ for {name}")
            results = {}
            for size in image_sizes:
                detector.image_size = size
                if not rows:
                    detector.predict(image)  # Warm each input size before timing.
                inference = detector.predict(image)
                covered = np.zeros_like(mask)
                crack_boxes = []
                for detection in inference.detections:
                    if detection.defect_class != "crack":
                        continue
                    box = detection.bbox_pixels
                    covered[box["y1"]:box["y2"], box["x1"]:box["x2"]] = True
                    crack_boxes.append({"bbox_pixels": box, "confidence": detection.confidence})
                results[str(size)] = {
                    "crack_boxes": crack_boxes,
                    "covered_crack_pixels": int(np.count_nonzero(covered & mask)),
                    "box_coverage_fraction": float(covered.mean()),
                    "inference_ms": round(inference.inference_time_ms, 2),
                }
            rows.append({"image": name, "mask_pixels": int(mask.sum()), "results": results})

    summary = {}
    for size in image_sizes:
        positives = [row for row in rows if row["mask_pixels"]]
        negatives = [row for row in rows if not row["mask_pixels"]]
        summary[str(size)] = {
            "positive_images": len(positives),
            "positive_images_with_crack_box": sum(bool(row["results"][str(size)]["crack_boxes"]) for row in positives),
            "positive_images_with_mask_overlap": sum(row["results"][str(size)]["covered_crack_pixels"] > 0 for row in positives),
            "negative_images": len(negatives),
            "negative_images_with_crack_box": sum(bool(row["results"][str(size)]["crack_boxes"]) for row in negatives),
            "median_positive_image_mask_coverage": median(
                row["results"][str(size)]["covered_crack_pixels"] / row["mask_pixels"] for row in positives
            ) if positives else None,
            "median_positive_image_box_coverage": median(
                row["results"][str(size)]["box_coverage_fraction"] for row in positives
            ) if positives else None,
            "median_inference_ms": median(row["results"][str(size)]["inference_ms"] for row in rows),
        }
    return {
        "dataset": "Liu et al. DeepCrack, authors' test split",
        "archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
        "available_test_images": len(files), "sample_images": len(rows), "sample_seed": 20261121,
        "confidence_threshold": detector.confidence_threshold, "device": device,
        "runtime": {"torch": version("torch"), "ultralytics": version("ultralytics")},
        "summary": summary, "images": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sample-count", type=int, default=48)
    parser.add_argument("--weights", type=Path, default=Path("ml/models/defect_detector.pt"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    if args.sample_count < 1:
        parser.error("Sample count must be positive")
    report = compare(args.archive, args.weights, args.sample_count, args.device)
    with args.out.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
