"""Download and merge multi-class concrete defect datasets from Roboflow.

Downloads two datasets and merges them into a single unified 7-class dataset:
  1. DEEP Concrete Defect Detection (~8,900 images, 6 classes)
  2. Pritha Ghosh Honeycomb Detection (~1,925 images, 1 class)

Final unified classes (7):
  0: crack
  1: spalling
  2: exposed_rebar
  3: corrosion
  4: efflorescence
  5: scaling
  6: honeycombing

Requirements:
  pip install roboflow

Usage:
    # Uses ROBOFLOW_API_KEY from .env or environment
    python -m ml.training.download_dataset

    # Or pass the key directly
    python -m ml.training.download_dataset --api-key YOUR_KEY

    # Create a small placeholder dataset for pipeline testing
    python -m ml.training.download_dataset --sample-only
"""

import argparse
import os
import random
import shutil
import sys
import yaml
from pathlib import Path


# ── Our standard 7-class taxonomy ──────────────────────────────────────
STANDARD_CLASSES = [
    "crack",           # 0
    "spalling",        # 1
    "exposed_rebar",   # 2
    "corrosion",       # 3
    "efflorescence",   # 4
    "scaling",         # 5
    "honeycombing",    # 6
]

# ── Name normalization: maps any dataset label → our standard name ─────
# Keys are lowercased for matching.
NAME_MAP = {
    "crack":                    "crack",
    "cracking":                 "crack",
    "cracks":                   "crack",
    "spallation":               "spalling",
    "spalling":                 "spalling",
    "exposed_reinforcement":    "exposed_rebar",
    "exposed reinforcement":    "exposed_rebar",
    "exposed-reinforcement":    "exposed_rebar",
    "exposed_rebar":            "exposed_rebar",
    "rebar":                    "exposed_rebar",
    "corrosionstain":           "corrosion",
    "corrosion":                "corrosion",
    "corrosion_stain":          "corrosion",
    "rust":                     "corrosion",
    "efflorescence":            "efflorescence",
    "scaling":                  "scaling",
    "honeycombing":             "honeycombing",
    "honeycomb":                "honeycombing",
    "honeycomb_concrete":       "honeycombing",
}


def normalize_class_name(raw_name: str) -> str | None:
    """Convert a raw dataset class name to our standard name."""
    key = raw_name.strip().lower().replace(" ", "_").replace("-", "_")
    return NAME_MAP.get(key)


def read_data_yaml(yaml_path: Path) -> dict:
    """Read a YOLO data.yaml and return its contents."""
    with open(yaml_path, "r") as f:
        return yaml.safe_load(f)


def get_class_names_from_yaml(data: dict) -> dict[int, str]:
    """Extract {index: class_name} mapping from data.yaml."""
    names = data.get("names", {})
    if isinstance(names, list):
        return {i: n for i, n in enumerate(names)}
    elif isinstance(names, dict):
        return {int(k): v for k, v in names.items()}
    return {}


def build_remap_table(source_classes: dict[int, str]) -> dict[int, int]:
    """Build a mapping from source class IDs → our standard class IDs.

    Returns:
        Dict mapping source_id → standard_id.
        Classes that don't map to anything are excluded (skipped).
    """
    remap = {}
    for src_id, src_name in source_classes.items():
        std_name = normalize_class_name(src_name)
        if std_name and std_name in STANDARD_CLASSES:
            remap[src_id] = STANDARD_CLASSES.index(std_name)
        else:
            print(f"  WARNING: Skipping unknown class '{src_name}' (id={src_id})")
    return remap


def remap_label_file(label_path: Path, remap: dict[int, int]) -> list[str]:
    """Remap class IDs in a YOLO label file. Returns remapped lines."""
    remapped = []
    with open(label_path, "r") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            src_id = int(parts[0])
            if src_id in remap:
                parts[0] = str(remap[src_id])
                remapped.append(" ".join(parts))
    return remapped


def merge_dataset_into(
    source_dir: Path,
    target_dir: Path,
    remap: dict[int, int],
    prefix: str,
) -> dict[str, int]:
    """Merge a downloaded dataset into the target directory with class remapping.

    Args:
        source_dir: Root of the downloaded dataset (contains train/, valid/, etc.)
        target_dir: Root of our unified dataset
        remap: Class ID remapping table
        prefix: Filename prefix to avoid collisions (e.g., "deep_", "hc_")

    Returns:
        Dict with counts: {"images": N, "labels": N, "skipped": N}
    """
    stats = {"images": 0, "labels": 0, "skipped": 0}

    for split in ["train", "valid", "test"]:
        src_img_dir = source_dir / split / "images"
        src_lbl_dir = source_dir / split / "labels"

        if not src_img_dir.exists():
            continue

        tgt_img_dir = target_dir / split / "images"
        tgt_lbl_dir = target_dir / split / "labels"
        tgt_img_dir.mkdir(parents=True, exist_ok=True)
        tgt_lbl_dir.mkdir(parents=True, exist_ok=True)

        for img_file in src_img_dir.iterdir():
            if not img_file.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
                continue

            # Find matching label file
            lbl_file = src_lbl_dir / (img_file.stem + ".txt")
            if not lbl_file.exists():
                stats["skipped"] += 1
                continue

            # Remap labels
            remapped_lines = remap_label_file(lbl_file, remap)
            if not remapped_lines:
                stats["skipped"] += 1
                continue

            # Copy image with prefix to avoid filename collisions
            new_name = f"{prefix}{img_file.name}"
            shutil.copy2(img_file, tgt_img_dir / new_name)

            # Write remapped label
            new_lbl = tgt_lbl_dir / f"{prefix}{img_file.stem}.txt"
            with open(new_lbl, "w") as f:
                f.write("\n".join(remapped_lines) + "\n")

            stats["images"] += 1
            stats["labels"] += 1

    return stats


