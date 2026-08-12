"""Download a concrete defect dataset from Roboflow Universe.

Downloads the CSEE Damage Segmentation dataset which includes:
  crack, efflorescence, rebar, rust, spalling, and more.

This script requires a free Roboflow API key:
  1. Sign up at https://app.roboflow.com (free, use Google/GitHub)
  2. Go to Settings > API Keys > Copy your API key
  3. Run: python -m ml.training.download_dataset --api-key YOUR_KEY

Or set the environment variable:
  set ROBOFLOW_API_KEY=YOUR_KEY

Usage:
    python -m ml.training.download_dataset --api-key YOUR_KEY
    python -m ml.training.download_dataset --sample-only
"""

import argparse
import os
import sys
from pathlib import Path


def download_roboflow_dataset(api_key: str, output_dir: Path) -> bool:
    """Download a multi-class concrete defect dataset from Roboflow."""
    try:
        from roboflow import Roboflow

        print("Connecting to Roboflow...")
        rf = Roboflow(api_key=api_key)

        # Try the CSEE damage dataset (multi-class: crack, rebar, rust, spalling)
        datasets_to_try = [
            ("university-bswxt", "crack-bphdr", 2, "Concrete crack multi-class"),
            ("shm", "concrete-defect-detection", 1, "SHM Concrete Defects"),
        ]

        for workspace, project_name, version_num, desc in datasets_to_try:
            try:
                print(f"Trying dataset: {desc}...")
                project = rf.workspace(workspace).project(project_name)
                version = project.version(version_num)
                dataset = version.download(
                    "yolov11",
                    location=str(output_dir),
                    overwrite=True,
                )
                print(f"Successfully downloaded: {desc}")
                print(f"Location: {output_dir}")

                # Verify the download
                data_yaml = output_dir / "data.yaml"
                if data_yaml.exists():
                    print(f"data.yaml found: {data_yaml}")
                    with open(data_yaml) as f:
                        print(f"Dataset config:\n{f.read()}")
                return True
            except Exception as e:
                print(f"  Failed: {e}")
                continue

        print("All dataset downloads failed.")
        return False

    except ImportError:
        print("ERROR: roboflow not installed. Run: pip install roboflow")
        return False


def create_sample_dataset(output_dir: Path) -> None:
    """Create a minimal placeholder dataset for pipeline testing."""
    print("Creating sample dataset structure...")

    classes = ["crack", "spalling", "exposed_rebar", "corrosion", "water_seepage", "honeycombing"]

    for split in ["train", "valid"]:
        img_dir = output_dir / split / "images"
        lbl_dir = output_dir / split / "labels"
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        for i, cls in enumerate(classes):
            try:
                from PIL import Image
                img = Image.new("RGB", (640, 640), color=(128, 128, 128))
                img.save(str(img_dir / f"{cls}_sample_{split}.jpg"))
            except ImportError:
                (img_dir / f"{cls}_sample_{split}.jpg").touch()

            with open(lbl_dir / f"{cls}_sample_{split}.txt", "w") as f:
                f.write(f"{i} 0.5 0.5 0.3 0.3\n")

    data_yaml = output_dir / "data.yaml"
    data_yaml.write_text(
        f"path: {output_dir.resolve()}\n"
        f"train: train/images\n"
        f"val: valid/images\n"
        f"\n"
        f"nc: {len(classes)}\n"
        f"names: {classes}\n"
    )

    print(f"Sample dataset created at: {output_dir}")
    print()
    print("This is a PLACEHOLDER for pipeline testing only.")
    print("For real training, get a proper dataset:")
    print()
    print("  OPTION A (Recommended): Roboflow")
    print("    1. Sign up free at https://app.roboflow.com")
    print("    2. Go to Settings > API Keys")
    print("    3. Run: python -m ml.training.download_dataset --api-key YOUR_KEY")
    print()
    print("  OPTION B: Manual download")
    print("    1. Go to https://universe.roboflow.com/search?q=concrete+defect")
    print("    2. Pick a dataset with 1000+ images")
    print("    3. Download in YOLOv11 format")
    print(f"    4. Extract to: {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download concrete defect dataset")
    parser.add_argument("--api-key", type=str, default=None, help="Roboflow API key")
    parser.add_argument("--output", type=str, default="ml/data/defects", help="Output directory")
    parser.add_argument("--sample-only", action="store_true", help="Create sample dataset only")
    args = parser.parse_args()

    backend_root = Path(__file__).resolve().parents[2]
    output_dir = backend_root / args.output

    if args.sample_only:
        create_sample_dataset(output_dir)
        return

    api_key = args.api_key or os.environ.get("ROBOFLOW_API_KEY")

    print("=" * 55)
    print("DefectSync — Dataset Download")
    print("=" * 55)

    if not api_key:
        print()
        print("No API key provided. To download a real dataset:")
        print("  1. Sign up free at https://app.roboflow.com")
        print("  2. Go to Settings > Roboflow API > Private API Key")
        print("  3. Re-run: python -m ml.training.download_dataset --api-key YOUR_KEY")
        print()
        print("Creating sample dataset for now...")
        create_sample_dataset(output_dir)
        return

    if download_roboflow_dataset(api_key, output_dir):
        print()
        print("Dataset ready. Start training with:")
        print(f"  python -m ml.training.train_detector --data {output_dir / 'data.yaml'}")
    else:
        print("Falling back to sample dataset...")
        create_sample_dataset(output_dir)


if __name__ == "__main__":
    main()
