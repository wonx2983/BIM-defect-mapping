from types import SimpleNamespace

from PIL import Image
import torch

from ml.inference.detector import DefectDetector
from ml.inference.tiling import tile_regions


def test_tiles_cover_large_frame_with_overlap_and_stay_in_budget():
    regions = tile_regions(3840, 1080, tile_size=256, overlap=.20, limit=16)
    assert 1 < len(regions) <= 16
    for a, b, boundary in ((0, 2, 3840), (1, 3, 1080)):
        intervals = sorted({(r[a], r[b]) for r in regions})
        assert intervals[0][0] == 0 and intervals[-1][1] == boundary
        assert all(end > next_start for (_, end), (next_start, _) in zip(intervals, intervals[1:]))


def test_overlap_boxes_are_deduplicated_after_frame_coordinate_translation():
    detector = DefectDetector.__new__(DefectDetector)
    detector.tile_inference = True
    detector.tile_size = 128
    detector.tile_overlap = .5
    detector.max_tiles = 4
    detector.confidence_threshold = .25
    detector.image_size = 640
    detector.device = "cpu"
    detector.severity_model = None

    def result(rows):
        return SimpleNamespace(boxes=SimpleNamespace(data=torch.tensor(rows).reshape(-1, 6)))

    def fake_yolo(images, **_):
        if isinstance(images, Image.Image):
            return [result([])]
        assert len(images) == 3
        return [
            result([[113, 32, 128, 52, .95, 0]]),  # Partial crack, clipped at tile edge
            result([[65, 32, 95, 52, .80, 0], [65, 32, 95, 52, .70, 1]]),
            result([]),
        ]

    detector.yolo = fake_yolo
    result = detector._predict(Image.new("RGB", (224, 128)))
    assert [d.defect_class for d in result.detections] == ["crack", "spalling"]
    assert result.detections[0].bbox_pixels == {"x1": 113, "y1": 32, "x2": 143, "y2": 52}
    assert result.detections[0].bbox["x"] == round(113 / 224, 4)
