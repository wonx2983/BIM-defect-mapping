"""Severity classifier training — ResNet-18 for 4-class severity grading.

Takes cropped defect regions from the YOLO detector and classifies them
into: Low, Medium, High, Critical.

This is a secondary classifier that runs AFTER YOLO detection.
The YOLO detector finds the defect and draws a bounding box.
This model zooms into that box and grades the severity.

Usage:
    python -m ml.training.train_severity --data ml/data/severity --epochs 30

Dataset structure for severity:
    ml/data/severity/
        train/
            low/       (cropped defect images graded as low)
            medium/
            high/
            critical/
        valid/
            low/
            medium/
            high/
            critical/

You can generate this dataset by:
    1. Running the YOLO detector on site images to get bounding boxes
    2. Cropping each detected defect region
    3. Manually labeling each crop as low/medium/high/critical
    4. Placing them in the folder structure above
"""

import argparse
import sys
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms


SEVERITY_CLASSES = ["low", "medium", "high", "critical"]
IMG_SIZE = 224


def get_transforms(is_train: bool) -> transforms.Compose:
    """Get data augmentation transforms for severity classification."""
    if is_train:
        return transforms.Compose([
            transforms.RandomResizedCrop(IMG_SIZE, scale=(0.7, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomVerticalFlip(p=0.3),
            transforms.RandomRotation(20),
            transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2, hue=0.05),
            transforms.RandomGrayscale(p=0.1),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
    else:
        return transforms.Compose([
            transforms.Resize(int(IMG_SIZE * 1.15)),
            transforms.CenterCrop(IMG_SIZE),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])


def build_model(num_classes: int = 4, pretrained: bool = True) -> nn.Module:
    """Build a ResNet-18 classifier with custom head for severity grading.

    ResNet-18 is chosen for its small size (~11M params), fast inference,
    and strong performance on texture/pattern recognition tasks like
    distinguishing crack severity levels.
    """
    model = models.resnet18(weights="IMAGENET1K_V1" if pretrained else None)
    num_features = model.fc.in_features
    model.fc = nn.Sequential(
        nn.Dropout(0.3),
        nn.Linear(num_features, 128),
        nn.ReLU(inplace=True),
        nn.Dropout(0.2),
        nn.Linear(128, num_classes),
    )
    return model


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: optim.Optimizer,
    device: torch.device,
) -> tuple[float, float]:
    """Train for one epoch, return (loss, accuracy)."""
    model.train()
    running_loss = 0.0
    correct = 0
    total = 0

    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        running_loss += loss.item() * images.size(0)
        _, predicted = outputs.max(1)
        total += labels.size(0)
        correct += predicted.eq(labels).sum().item()

    return running_loss / total, correct / total


@torch.no_grad()
def validate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> tuple[float, float]:
    """Validate model, return (loss, accuracy)."""
    model.eval()
    running_loss = 0.0
    correct = 0
    total = 0

    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        outputs = model(images)
        loss = criterion(outputs, labels)

        running_loss += loss.item() * images.size(0)
        _, predicted = outputs.max(1)
        total += labels.size(0)
        correct += predicted.eq(labels).sum().item()

    return running_loss / total, correct / total


def main() -> None:
    parser = argparse.ArgumentParser(description="Train severity classifier")
    parser.add_argument("--data", type=str, default="ml/data/severity", help="Dataset root")
    parser.add_argument("--epochs", type=int, default=30, help="Training epochs")
    parser.add_argument("--batch", type=int, default=32, help="Batch size")
    parser.add_argument("--lr", type=float, default=0.001, help="Learning rate")
    parser.add_argument("--device", type=str, default="auto", help="Device: auto, cuda, cpu")
    parser.add_argument("--output", type=str, default="ml/models/severity_classifier.pt")
    args = parser.parse_args()

    # Resolve paths
    backend_root = Path(__file__).resolve().parents[2]
    data_path = backend_root / args.data
    output_path = backend_root / args.output

    if not (data_path / "train").exists():
        print(f"ERROR: Training data not found at {data_path / 'train'}")
        print("Create the severity dataset with folders: low, medium, high, critical")
        sys.exit(1)

    # Device selection
    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)

    print("=" * 60)
    print("DefectSync — Severity Classifier Training")
    print("=" * 60)
    print(f"  Dataset:  {data_path}")
    print(f"  Device:   {device}")
    print(f"  Epochs:   {args.epochs}")
    print(f"  Batch:    {args.batch}")
    print(f"  LR:       {args.lr}")
    print("=" * 60)

    # Datasets
    train_dataset = datasets.ImageFolder(
        str(data_path / "train"), transform=get_transforms(is_train=True)
    )
    val_dataset = datasets.ImageFolder(
        str(data_path / "valid"), transform=get_transforms(is_train=False)
    )

    print(f"  Train samples: {len(train_dataset)}")
    print(f"  Val samples:   {len(val_dataset)}")
    print(f"  Classes:       {train_dataset.classes}")

    # Handle class imbalance (critical defects are rare)
    class_counts = [0] * len(SEVERITY_CLASSES)
    for _, label in train_dataset:
        class_counts[label] += 1
    class_weights = torch.tensor(
        [1.0 / max(c, 1) for c in class_counts], dtype=torch.float32
    ).to(device)
    class_weights = class_weights / class_weights.sum() * len(SEVERITY_CLASSES)

    train_loader = DataLoader(
        train_dataset, batch_size=args.batch, shuffle=True, num_workers=2, pin_memory=True
    )
    val_loader = DataLoader(
        val_dataset, batch_size=args.batch, shuffle=False, num_workers=2, pin_memory=True
    )

    # Model
    model = build_model(num_classes=len(SEVERITY_CLASSES)).to(device)
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    # Training loop
    best_val_acc = 0.0
    for epoch in range(1, args.epochs + 1):
        train_loss, train_acc = train_one_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_acc = validate(model, val_loader, criterion, device)
        scheduler.step()

        print(
            f"Epoch {epoch:3d}/{args.epochs} | "
            f"Train Loss: {train_loss:.4f} Acc: {train_acc:.4f} | "
            f"Val Loss: {val_loss:.4f} Acc: {val_acc:.4f}"
        )

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            output_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save({
                "model_state_dict": model.state_dict(),
                "classes": SEVERITY_CLASSES,
                "img_size": IMG_SIZE,
                "val_accuracy": best_val_acc,
                "epoch": epoch,
            }, output_path)
            print(f"  → Saved best model (val_acc={best_val_acc:.4f})")

    print(f"\nBest validation accuracy: {best_val_acc:.4f}")
    print(f"Model saved to: {output_path}")


if __name__ == "__main__":
    main()
