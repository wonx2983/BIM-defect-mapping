"""Build the project PDF from the checked-in simulation evidence. Requires ReportLab."""

import json
from html import escape
from pathlib import Path
from statistics import mean

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs" / "bim-simulation"
OUTPUT = ROOT / "docs" / "DefectSync-project-report.pdf"
REPO = "https://github.com/wonx2983/BIM-defect-mapping"
NAVY = colors.HexColor("#13283A")
TEAL = colors.HexColor("#087C78")
TEXT = colors.HexColor("#243B4A")
MUTED = colors.HexColor("#4D6572")
PALE = colors.HexColor("#EAF4F3")
RULE = colors.HexColor("#C6D9DB")
WIDTH = A4[0] - 96


def style(name, size, leading, color=TEXT, font="Helvetica", after=0):
    return ParagraphStyle(name, fontName=font, fontSize=size, leading=leading,
                          textColor=color, alignment=TA_LEFT, spaceAfter=after)


STYLES = {
    "tag": style("tag", 9, 13, TEAL, "Helvetica-Bold", 8),
    "title": style("title", 29, 33, NAVY, "Helvetica-Bold", 12),
    "cover": style("cover", 42, 44, NAVY, "Helvetica-Bold", 16),
    "lead": style("lead", 13, 18, MUTED, after=13),
    "heading": style("heading", 13, 17, NAVY, "Helvetica-Bold", 5),
    "body": style("body", 10.4, 14.7, after=9),
    "table": style("table", 9.3, 13),
    "thead": style("thead", 9.3, 13, colors.white, "Helvetica-Bold"),
    "caption": style("caption", 8.7, 12, MUTED, after=10),
    "formula": style("formula", 9.5, 14, TEAL, "Courier-Bold", 4),
}


def para(text, kind="body"):
    return Paragraph(text, STYLES[kind])


def table(headers, rows, fractions):
    data = [[para(text, "thead") for text in headers]]
    data.extend([[para(str(text), "table") for text in row] for row in rows])
    block = Table(data, colWidths=[WIDTH * f for f in fractions], repeatRows=1, hAlign="LEFT")
    block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, -1), (-1, -1), .6, RULE),
    ]))
    return block


def figure(filename, caption, width=WIDTH):
    picture = Image(RUN / filename, width=width, height=width * 720 / 1280)
    picture.hAlign = "LEFT"
    return KeepTogether([picture, Spacer(1, 6), para(caption, "caption")])


def page(story, group, title, lead, first=False):
    if not first:
        story.append(PageBreak())
    story.extend([para(group, "tag"), para(title, "cover" if first else "title"), para(lead, "lead")])


def block(story, heading, *paragraphs):
    story.append(para(heading, "heading"))
    story.extend(para(body) for body in paragraphs)


def link(label, path):
    return f'<a color="#087C78" href="{REPO}/blob/main/{path}">{escape(label)}</a>'


def external(label, url):
    return f'<a color="#087C78" href="{url}">{escape(label)}</a>'


def connection_diagram():
    drawing = Drawing(WIDTH, 135)
    captions = [
        ("CAPTURE", "Image / sampled frame"),
        ("DETECT", "Class + original box"),
        ("MAP", "IFC GlobalId + XYZ"),
        ("REVIEW", "Pin + evidence"),
    ]
    for index, (heading, detail) in enumerate(captions):
        x = 4 + 124 * index
        drawing.add(Rect(x, 44, 113, 51, rx=6, ry=6, fillColor=PALE, strokeColor=RULE))
        drawing.add(String(x + 10, 77, heading, fontName="Helvetica-Bold", fontSize=9, fillColor=TEAL))
        drawing.add(String(x + 10, 59, detail, fontSize=8, fillColor=TEXT))
        if index:
            drawing.add(Line(x - 11, 69, x, 69, strokeColor=TEAL))
    drawing.add(String(8, 108, "Inspection pipeline", fontName="Helvetica-Bold", fontSize=10, fillColor=NAVY))
    drawing.add(String(8, 20, "Calibration and the linked IFC model supply the geometry used in MAP.", fontSize=9, fillColor=MUTED))
    return drawing


def ray_diagram():
    drawing = Drawing(WIDTH, 184)
    drawing.add(Rect(0, 0, WIDTH, 184, rx=6, ry=6, fillColor=PALE, strokeColor=RULE))
    drawing.add(Line(55, 46, 428, 141, strokeColor=TEAL, strokeWidth=2))
    drawing.add(Line(122, 40, 122, 126, strokeColor=MUTED, strokeWidth=2))
    drawing.add(Line(278, 58, 278, 139, strokeColor=NAVY, strokeWidth=4))
    drawing.add(Line(391, 81, 391, 156, strokeColor=MUTED, strokeWidth=3))
    for x, y in [(55,46), (122,63), (278,103), (391,132)]:
        drawing.add(Circle(x, y, 4, fillColor=TEAL, strokeColor=colors.white))
    for x, y, label in [(26, 26, "Camera C"), (91, 138, "Image plane"),
                        (132, 53, "Pixel (u, v)"), (228, 149, "Wall A: first hit"),
                        (349, 167, "Wall B: farther hit"), (166, 101, "World ray")]:
        drawing.add(String(x, y, label, fontSize=9, fillColor=NAVY))
    return drawing


