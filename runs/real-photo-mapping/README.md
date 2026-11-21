# Real-photo BIM mapping test

DefectSync ran tiled YOLO, ArUco calibration, and IFC raycasting on a photograph of a measured façade. The façade and marker were physical; the test crack was digitally generated on the photo. No crack box or centre pixel was supplied to the mapper by hand.

- [Source photo](source-photo.png) and [measured IFC](measured-facade.ifc)
- [Physical column and IFC correspondence](physical-column-to-ifc-c1.png)
- [Two-output HTML report](tiled-pipeline-review/index.html) and [numerical results](tiled-pipeline-review/review-results.json)
- [Live screen recording](tiled-pipeline-review/tiled-pipeline-live.mp4) and [recorded result frame](tiled-pipeline-review/recorded-result.png)

The report and recording show two selected outputs from the run. Download the directory before opening the HTML report so its relative video and image links work.

| Selected output | YOLO confidence | Mapping result |
| --- | ---: | --- |
| Added crack | 53.9% | C1, the left façade column, hit at (0.450, 0.000, 1.188) m |
| False efflorescence alert | 33.0% | No IFC element hit |

The 1024 × 466 photo was processed at a 0.25 confidence threshold with tiling enabled: one full-frame pass and 15 overlapping tiles. ArUco `DICT_4X4_50` ID 0 on C2 was registered at (4.245, 0.000, 1.2285) m, with outward normal (0, −1, 0), 90° rotation in the project’s marker basis, and a 0.150 m black-square side. The camera’s horizontal field of view was assumed to be 65°; mean marker reprojection error was 0.438 px.

The test demonstrates an element association for this image. It does not establish absolute position accuracy or a detector performance rate. A ray miss alone is not proof that a detection is false.

The input files are preserved as used in the test:

| File | SHA-256 |
| --- | --- |
| `source-photo.png` | `ba31256d4e8137448638dd6997ba42415e8af66acc4c62536111855ef5380383` |
| `measured-facade.ifc` | `cc5fc97ca3dd939913e10cacf285c7e0e7bafc26005ae4ad4183f4249427f475` |
