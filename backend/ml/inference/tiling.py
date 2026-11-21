"""Frame tiles and duplicate suppression in original image coordinates."""

from dataclasses import dataclass
from math import ceil

import numpy as np


@dataclass(frozen=True)
class FrameBox:
    class_id: int
    confidence: float
    xyxy: tuple[float, float, float, float]
    clipped: bool = False


def tile_regions(width: int, height: int, tile_size: int, overlap: float, limit: int):
    """Cover the frame with evenly spaced tiles, enlarging tiles to respect the budget."""
    def count(length, size):
        return 1 + ceil(max(0, length - size) / max(1, int(size * (1 - overlap))))

    lo, hi = min(tile_size, max(width, height)), max(width, height)
    while lo < hi:
        mid = (lo + hi) // 2
        if count(width, mid) * count(height, mid) <= limit:
            hi = mid
        else:
            lo = mid + 1
    size = lo

    def origins(length):
        last = max(0, length - size)
        steps = count(length, size) - 1
        return [round(i * last / steps) for i in range(steps + 1)] if steps else [0]

    return [(x, y, min(x + size, width), min(y + size, height))
            for y in origins(height) for x in origins(width)]


def suppress_duplicates(boxes: list[FrameBox]) -> list[FrameBox]:
    """Use class-aware NMS and tolerate tile-edge partial duplicates."""
    by_class: dict[int, list[FrameBox]] = {}
    for box in boxes:
        by_class.setdefault(box.class_id, []).append(box)
    keep = []
    for candidates in by_class.values():
        candidates.sort(key=lambda b: (not b.clipped, b.confidence), reverse=True)
        coordinates = np.asarray([b.xyxy for b in candidates], dtype=np.float64)
        clipped = np.asarray([b.clipped for b in candidates])
        sizes = coordinates[:, 2:] - coordinates[:, :2]
        areas = np.prod(sizes, axis=1)
        active = np.arange(len(candidates))
        while len(active):
            first, active = active[0], active[1:]
            keep.append(candidates[first])
            lo = np.maximum(coordinates[first, :2], coordinates[active, :2])
            hi = np.minimum(coordinates[first, 2:], coordinates[active, 2:])
            intersection = np.prod(np.maximum(0, hi - lo), axis=1)
            union = areas[first] + areas[active] - intersection
            smaller = np.minimum(areas[first], areas[active])
            suppress = (intersection >= .5 * union) | (
                (clipped[first] | clipped[active]) & (intersection >= .75 * smaller)
            )
            active = active[~suppress]
    return sorted(keep, key=lambda b: b.confidence, reverse=True)