def shell(canvas, doc):
    w, h = A4
    canvas.saveState()
    canvas.setFillColor(TEAL)
    canvas.rect(0, h - 7, w, 7, fill=1, stroke=0)
    canvas.setStrokeColor(RULE)
    canvas.line(48, 40, w - 48, 40)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(48, 26, "DEFECTSYNC  /  B.TECH PROJECT REPORT")
    canvas.drawRightString(w - 48, 26, f"{doc.page:02d}")
    canvas.restoreState()


def build():
    result = json.loads((RUN / "results.json").read_text(encoding="utf-8"))
    known = result["mapping"]
    positive = result["detections"]["positive"]
    detected = {row["matches"]: row for row in positive if row.get("matches")}
    clean_count = len(result["detections"]["clean"])
    matched = result["detection_true_positives"]
    false_positive = result["detection_false_positives"]
    correct_known = sum(row["correct_element"] for row in known)
    correct_automatic = sum(row.get("correct_element") is True for row in detected.values())
    point_errors = [row["error_cm"] for row in known if row["error_cm"] is not None]
    assert len(known) == 2 and matched == 2 and result["calibration_passed"], "Expected verified two-crack demo"
    story = []

    page(story, "INDIAN INSTITUTE OF TECHNOLOGY DELHI  /  NOVEMBER 2026", "DefectSync",
         "Technical report on AI-driven concrete inspection and automated defect-to-BIM mapping.", first=True)
    block(story, "B.Tech project",
          "Department of Civil Engineering, Indian Institute of Technology Delhi<br/>"
          "<b>Project supervisor:</b> Prof. Sahil Garg")
    story.append(connection_diagram())
    story.append(table(["Contribution", "Responsibility and result"], [
        ("<b>Part I</b><br/>Bhavishya Kumar Singh",
         "Find suspected defects in images or sampled video frames. Produce class, confidence, bounding boxes, size in pixels, and annotated evidence."),
        ("<b>Part II</b><br/>Krishan Jangir",
         "Register IFC geometry and cameras, recover camera pose from a marker, and locate the defect on a specific IFC element in 3D."),
    ], [.34, .66]))
    story.append(Spacer(1, 14))
    block(story, "Reading guide",
          "<b>Pages 2-7.</b> System overview, followed by Part I: detection, data, training, severity and video.<br/>"
          "<b>Pages 8-11.</b> Part II: IFC viewer, camera registration, coordinate transforms and raycasting.<br/>"
          "<b>Pages 12-16.</b> Shared user journey, software stack, validation and references.")

    page(story, "SYSTEM OVERVIEW", "From inspection to IFC element",
         "The detector answers what and where in the image. The mapper answers which model element and where in 3D.")
    block(story, "Problem and design objective",
          "A photograph can reveal a suspected surface defect before the surface is covered, but a pixel or a camera name does not identify the affected wall, column or slab. One camera may see several elements. DefectSync joins image-based observations to a persistent building element and source evidence so an inspector can review and track it.")
    story.append(table(["Step", "System responsibility", "Handed to the next step"], [
        ("1. Capture", "Upload an image or video, or capture a bounded batch from a configured RTSP camera.",
         "Image/frame, source identity and evidence."),
        ("2. Detect", "Run the trained YOLO checkpoint and interpret its raw boxes.",
         "Class, score, original-image box, pixel size and severity estimate."),
        ("3. Calibrate", "Match ArUco image corners with registered 3D corners for the linked model.",
         "Intrinsics, camera pose, calibration status and candidate elements."),
        ("4. Locate", "Project the box centre as a ray and find the nearest IFC surface intersection.",
         "Model ID, element GlobalId, 3D hit point or unresolved status."),
        ("5. Review", "Show observations with their evidence, store changes and export CSV.",
         "An auditable inspection record."),
    ], [.17, .44, .39]))
    story.append(Spacer(1, 14))
    block(story, "Shared architecture",
          "Next.js provides the Dashboard, Projects, Detection, Video, BIM Viewer and Reports. Three.js and web-ifc load the viewer geometry. FastAPI exposes the project, inspection, calibration and mapping APIs. PostgreSQL holds project membership, models, camera and marker settings, defects and audit events. Private local storage holds IFC, captures and annotated media.",
          "The viewer and backend interpret the same IFC version. The viewer converts between display axes and IFC axes for placement. The backend uses IfcOpenShell world-space meshes for raycasting. A separate camera worker runs due jobs and reports its availability.")
    block(story, "The interface between student contributions",
          "The mapper uses the bounding-box centre <b>(u, v)</b> in original-frame pixels. The source camera and frame resolution tie that pixel to the calibrated intrinsics and pose. Class, confidence and reference to the source evidence are carried through. A pixel from a different crop or resolution must first be translated to the calibrated image coordinates.")

    page(story, "PART I  /  BHAVISHYA KUMAR SINGH", "Detecting defects in images",
         "This contribution turns camera observations into structured, reviewable detections.")
    block(story, "1. Acquire and validate the input",
          "Detection accepts image uploads. Video processing samples selected frames from an uploaded clip, and the camera workflow samples frames from an authorized RTSP source. Inputs are decoded before inference. The image upload path corrects EXIF orientation and converts to RGB. Size, frame count and stream time limits bound the cost of an inspection.",
          "A smaller frame interval samples motion and intermittent visibility more densely, at a higher processing cost. A missed sample can hide a brief event. A fixed camera can often inspect the same surfaces periodically rather than process every frame.")
    block(story, "2. Run the detector",
          "The bundled YOLOv11 checkpoint predicts bounding boxes, class labels and confidence scores. The inference library resizes the image for the model, filters low-confidence candidates and suppresses overlapping predictions. Output boxes are expressed in the original image's pixel coordinates so evidence and mapping stay aligned.",
          "The seven classes are crack, spalling, exposed rebar, corrosion, efflorescence, scaling and honeycombing. The default configured confidence threshold is 0.25. A confidence score ranks a model prediction. It is not a measured probability that a wall has a defect.")
    block(story, "3. Present a reviewable observation",
          "The response includes original-image and normalized box coordinates, pixel width and height, estimated severity, and inference metadata. An annotated frame draws the class and box over the source view. An inspector can compare the proposed defect with its context before making a decision.",
          "The severity pipeline can use an optional classifier. Without a trained classifier checkpoint, it falls back to a heuristic score and severity band. Pixel dimensions alone cannot establish physical crack width or severity. A camera image with unknown depth and scale needs additional measurement.")
    block(story, "Training and inference are separate",
          "The dataset tooling normalizes source labels into the seven-class taxonomy and writes a YOLO dataset configuration for the image and label splits. The trainer can fine-tune a YOLO checkpoint and save the best weights. This report evaluates the bundled checkpoint as supplied. It does not report a new training run.")
    story.append(table(["Visual review", "Typical cause", "Inspector action"], [
        ("False alert", "Stain, shadow, joint, texture or a construction detail resembles a learned class.", "Compare the original view, zoom in, and verify the observation."),
        ("Missed defect", "The defect is too small, blurred, obstructed, or looks different from the training examples.", "Acquire closer or better-lit evidence and inspect manually."),
    ], [.20, .40, .40]))

    page(story, "PART I  /  BHAVISHYA KUMAR SINGH", "Dataset and model training",
         "A shared taxonomy lets the detector learn several defect types and emit a stable class ID for the rest of the system.")
    block(story, "Dataset curation",
          "The repository's preparation tool targets two Roboflow sources: DEEP Concrete Defect Detection and a honeycombing dataset. It translates names and indices into a single taxonomy and writes train, validation and test locations in YOLO format. The raw datasets are not bundled, so the exact retained counts and split independence are not independently verified here.",
          "Each annotation carries a class index and a normalized box centre, width and height. The unified labels make predictions across sources comparable. Before a field benchmark, verify for each class that site, capture session and near-duplicate images do not cross the training and evaluation splits. Retain verified normal surfaces to measure false alarms.")
    story.append(table(["Class", "Surface cue used in review", "Severity base"], [
        ("Crack", "Linear, branched or network-like discontinuity", "0.60"),
        ("Spalling", "Detached or missing concrete cover", "0.70"),
        ("Exposed rebar", "Reinforcing steel visible through cover loss", "0.90"),
        ("Corrosion", "Rust-related surface staining or exposed steel oxidation", "0.85"),
        ("Efflorescence", "Pale mineral or salt deposits", "0.50"),
        ("Scaling", "Flaking or peeling of the surface layer", "0.65"),
        ("Honeycombing", "Voids and exposed coarse aggregate from incomplete consolidation", "0.75"),
    ], [.22, .60, .18]))
    story.append(Spacer(1, 13))
    block(story, "Transfer learning and checkpointing",
          "The training script fine-tunes a YOLO11 checkpoint with configurable image size, batch and epoch count. The default arguments use 640-pixel training images and 50 epochs. Colour, perspective, rotation, scale, flips, mosaic and mixup augment the training set. Run state supports checkpoint resumption. The script can copy best weights into the model directory and optionally export ONNX. The delivered FastAPI inference path uses the PyTorch checkpoint.")

    page(story, "PART I  /  BHAVISHYA KUMAR SINGH", "Severity as a review aid",
         "The software gives each candidate a consistent review priority and retains the evidence behind it.")
    block(story, "Classifier path",
          "The optional ResNet-18 path uses transfer learning on labelled defect crops. It crops the YOLO box, resizes to 224 x 224 and applies normalization. Softmax gives a class distribution. A weighted sum of the probability for each band gives a continuous score using midpoints 0.125, 0.375, 0.625 and 0.875. The training code provides class weighting, AdamW and a cosine schedule for this pathway.",
          "This release does not bundle a trained severity checkpoint. The runtime therefore uses the rule path. A deployed classifier would need provenance, verified label order and independent expert-labelled grading data.")
    block(story, "Rule path used in the current application",
          "The rule starts with the base weight of the predicted defect class and combines it with four quantities derived from the box and detector output. Scores are bounded to [0, 1].")
    story.append(table(["Factor", "Weight", "What it measures"], [
        ("Class", "25%", "Fixed importance weight for the predicted defect type."),
        ("Relative box area", "25%", "Box area divided by image area, scaled and capped."),
        ("Detection confidence", "20%", "Prominence proxy from the detector output."),
        ("Aspect ratio", "15%", "Elongation of the detected rectangle, scaled and capped."),
        ("Image-edge proximity", "15%", "Distance to the nearest image boundary, not a verified structural joint."),
    ], [.25, .16, .59]))
    story.append(Spacer(1, 12))
    block(story, "Score interpretation",
          "Low, Medium, High and Critical are bands separated by 0.25, 0.50 and 0.75. Framing, distance and cropping can change the image-derived factors even for the same defect. The score and pixel dimensions help order a review queue. Engineering severity and physical crack width require independent measurement and judgement.")

    page(story, "PART I  /  BHAVISHYA KUMAR SINGH", "Working with video evidence",
         "Frame sampling limits computational cost. Repeat counting reduces inflated totals in a stable camera view.")
    block(story, "Upload or connect, then sample",
          "The video path decodes frames using OpenCV, converts frame arrays to RGB for the detector, and samples by frame index. Processing every tenth frame of a 30 fps video produces about three inspected frames per second before compute and network effects. The sampling interval trades event coverage against GPU or CPU load. Results retain frames and timestamps so reviewers can inspect the source.",
          "An RTSP source uses the same inference path. The scheduled-worker workflow runs bounded capture and processing batches. The code limits work per request and handles unreachable sources as failures rather than fabricating defect records.")
    block(story, "Two different uses of overlap",
          "Within one image, YOLO postprocessing suppresses overlapping boxes as part of inference. Across sampled frames, the current video summary treats a same-class box with IoU greater than 0.50 against an already counted box as a repeat. This produces a unique-count estimate. It does not provide persistent tracks and assumes image positions stay comparable.",
          "The BIM mapper uses a separate 3D rule after it has an element and position. Image-plane overlap is unsuitable for matching detections across cameras because the same defect can appear at different pixel positions. Part II explains the surface-based merge.")
    block(story, "Structured handoff",
          "A detection contributes the source identity, sampling timestamp, class, confidence and severity score together with the original-image box. Its position can be computed from the average of the upper-left and lower-right corners. The viewer retains the annotated evidence. The downstream mapper needs the camera model and original pixel dimensions to interpret the selected point.")
    story.append(table(["Scenario", "Expected consequence"], [
        ("Camera shake or zoom", "Pixel overlap can fall even when the defect has not moved. Review repeated counts and recalibrate if stream geometry changes."),
        ("A temporarily occluded area", "A sampled frame may provide no useful view. Absence of a prediction is not evidence that the surface is clear."),
        ("Nearby same-class defects", "Similar overlapping boxes can be counted together. Review the source frames where this matters."),
    ], [.32, .68]))

    page(story, "PART I  /  BHAVISHYA KUMAR SINGH", "Detection contribution and evidence",
         "The contribution is a concrete-inspection workflow built around established vision algorithms.")
    block(story, "What Student 1 contributes",
          "<b>Unified concrete taxonomy.</b> The project brings seven classes into one localized detector and normalizes labels across dataset sources. It can report several defect types without reducing the output to image-level crack or no-crack classification.",
          "<b>Operational output.</b> The same inference wrapper handles uploaded photos, sampled video and camera frames. It turns boxes into typed, scored, evidence-linked observations that a geometry pipeline can consume.",
          "<b>Priority and repeat handling.</b> Optional learned severity, an explainable fallback, and video repeat counting provide a review path on machines with and without a separate severity checkpoint. YOLO, ResNet, IoU and non-maximum suppression are established methods. The contribution is their adaptation and combination for inspection.")
    block(story, "Checkpoint evidence and the correct benchmark",
          "The repository audit reports the following embedded validation metrics for the actual bundled weights. These are checkpoint metadata. The raw dataset and complete run provenance are unavailable, so an independent rerun is still needed.")
    story.append(table(["Precision", "Recall", "mAP at IoU 0.50", "mAP at IoU 0.50-0.95"], [
        ("59.57%", "51.33%", "54.74%", "29.70%"),
    ], [.20, .19, .27, .34]))
    story.append(Spacer(1, 13))
    block(story, "How to evaluate the detector",
          "Match each prediction to at most one same-class reference box at a defined intersection-over-union threshold. Precision is the proportion of reported detections that match. Recall is the proportion of labelled defects found. Average precision summarizes the precision-recall curve, and mAP averages over classes or IoU thresholds as stated. For site video, also count false alerts per interval and measure missed defects by class and size.",
          "The integrated simulation later in this report verifies the software handoff. It cannot substitute for independent site images or expert severity labels.")

    page(story, "PART II  /  KRISHAN JANGIR", "Registering a camera in BIM",
         "Calibration relates pixels to the IFC coordinate system by observing a marker of known size and pose.")
    block(story, "Import the model and place the marker",
          "Choose the project and upload the correct IFC version. IFC elements have persistent GlobalIds and shape representations. In Markers, search the viewer's element list or click a surface. The selected point becomes the marker centre. The UI displays the surface direction, the marker's top edge and a preview of the printed square.",
          "The user can apply a surveyed offset from a reference corner using the IFC axes. The registry stores project/model association, element GUID, centre (X, Y, Z) in metres, normal, rotation, physical square size, dictionary and ID. The dictionary and encoded ID distinguish patterns. The server prevents reuse of a registered pattern within the same project.")
    block(story, "Print, install and register a source",
          "Download the generated SVG, print at 100% scale, and measure the black square. Mount it at the registered centre and match the orientation. In Cameras, enter the authorized RTSP URL, horizontal field of view and inspection interval. One visible marker provides four image corners for a fixed-camera pose estimate. Different cameras may see different registered IDs.")
    block(story, "Solve the pose and check the fit",
          "OpenCV decodes the pattern and refines the corner locations. The known square's four corners are transformed into IFC coordinates using the stored marker centre, normal and rotation. The viewpoint is recovered with Perspective-n-Point (PnP) from 3D/2D correspondences. Focal length can be estimated from horizontal field of view and image width. Measured intrinsics and lens distortion are preferable in the field.")
    story.extend([
        para("f_x = image_width / (2 * tan(horizontal_FOV / 2))", "formula"),
        para("p_camera = R * p_IFC + t    |    camera_center = -R^T * t", "formula"),
        Spacer(1, 7),
    ])
    block(story, "Calibration acceptance",
          "For one marker, the implementation uses iterative PnP. With more matched markers it can use RANSAC to reject inconsistent correspondences before refinement. The backend rejects missing or unmatched markers and fits above 2 pixels of mean reprojection error.",
          "The preview helps diagnose unreadable markers or poor visibility. A small corner reprojection error measures fit near the marker. It cannot certify the 3D position of the camera or mapping accuracy elsewhere in the frame.")

    page(story, "PART II  /  PIXEL-TO-IFC MAPPING", "From a pixel to a surface",
         "The recovered camera pose enables a ray to be tested against physical geometry from the linked IFC version.")
    block(story, "1. Build the candidate geometry",
          "IfcOpenShell extracts triangulated structural geometry in world coordinates. Meshes are grouped by IFC GlobalId and cached by model file identity. A view frustum limits the search to elements whose bounds overlap the camera region. This is a geometric filter, so an element inside the frustum may still be occluded.")
    block(story, "2. Back-project the box centre",
          "The system uses the bounding-box midpoint <b>(u, v)</b>. It undistorts the point when distortion coefficients are available and removes the principal point and focal scaling. The camera-space direction is rotated into IFC coordinates. The ray starts at the recovered camera centre.")
    story.extend([
        para("d_camera = normalize([(u - c_x)/f_x, (v - c_y)/f_y, 1])", "formula"),
        para("d_world = normalize(R^T * d_camera)", "formula"),
        para("p(s) = camera_center + s * d_world,  s &gt; 0", "formula"),
        Spacer(1, 8),
    ])
    block(story, "3. Find the nearest surface and store the observation",
          "The mapper checks candidate triangles and selects the nearest positive intersection within the allowed range. It attempts Trimesh ray queries and can fall back to the Moller-Trumbore triangle intersection routine. The nearest hit supplies the IFC element GlobalId and the 3D point in metres. A miss has no valid mapped coordinate.",
          "The linked IFC version remains part of the mapped record. Same-class observations on the same element within 0.50 m can be deduplicated. The record can preserve the stronger observation and refresh its audit trail. Near defects may need human review because a distance threshold can group separate defects.")
    block(story, "Why mapping can fail",
          "The centre of a defect box may fall outside the crack, on a foreground object, or on a neighbouring element. Camera movement, poor intrinsics, wrong marker measurements, and differences between the built surface and the IFC geometry can displace a pin or cause a missed ray. A surface hit indicates geometrical correspondence. The inspector still verifies the evidence.")

    page(story, "PART II  /  KRISHAN JANGIR", "Geometry, intersection and identity",
         "A camera pixel determines a direction only. The IFC geometry supplies the surface and its identity.")
    story.append(ray_diagram())
    story.append(para("Figure 1. Conceptual cross-section. Multiple surfaces can lie along the same ray. The nearest eligible triangle supplies the reported hit.", "caption"))
    block(story, "Worked example with simplified coordinates",
          "Take camera centre C = (0, 0, 0), identity orientation and focal lengths of 800 pixels. A box centre 80 pixels to the right of the principal point gives the unnormalized direction (0.10, 0, 1). Suppose the ray lands inside a wall triangle at Z = 5 m and inside another at Z = 8 m. Their intersections are (0.50, 0, 5) and (0.80, 0, 8). The first wall is the returned element. The example is schematic and independent of the final simulation.")
    block(story, "Moller-Trumbore in the implementation",
          "The fallback intersection solves C + s d = A + u(B - A) + v(D - A), where A, B and D are triangle vertices. It rejects near-parallel rays, barycentric points outside the triangle (u or v negative, or u + v above 1), and nonpositive distances. Across eligible hits, keep the smallest distance. Trimesh provides an accelerated alternative.")
    block(story, "Viewer versus IFC coordinates",
          "The viewer uses a display-axis convention for Three.js, while calibration and persisted defect positions use IFC world axes and metres. A click on the mesh is converted back into IFC coordinates before saving a marker. When a stored position is drawn as a pin, it passes through the inverse conversion. The database links the GUID to the selected model version so another upload cannot silently reinterpret the point.")

    page(story, "PART II  /  KRISHAN JANGIR", "BIM mapping contribution",
         "The contribution combines BIM-anchored camera references with per-observation geometry and an inspector-facing model.")
    block(story, "What Student 2 contributes",
          "<b>BIM-anchored registration.</b> The inspector creates a printable marker from an IFC surface point, orientation and measured size. The same registry drives both printing and recovery of 3D marker corners. A fixed camera can recover its pose when it sees a registered marker. A known model coordinate still depends on an accurate as-built installation.",
          "<b>Selection among visible candidates.</b> A camera may observe many structural elements. The frustum limits the candidate list, and each defect uses its own pixel ray. This resolves individual IFC GUIDs without assigning every detection to a camera's single zone label.",
          "<b>Persistent review context.</b> The system records the association to an IFC version and GlobalId, and uses position proximity to merge repeated observations after mapping. The viewer presents the saved location with the capture so the inspector can correct errors. Trigonometry, ArUco, PnP and raycasting are established. The project contribution is how these mechanisms are connected and used for fixed-camera concrete inspection.")
    story.append(table(["Related work", "Relationship to this project"], [
        ("Mishra et al. [3]", "Uses a mobile calibration robot and fiducial for multi-camera registration. This project uses a marker registered against a fixed IFC surface."),
        ("Hsieh et al. [4]", "Links camera recognition to BIM components for progress monitoring. This project targets surface defect observations and their lifecycle."),
        ("Chen et al. [5]", "Registers aerial images to BIM for defect reconstruction. This project uses a fixed camera and a known marker during setup."),
    ], [.27, .73]))
    story.append(Spacer(1, 12))
    block(story, "Scope of the novelty claim",
          "These examples establish overlapping ideas. The defensible novelty claim is the project's specific application and integration. The current repository stores BIM-linked observations in PostgreSQL and displays them over the IFC. Direct IFC property-set or BCF write-back remains outside the implemented scope.")

    page(story, "USER EXPERIENCE  /  END-TO-END WORKFLOW", "Operate and review an inspection",
         "A project workspace lets the inspector move from manual evidence upload to scheduled, mapped inspection.")
    story.append(table(["Screen", "What the user does", "What to check"], [
        ("Projects", "Sign in and create or open the inspection project.",
         "Confirm the project and membership before uploading evidence."),
        ("BIM Viewer", "Upload or select the IFC version and inspect visible elements.",
         "Confirm the building version and the relevant structural element."),
        ("Detection / Video", "Upload an image or a clip for an ad hoc inspection.",
         "Compare boxes and confidence with the original frame. Ad hoc evidence does not supply a calibrated camera pose by itself."),
        ("Markers", "Choose an IFC face, register the centre and orientation, and download the generated pattern.",
         "Verify the measured square, IFC axes, print orientation and physical installation."),
        ("Cameras", "Register RTSP source, FOV and interval. Preview, calibrate and start monitoring.",
         "Check camera reachability, registered marker visibility, calibration status and worker availability."),
        ("BIM Viewer / Reports", "Select a mapped pin and inspect the saved observation. Update its status and export CSV.",
         "Verify the building element, world position and source evidence. Review any unmatched alerts."),
    ], [.22, .38, .40]))
    story.append(Spacer(1, 14))
    block(story, "Scheduled operation and recovery",
          "After successful calibration, the worker claims due camera jobs using a database lease, processes bounded inspections, and releases the claim. Monitoring status depends on the worker heartbeat. If the worker is offline or calibration fails, the camera remains registered. The inspector can preview the stream, resolve the issue and retry from its card.",
          "If the camera moves or the model changes, verify calibration again before using mapped results. Video and Detection do not require duplicate camera registration. The scheduler performs periodic batches, so an inspection interval is not continuous real-time recording.")
    block(story, "Manually assign an unresolved observation",
          "In the BIM Viewer's Defects tab, select <b>Map</b> on an unmapped item and click the correct IFC surface. The system saves the selected model, element and point. The inspector can remove an incorrect assignment before mapping it again.")

    page(story, "SHARED APPLICATION  /  TECHNOLOGY AND DATA", "Software stack and records",
         "The integration turns a transient detection into a traceable inspection with a source image, project, location and review status.")
    story.append(table(["Layer", "Tools and implementation"], [
        ("Web interface", "Next.js, React and TypeScript for forms, dashboard and review. Three.js and web-ifc for geometry and 3D picking."),
        ("Service/API", "Python and FastAPI for authenticated REST endpoints. SQLAlchemy and Alembic manage data and PostgreSQL schema changes."),
        ("Vision", "Ultralytics YOLO11 and PyTorch for inference. Pillow and OpenCV decode images and sampled video. OpenCV detects ArUco corners and solves pose."),
        ("Geometry", "IfcOpenShell supplies structural meshes. NumPy handles transforms and frustum tests. Trimesh or explicit ray-triangle intersection yields surface hits."),
        ("Storage and jobs", "PostgreSQL stores project entities, scheduled camera claims, and audit events. Protected local storage serves IFC and evidence. A separate scheduler processes camera batches."),
    ], [.22, .78]))
    story.append(Spacer(1, 12))
    block(story, "Records and relationships",
          "An organization contains users and projects. A project contains uploaded IFC versions, markers, cameras and defects. Calibration links a camera to a model and holds intrinsics, pose and candidate GlobalIds. Mapped defects retain model ID, element GlobalId, world position and source evidence. An unresolved observation lacks a verified 3D location and should be inspected before accepting a pin.")
    block(story, "Review lifecycle and access",
          "The review stages include detected, confirmed, assigned, in progress, resolved and verified. Defect changes are auditable. The dashboard summarizes critical alerts and reports can export CSV for inspection follow-up. External notification delivery remains future work.",
          "Authentication and project-scoped media checks govern access to IFC models, photos and inspection history. The backend keeps camera and database credentials out of public evidence. For deployment, use a protected database, an HTTPS reverse proxy and explicit authorization for each RTSP source.")

    page(story, "INTEGRATED EVIDENCE  /  SCHEPENDOMLAAN", "Pipeline validation",
         "The current demonstration uses one IFC model, one fixed virtual camera and two known wall defects.")
    story.append(figure("08-detector-to-bim.png",
                        "Figure 2. Recorded output: C3 and C4 match reference cracks. The other two boxes are false alerts.", width=458))
    block(story, "Controlled setup",
          "The renderer uses a fixed 1280 x 720 virtual pinhole camera with 57 degrees horizontal field of view and a virtual ArUco marker. The IFC surfaces give reference GlobalIds and world coordinates. The calibration receives the rendered image and marker data. The true camera pose is held back for scoring.")
    story.append(table(["Crack", "Reference-pixel mapping error", "YOLO-box mapping error", "IFC element"], [
        (row["id"], f"{row['error_cm']:.2f} cm", f"{detected[row['id']]['error_cm']:.2f} cm",
         "Correct in both paths" if row["correct_element"] and detected[row["id"]]["correct_element"] else "Review")
        for row in known
    ], [.13, .30, .28, .29]))
    story.append(Spacer(1, 10))
    block(story, "What the measurements show",
          f"Two cracks were simulated and both were detected. There were {false_positive} false alerts on the crack frame and {clean_count} on the clean control. This selected demonstration does not establish 100% accuracy.",
          f"The mapper assigned {correct_known} of {len(known)} known reference pixels and {correct_automatic} of {matched} matched YOLO boxes to the expected elements. "
          f"Mean 3D position error from reference pixels was {mean(point_errors):.2f} cm. The marker reprojection error was "
          f"{result['reprojection_error_px']:.3f} pixels, but the camera position estimate differed by {result['pose_error_cm']:.2f} cm. "
          "The marker-free control was rejected.")

    page(story, "REPRODUCIBILITY  /  FIELD VALIDATION", "What is verified and what to test next",
         "The recorded run demonstrates the software pipeline under controlled conditions. Field deployment needs independent acceptance.")
    block(story, "Reproduce the recorded workflow",
          "Install the backend requirements, configure PostgreSQL and the signing secret in the root environment file, and run Alembic migrations. Start the FastAPI and Next.js services using the repository README. For live scheduled inspections, start the camera worker and configure the approved RTSP hosts. The simulation itself runs offline with the Schependomlaan IFC and the bundled detector checkpoint.",
          "The simulation script regenerates the virtual frame, reference boxes, clean control, calibration view and mapping output. The presentation script assembles the HTML and captioned MP4 from those saved artifacts. Raw JSON stores the model hashes, intrinsics settings, pose, detections and world coordinates. CSV records the known-pixel mapping measurements.")
    block(story, "Protect project data",
          "Authenticated project routes separate organizations and user roles. The media routes enforce project access for IFC and inspection files. Keep database credentials, signing keys, and RTSP credentials out of source control. Use HTTPS and restrict camera networks in deployment.")
    story.append(table(["Validation area", "Field procedure"], [
        ("Detection", "Use independently labelled site images across lighting, materials, distances and defect classes. Include normal surfaces. Report precision, recall and class-level metrics at a documented threshold."),
        ("Spatial mapping", "Survey independent points on actual IFC elements. Compare correct-element rate and distribution of 3D position errors. Repeat after lens adjustments and camera motion."),
        ("Operations", "Exercise authorized RTSP feeds during network loss and reconnection. Test coverage, scheduling latency, duplicate handling and evidence access across projects."),
    ], [.24, .76]))
    story.append(Spacer(1, 14))
    block(story, "Joint contribution and remaining work",
          "The integrated system pairs an evidence-producing detector with a geometry-based mapper and a review workflow. Each subsystem can be evaluated independently, which exposes whether an error came from a missed detection, calibration, a wrong surface hit, or a duplicate record.",
          "Future work includes calibrated physical sizing, expert-validated severity, markerless or alternative registration, more extensive multi-camera testing, and model-native export. These require evaluation before they can support operational claims.")

    page(story, "REFERENCES  /  PROJECT SOURCES", "Sources for the two contributions",
         "The student presentations establish authorship and scope. The current repository and evidence establish implementation and results.")
    block(story, "Student presentations",
          "<b>Bhavishya Kumar Singh.</b> <i>AI-Driven Defect Detection &amp; Severity Analysis for Real-Time Structural Health Monitoring with BIM Integration.</i> Supplied presentation and speaker notes. Used to identify the scope of Part I.",
          "<b>Krishan Jangir.</b> <i>Automated Mapping of Detected Concrete Defects onto BIM Elements.</i> Supplied mid-term presentation. Used to identify the scope of Part II.")
    block(story, "Primary technical references",
          f"[1] {external('Redmon et al., You Only Look Once: Unified, Real-Time Object Detection', 'https://arxiv.org/abs/1506.02640')}. CVPR, 2016.",
          f"[2] {external('Ultralytics, YOLO11 model documentation', 'https://docs.ultralytics.com/models/yolo11/')}. Model family used in the detector.",
          f"[3] {external('Mishra et al., Look Both Ways: Bidirectional Visual Sensing for Automatic Multi-Camera Registration', 'https://arxiv.org/abs/2208.07362')}. 2022.",
          f"[4] {external('Hsieh et al., Integration of Construction Progress Monitoring Results Using AI Image Recognition from Multiple Cameras onto a BIM', 'https://doi.org/10.22260/ISARC2024/0090')}. ISARC, 2024.",
          f"[5] {external('Chen et al., Automatic concrete defect detection and reconstruction by aligning aerial images onto semantic-rich building information model', 'https://doi.org/10.1111/mice.12928')}.",
          f"[6] {external('OpenCV, Perspective-n-Point pose computation', 'https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html')}.")
    block(story, "Repository implementation and evidence",
          f"{link('Project README and setup', 'README.md')}<br/>"
          f"{link('Dataset preparation code', 'backend/ml/training/download_dataset.py')}<br/>"
          f"{link('Detector implementation', 'backend/ml/inference/detector.py')}<br/>"
          f"{link('Camera calibration', 'backend/ml/calibration/camera_calibrator.py')}<br/>"
          f"{link('BIM mapping implementation', 'backend/app/services/auto_mapper.py')}<br/>"
          f"{link('Checkpoint provenance audit', 'docs/project_audit_2026-11-18.md')}<br/>"
          f"{link('Current demonstration evidence and walkthrough', 'runs/bim-simulation/README.md')}<br/>"
          f"{link('Deployment and acceptance checks', 'docs/deployment.md')}")
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=42, rightMargin=42,
                            topMargin=47, bottomMargin=54, title="DefectSync Project Report",
                            author="DefectSync B.Tech project", subject="Defect detection and IFC spatial mapping")
    doc.build(story, onFirstPage=shell, onLaterPages=shell)
    print(OUTPUT)


if __name__ == "__main__":
    build()