def write_unified_data_yaml(output_dir: Path) -> None:
    """Write the final data.yaml with our 7 standard classes."""
    data = {
        "path": str(output_dir.resolve()),
        "train": "train/images",
        "val": "valid/images",
        "test": "test/images",
        "nc": len(STANDARD_CLASSES),
        "names": STANDARD_CLASSES,
    }
    yaml_path = output_dir / "data.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    print(f"\ndata.yaml written to: {yaml_path}")
    print(f"  Classes ({len(STANDARD_CLASSES)}): {STANDARD_CLASSES}")


def download_and_merge(api_key: str, output_dir: Path) -> bool:
    """Download both datasets, remap classes, and merge into one."""
    try:
        from roboflow import Roboflow
    except ImportError:
        print("ERROR: roboflow not installed. Run: pip install roboflow")
        return False

    rf = Roboflow(api_key=api_key)
    tmp_base = output_dir.parent / "_tmp_downloads"

    # ── Dataset 1: DEEP Concrete Defect Detection ──────────────────
    print("=" * 60)
    print("Step 1/3: Downloading DEEP dataset (~8,900 images, 6 classes)")
    print("=" * 60)
    deep_dir = tmp_base / "deep"
    try:
        project = rf.workspace("deep-zqmpp").project("concrete-defect-detection-zuym8-0jcxx")
        version = project.version(1)
        version.download("yolov11", location=str(deep_dir), overwrite=True)
        print("DEEP dataset downloaded successfully.")
    except Exception as e:
        print(f"ERROR downloading DEEP dataset: {e}")
        print("\nTrying alternative format...")
        try:
            version.download("yolov8", location=str(deep_dir), overwrite=True)
            print("DEEP dataset downloaded with YOLOv8 format.")
        except Exception as e2:
            print(f"ERROR: Could not download DEEP dataset: {e2}")
            return False

    # ── Dataset 2: Pritha Ghosh Honeycomb Detection ────────────────
    print()
    print("=" * 60)
    print("Step 2/3: Downloading Honeycombing dataset (~1,925 images)")
    print("=" * 60)
    hc_dir = tmp_base / "honeycomb"
    try:
        project = rf.workspace("pritha-ghosh-xrgsu").project("honeycomb_defect_detection")
        version = project.version(1)
        version.download("yolov11", location=str(hc_dir), overwrite=True)
        print("Honeycombing dataset downloaded successfully.")
    except Exception as e:
        print(f"ERROR downloading Honeycombing dataset: {e}")
        try:
            version.download("yolov8", location=str(hc_dir), overwrite=True)
            print("Honeycombing dataset downloaded with YOLOv8 format.")
        except Exception as e2:
            print(f"ERROR: Could not download Honeycombing dataset: {e2}")
            print("Continuing with DEEP dataset only (6 classes).")
            hc_dir = None

    # ── Step 3: Remap and Merge ────────────────────────────────────
    print()
    print("=" * 60)
    print("Step 3/3: Remapping classes and merging datasets")
    print("=" * 60)

    # Clean output directory
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # Process DEEP dataset
    deep_yaml_candidates = list(deep_dir.rglob("data.yaml"))
    if not deep_yaml_candidates:
        print("ERROR: No data.yaml found in DEEP download.")
        return False

    deep_yaml = deep_yaml_candidates[0]
    deep_data = read_data_yaml(deep_yaml)
    deep_classes = get_class_names_from_yaml(deep_data)
    print(f"\nDEEP classes found: {deep_classes}")

    deep_remap = build_remap_table(deep_classes)
    print(f"DEEP remap table: {deep_remap}")

    # The actual image/label dirs might be inside a subfolder
    deep_root = deep_yaml.parent
    deep_stats = merge_dataset_into(deep_root, output_dir, deep_remap, prefix="deep_")
    print(f"DEEP merged: {deep_stats['images']} images, {deep_stats['skipped']} skipped")

    # Process Honeycombing dataset
    if hc_dir and hc_dir.exists():
        hc_yaml_candidates = list(hc_dir.rglob("data.yaml"))
        if hc_yaml_candidates:
            hc_yaml = hc_yaml_candidates[0]
            hc_data = read_data_yaml(hc_yaml)
            hc_classes = get_class_names_from_yaml(hc_data)
            print(f"\nHoneycombing classes found: {hc_classes}")

            hc_remap = build_remap_table(hc_classes)
            print(f"Honeycombing remap table: {hc_remap}")

            hc_root = hc_yaml.parent
            hc_stats = merge_dataset_into(hc_root, output_dir, hc_remap, prefix="hc_")
            print(f"Honeycombing merged: {hc_stats['images']} images, {hc_stats['skipped']} skipped")
        else:
            print("WARNING: No data.yaml found in Honeycombing download.")

    # Write unified data.yaml
    write_unified_data_yaml(output_dir)

    # Print final summary
    total_train = len(list((output_dir / "train" / "images").glob("*"))) if (output_dir / "train" / "images").exists() else 0
    total_valid = len(list((output_dir / "valid" / "images").glob("*"))) if (output_dir / "valid" / "images").exists() else 0
    total_test = len(list((output_dir / "test" / "images").glob("*"))) if (output_dir / "test" / "images").exists() else 0

    print()
    print("=" * 60)
    print("Dataset Merge Complete!")
    print("=" * 60)
    print(f"  Train:  {total_train} images")
    print(f"  Valid:  {total_valid} images")
    print(f"  Test:   {total_test} images")
    print(f"  Total:  {total_train + total_valid + total_test} images")
    print(f"  Classes: {len(STANDARD_CLASSES)} → {STANDARD_CLASSES}")
    print(f"  Output:  {output_dir}")
    print()

    # Clean up temp downloads
    print("Cleaning up temporary files...")
    if tmp_base.exists():
        shutil.rmtree(tmp_base)
    print("Done.")

    return True


