"""Build the project PDF from the checked-in simulation evidence. Requires ReportLab."""

import json
from html import escape
from pathlib import Path
from statistics import mean

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
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

    page(story, "PROJECT REPORT  /  NOVEMBER 2026", "DefectSync",
         "From concrete defect detection to location in a building information model.", first=True)
    story.append(figure("01-virtual-camera.png",
                        "Figure 1. Current Schependomlaan virtual camera frame. Two simulated wall cracks and one virtual ArUco marker are present."))
    story.append(table(["Contribution", "Responsibility and result"], [
        ("<b>Part I | Student 1</b><br/>Defect detection",
         "Find suspected defects in images or sampled video frames. Produce class, confidence, bounding boxes, size in pixels, and annotated evidence."),
        ("<b>Part II | Student 2</b><br/>BIM mapping",
         "Register IFC geometry and cameras, recover camera pose from a marker, and locate the defect on a specific IFC element in 3D."),
    ], [.34, .66]))
    story.append(Spacer(1, 14))
    block(story, "Demonstration outcome",
          f"Two cracks were simulated and both were detected. Both matched detections mapped to the expected IFC walls. "
          f"The crack frame also generated {false_positive} false alerts and the clean control generated {clean_count}. "
          "This is a selected software demonstration from one viewpoint. It does not establish 100% accuracy or field readiness.")

    page(story, "SYSTEM OVERVIEW", "From inspection to IFC element",
         "The detector answers what and where in the image. The mapper answers which model element and where in 3D.")
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

    page(story, "PART I  /  STUDENT 1", "Detecting defects in images",
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

    page(story, "PART I  /  DETECTION EVALUATION", "What the detector found",
         "Evaluation compares the detector's actual boxes with independently defined reference boxes.")
    story.append(figure("04-yolo-positive.png",
                        "Figure 2. Actual detector output for the current two-crack frame. The two crack boxes match C3 and C4. The other boxes are false alerts."))
    block(story, "Matching rule",
          "Match a prediction to one unused reference box of the same class. Intersection over union (IoU) is the overlap area divided by the union area. This run uses IoU at least 0.50, with predictions evaluated in descending confidence order.")
    story.append(table(["Observation", "Confidence", "IoU / outcome"], [
        (crack, f"{prediction['confidence']:.3f}",
         f"{prediction['best_unmatched_iou']:.3f} / matched crack")
        for crack, prediction in detected.items()
    ] + [
        ("Other boxes on the crack frame", "At least 0.25", f"{false_positive} unmatched predictions"),
        ("Clean control", "At least 0.25", f"{clean_count} false alerts"),
    ], [.47, .19, .34]))
    story.append(Spacer(1, 10))
    block(story, "How to interpret the outcome",
          "Both reference cracks were detected in this chosen frame. The false alerts show why the result is not an accuracy claim. A general evaluation needs annotated independent site data, multiple classes and conditions, negative scenes, and metrics such as precision, recall and average precision.")

    page(story, "PART II  /  STUDENT 2", "Registering a camera in BIM",
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

    page(story, "INTEGRATED EVIDENCE  /  SCHEPENDOMLAAN", "Two simulated cracks, one workflow",
         "The current demonstration uses one IFC model, one fixed virtual camera and two known wall defects.")
    story.append(figure("08-detector-to-bim.png",
                        "Figure 3. Current run: every YOLO box was submitted to the mapper. C3 and C4 match reference cracks and the other boxes are unmatched alerts."))
    block(story, "Controlled setup",
          "The renderer uses a fixed 1280 x 720 virtual pinhole camera with 57 degrees horizontal field of view and a virtual ArUco marker. The IFC surfaces give reference GlobalIds and world coordinates. The calibration receives the rendered image and marker data. The true camera pose is held back for scoring.")
    story.append(table(["Crack", "Reference-pixel mapping error", "YOLO-box mapping error", "IFC element"], [
        (row["id"], f"{row['error_cm']:.2f} cm", f"{detected[row['id']]['error_cm']:.2f} cm",
         "Correct in both paths" if row["correct_element"] and detected[row["id"]]["correct_element"] else "Review")
        for row in known
    ], [.13, .30, .28, .29]))
    story.append(Spacer(1, 10))
    block(story, "What the measurements show",
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
    block(story, "Source and inspection evidence",
          f"{link('Project README and setup', 'README.md')}<br/>"
          f"{link('Detection implementation', 'backend/ml/inference/detector.py')}<br/>"
          f"{link('Camera calibration', 'backend/ml/calibration/camera_calibrator.py')}<br/>"
          f"{link('BIM mapping implementation', 'backend/app/services/auto_mapper.py')}<br/>"
          f"{link('Current demonstration evidence and walkthrough', 'runs/bim-simulation/README.md')}<br/>"
          f"{link('Deployment and acceptance checks', 'docs/deployment.md')}")
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=42, rightMargin=42,
                            topMargin=47, bottomMargin=54, title="DefectSync Project Report",
                            author="DefectSync B.Tech project", subject="Defect detection and IFC spatial mapping")
    doc.build(story, onFirstPage=shell, onLaterPages=shell)
    print(OUTPUT)


if __name__ == "__main__":
    build()
