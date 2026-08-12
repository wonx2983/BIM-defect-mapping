"""YOLOv11 training script for 6-class construction defect detection.

Supports automatic resume — if training gets interrupted (Ctrl+C, power loss,
laptop sleep), just re-run the same command and it picks up from the last checkpoint.

Usage:
    # First run — starts from scratch
    python -m ml.training.train_detector --model yolo11s.pt --epochs 50

    # Interrupted? Just re-run — auto-resumes from last checkpoint
    python -m ml.training.train_detector --model yolo11s.pt --epochs 50

    # Force fresh start (ignores existing checkpoints)
    python -m ml.training.train_detector --model yolo11s.pt --epochs 50 --fresh

GTX 1650 (4GB VRAM) recommended settings:
    --model yolo11n.pt or yolo11s.pt
    --batch 8 (reduce to 4 if OOM)
    --imgsz 640
"""

import argparse
import shutil
import sys
from pathlib import Path

from ultralytics import YOLO


def find_last_checkpoint(project: str, name: str) -> Path | None:
    """Find the last saved checkpoint for auto-resume.

    Checks for:
      1. last.pt (YOLO's automatic checkpoint)
      2. Any epoch_N.pt files (from save_period)
    """
    run_dir = Path(project) / name / "weights"
    if not run_dir.exists():
        return None

    last_pt = run_dir / "last.pt"
    if last_pt.exists():
        return last_pt

    # Look for epoch checkpoints
    checkpoints = sorted(run_dir.glob("epoch*.pt"))
    if checkpoints:
        return checkpoints[-1]

    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train YOLOv11 defect detector")
    parser.add_argument(
        "--model", type=str, default="yolo11s.pt",
        help="Base model: yolo11n.pt (fast), yolo11s.pt (balanced), yolo11m.pt (accurate)",
    )
    parser.add_argument(
        "--data", type=str, default="ml/data/defects/data.yaml",
        help="Path to dataset YAML config",
    )
    parser.add_argument("--epochs", type=int, default=50, help="Total training epochs")
    parser.add_argument("--imgsz", type=int, default=640, help="Input image size")
    parser.add_argument(
        "--batch", type=int, default=8,
        help="Batch size (reduce if GPU OOM — try 4 for GTX 1650)",
    )
    parser.add_argument("--device", type=str, default="0", help="Device: 0 (GPU), cpu")
    parser.add_argument("--workers", type=int, default=4, help="Dataloader workers")
    parser.add_argument(
        "--project", type=str, default="ml/runs/detect",
        help="Output directory for training runs",
    )
    parser.add_argument("--name", type=str, default="defect_detector", help="Run name")
    parser.add_argument(
        "--fresh", action="store_true",
        help="Force fresh training (ignore existing checkpoints)",
    )
    parser.add_argument(
        "--export-onnx", action="store_true",
        help="Export to ONNX after training for cross-platform inference",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Resolve data path relative to backend/
    backend_root = Path(__file__).resolve().parents[2]
    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = backend_root / data_path

    if not data_path.exists():
        print(f"ERROR: Dataset config not found at {data_path}")
        print()
        print("Download a dataset first:")
        print("  python -m ml.training.download_dataset")
        print()
        print("Or download manually from https://universe.roboflow.com")
        sys.exit(1)

    # Check for existing checkpoint (auto-resume)
    resume_from = None
    if not args.fresh:
        checkpoint = find_last_checkpoint(args.project, args.name)
        if checkpoint:
            resume_from = checkpoint
            print(f"Found checkpoint: {checkpoint}")
            print("Resuming training automatically.")
            print("(Use --fresh to start over)")
            print()

    print("=" * 60)
    print("DefectSync — YOLOv11 Defect Detector Training")
    print("=" * 60)
    print(f"  Model:      {args.model}")
    print(f"  Dataset:    {data_path}")
    print(f"  Epochs:     {args.epochs}")
    print(f"  Image Size: {args.imgsz}")
    print(f"  Batch Size: {args.batch}")
    print(f"  Device:     {args.device}")
    print(f"  Resume:     {resume_from or 'No (fresh start)'}")
    print(f"  Output:     {args.project}/{args.name}")
    print("=" * 60)

    if resume_from:
        # Resume from checkpoint
        model = YOLO(str(resume_from))
        results = model.train(resume=True)
    else:
        # Fresh training
        model = YOLO(args.model)
        results = model.train(
            data=str(data_path),
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            device=args.device,
            workers=args.workers,
            project=args.project,
            name=args.name,
            exist_ok=True,# Overwrite existing run dir
            # Augmentation tuned for construction site imagery
            amp=False,  
            hsv_h=0.015,
            hsv_s=0.5,
            hsv_v=0.4,
            degrees=15.0,
            translate=0.1,
            scale=0.5,
            shear=5.0,
            perspective=0.001,
            flipud=0.3,
            fliplr=0.5,
            mosaic=1.0,
            mixup=0.1,
            # Training hyperparameters
            lr0=0.01,
            lrf=0.01,
            warmup_epochs=3,
            weight_decay=0.0005,
            # Checkpointing — saves every 5 epochs for resume safety
            save=True,
            save_period=5,
            plots=True,
            verbose=True,
        )

    print()
    print("=" * 60)
    print("Training Complete")
    print("=" * 60)

    # Copy best weights to the models directory
    best_pt = Path(args.project) / args.name / "weights" / "best.pt"
    if best_pt.exists():
        dest = backend_root / "ml" / "models" / "defect_detector.pt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(best_pt, dest)
        print(f"Best model copied to: {dest}")

        if args.export_onnx:
            print("Exporting to ONNX...")
            best_model = YOLO(str(dest))
            best_model.export(format="onnx", imgsz=args.imgsz)
            print("ONNX export complete.")
    else:
        print(f"WARNING: best.pt not found at {best_pt}")

    print(f"\nResults saved to: {args.project}/{args.name}")
    print("To use: set ML_MODEL_PATH=ml/models/defect_detector.pt in .env")


if __name__ == "__main__":
    main()