def create_sample_dataset(output_dir: Path) -> None:
    """Create a minimal placeholder dataset for pipeline testing."""
    print("Creating sample dataset structure...")

    for split in ["train", "valid"]:
        img_dir = output_dir / split / "images"
        lbl_dir = output_dir / split / "labels"
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        for i, cls in enumerate(STANDARD_CLASSES):
            try:
                from PIL import Image
                img = Image.new("RGB", (640, 640), color=(128, 128, 128))
                img.save(str(img_dir / f"{cls}_sample_{split}.jpg"))
            except ImportError:
                (img_dir / f"{cls}_sample_{split}.jpg").touch()

            with open(lbl_dir / f"{cls}_sample_{split}.txt", "w") as f:
                f.write(f"{i} 0.5 0.5 0.3 0.3\n")

    write_unified_data_yaml(output_dir)

    print(f"\nSample dataset created at: {output_dir}")
    print("This is a PLACEHOLDER for pipeline testing only.")
    print("For real training, run without --sample-only to download real data.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download and merge multi-class concrete defect datasets"
    )
    parser.add_argument("--api-key", type=str, default=None, help="Roboflow API key")
    parser.add_argument(
        "--output", type=str, default="ml/data/defects",
        help="Output directory for merged dataset",
    )
    parser.add_argument(
        "--sample-only", action="store_true",
        help="Create sample dataset only (no download)",
    )
    args = parser.parse_args()

    backend_root = Path(__file__).resolve().parents[2]
    output_dir = backend_root / args.output

    if args.sample_only:
        create_sample_dataset(output_dir)
        return

    # Try: CLI arg → env var → .env file
    api_key = args.api_key or os.environ.get("ROBOFLOW_API_KEY")

    if not api_key:
        # Try reading from .env file directly
        env_file = backend_root.parent / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.startswith("ROBOFLOW_API_KEY="):
                        api_key = line.strip().split("=", 1)[1]
                        break

    print("=" * 60)
    print("DefectSync — Multi-Class Dataset Download & Merge")
    print("=" * 60)
    print()
    print("Datasets:")
    print("  1. DEEP Concrete Defect Detection (~8,900 images)")
    print("     Classes: Crack, CorrosionStain, Efflorescence,")
    print("              Exposed_reinforcement, Scaling, Spallation")
    print()
    print("  2. Pritha Ghosh Honeycomb Detection (~1,925 images)")
    print("     Classes: Honeycomb")
    print()
    print(f"Output: {output_dir}")
    print(f"Final classes (7): {STANDARD_CLASSES}")
    print()

    if not api_key:
        print("ERROR: No Roboflow API key found.")
        print()
        print("  Option 1: Set in .env → ROBOFLOW_API_KEY=your_key")
        print("  Option 2: Pass via CLI → --api-key your_key")
        print("  Option 3: Set env var  → set ROBOFLOW_API_KEY=your_key")
        print()
        print("Get a free key at: https://app.roboflow.com → Settings → API Keys")
        print()
        print("Falling back to sample dataset...")
        create_sample_dataset(output_dir)
        return

    if download_and_merge(api_key, output_dir):
        print()
        print("Ready to train! Run:")
        print(f"  python -m ml.training.train_detector \\")
        print(f"    --data {output_dir / 'data.yaml'} \\")
        print(f"    --model yolo11s.pt --epochs 50 --batch 4 --fresh")
    else:
        print()
        print("Download failed. Falling back to sample dataset...")
        create_sample_dataset(output_dir)


if __name__ == "__main__":
    main()
