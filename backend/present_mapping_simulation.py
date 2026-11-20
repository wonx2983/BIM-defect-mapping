"""Build a browser report and a captioned MP4 from recorded simulation evidence."""

import argparse
import html
import json
import shutil
import subprocess
from pathlib import Path
from statistics import mean

from PIL import Image, ImageDraw, ImageFont


def report(out):
    evidence = json.loads((out / "results.json").read_text(encoding="utf-8"))
    mapping = evidence["mapping"]
    predictions = evidence["detections"]["positive"]
    clean_count = len(evidence["detections"]["clean"])
    tp = evidence["detection_true_positives"]
    fp = evidence["detection_false_positives"]
    missed = evidence["detection_misses"]
    correct = sum(row["correct_element"] for row in mapping)
    errors = [row["error_cm"] for row in mapping if row["error_cm"] is not None]
    error_summary = f"{mean(errors):.2f} cm mean and {max(errors):.2f} cm maximum" if errors else "No hits"
    matched_predictions = [row for row in predictions if row.get("matches")]
    end_to_end = sum(row["correct_element"] is True for row in matched_predictions)
    reprojection = evidence["reprojection_error_px"]
    calibration = (
        f"ID {evidence['marker']['marker_dict_id']} decoded. Reprojection error {reprojection:.3f} px. "
        f"Recovered camera position differs by {evidence['pose_error_cm']:.2f} cm."
        if evidence["calibration_passed"] else f"Calibration failed. {evidence['calibration_error']}"
    )
    pages = [
        ("Virtual camera and IFC", "01-virtual-camera.png",
         f"A fixed virtual camera renders the Schependomlaan IFC with one ArUco marker and {len(mapping)} rendered cracks.",
         "The renderer records the exact surface GUID and 3D position behind each labelled crack."),
        ("Part 1 | Detection ground truth", "03-ground-truth.png",
         "Blue boxes are the known crack annotations. These labels are held out from the detector.",
         "Run the bundled YOLO checkpoint at confidence 0.25. Score class-correct matches at IoU 0.50."),
        ("Part 1 | Actual YOLO output", "04-yolo-positive.png",
         f"{len(predictions)} predictions on the positive frame. {tp} matched, {fp} unmatched, {len(missed)} missed.",
         "Red boxes show actual detector outputs. An unmatched prediction can be a localization or class error."),
        ("Part 1 | Clean control", "04-yolo-clean.png",
         f"The same view and marker without rendered cracks produced {clean_count} YOLO predictions.",
         "The clean control checks whether the scene or marker itself triggers a false alarm."),
        ("Part 2 | Single-marker calibration", "05-marker-calibration.png",
         calibration,
         f"The marker's registered square side is {evidence['marker']['physical_size_m']:.3f} m."),
        ("Part 2 | Missing-marker control", "07-no-marker-control.png",
         f"Calibration {'rejected' if evidence['missing_marker_rejected'] else 'accepted'} the same view with the virtual marker removed.",
         "This control uses the same camera, geometry and registered marker information."),
        ("Part 2 | Scored BIM mapping", "06-bim-mapping.png",
         f"{correct} of {len(mapping)} known crack pixels mapped to the expected IFC element. {error_summary}.",
         "Each label gives the 3D distance from the mapped intersection to the reference point."),
        ("Combined result | Actual detection to BIM", "08-detector-to-bim.png",
         f"{end_to_end} of {len(mapping)} reference cracks passed both detection and correct IFC element assignment.",
         "Every YOLO box was also passed to the mapper. The report separates matched cracks and unmatched boxes."),
    ]
    escape = lambda value: html.escape(str(value if value is not None else "—"))

    def table(headers, rows):
        cells = "".join("<tr>" + "".join(f"<td>{escape(value)}</td>" for value in row) + "</tr>" for row in rows)
        return "<table><thead><tr>" + "".join(f"<th>{escape(h)}</th>" for h in headers) + "</tr></thead><tbody>" + cells + "</tbody></table>"

    prediction_table = table(
        ["Output", "Class", "Confidence", "Best available IoU", "Matched crack", "Mapped GUID", "Correct element", "3D error (cm)"],
        [(f"D{i+1}", p["defect_class"], f"{p['confidence']:.3f}", f"{p['best_unmatched_iou']:.3f}",
          p.get("matches"), p.get("mapped_guid"), p.get("correct_element"),
          f"{p['error_cm']:.2f}" if p.get("error_cm") is not None else None) for i, p in enumerate(predictions)],
    ) if predictions else "<p>YOLO returned no boxes on the positive frame.</p>"
    mapping_table = table(
        ["Crack", "IFC type", "Expected GUID", "Mapped GUID", "Correct", "Error (cm)"],
        [(row["id"], row["element_type"], row["element_guid"], row["mapped_guid"], row["correct_element"],
          f"{row['error_cm']:.2f}" if row["error_cm"] is not None else None) for row in mapping],
    )
    sections = "".join(
        f'<section><h2>{escape(title)}</h2><p>{escape(first)} {escape(second)}</p>'
        f'<a href="{file}"><img src="{file}" alt="{escape(title)}"></a>'
        + (prediction_table if title.startswith("Combined") else "")
        + (mapping_table if title.startswith("Part 2 | Scored") else "") + "</section>"
        for title, file, first, second in pages
    )
    summary = f"""
    <p>Controlled software experiment on the uploaded Schependomlaan IFC. The scene uses structural IFC meshes
    with synthetic surface textures. It represents separate detection and BIM mapping contributions.</p>
    <dl><dt>Detection</dt><dd>{tp}/{len(mapping)} class-correct box matches, {fp} unmatched positive-frame predictions,
    {clean_count} clean-frame predictions. Missed IDs: {escape(', '.join(missed) or 'none')}.</dd>
    <dt>Mapping given reference pixels</dt><dd>{correct}/{len(mapping)} correct IFC element assignments.
    {escape(error_summary)} over {len(errors)} mapped points.</dd>
    <dt>Combined detector to BIM</dt><dd>{end_to_end}/{len(mapping)} detected and assigned to the expected IFC element.</dd></dl>
    """
    methodology = """
    <h2>Method and scope</h2>
    <p>The fixed virtual pinhole camera uses a 1280 × 720 image, a 57° horizontal field of view and zero distortion.
    The depth buffer gives reference world positions in metres and the visible IFC GlobalId for each sampled pixel.
    The production OpenCV calibration receives just the frame, FOV and registered marker geometry.
    The renderer's true pose is held back for scoring. The production mapper uses the recovered pose and the
    candidate IFC meshes to raycast the input pixels.</p>
    <p>Part 1 matches actual YOLO boxes to unused crack annotations in descending confidence order with class and IoU checks.
    Part 2 supplies the known crack locations independently. The combined result supplies actual YOLO box centres.
    When a YOLO box fails the matching rule, its mapped GUID is still recorded, but correctness cannot be attributed to a reference crack.</p>
    <p>One simulated viewpoint and the shown crack samples are a small software experiment. This run does not establish field detection accuracy,
    coverage of all defect classes, live RTSP behaviour, or accuracy with physical lens distortion and installation tolerances.
    The MP4 is a captioned walkthrough assembled from the saved experiment frames.</p>
    """
    (out / "index.html").write_text(f"""<!doctype html><html lang="en"><meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1"><title>DefectSync simulation record</title>
    <style>
    body{{margin:0;background:#eef2f5;color:#172534;font:17px/1.55 system-ui,sans-serif}}
    main{{max-width:1100px;padding:42px 20px;margin:auto}} h1{{font-size:clamp(30px,5vw,50px);line-height:1.12}}
    h2{{font-size:24px}} section,dl{{background:white;border-radius:12px;padding:20px;margin:24px 0;overflow:auto}}
    dt{{font-weight:700}} dd{{margin:0 0 12px}} img,video{{display:block;width:100%;border-radius:8px}}
    table{{margin-top:18px;width:100%;border-collapse:collapse;font-size:.87em}}
    td,th{{text-align:left;padding:8px;border-bottom:1px solid #dce4e8}} a{{color:#085e83}}
    </style><main><h1>DefectSync simulation record</h1>{summary}
    <p><a href="results.json">Raw results and provenance</a> · <a href="mapping.csv">Mapping measurements CSV</a> ·
    <a href="07-no-marker-control.png">Missing-marker input</a> · <a href="execution.txt">Execution log</a></p>
    <video controls preload="metadata" src="simulation.mp4"></video>{sections}{methodology}</main></html>""", encoding="utf-8")
    return pages


def video(out, pages):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to create the presentation recording")
    import textwrap
    fonts = Path("C:/Windows/Fonts")
    title_font = ImageFont.truetype(str(fonts / "segoeuib.ttf"), 35)
    caption_font = ImageFont.truetype(str(fonts / "segoeui.ttf"), 24)
    chapters = out / "chapters"
    chapters.mkdir(exist_ok=True)
    for index, (title, file, first, second) in enumerate(pages):
        slide = Image.new("RGB", (1280, 900), "#142538")
        with Image.open(out / file) as frame:
            slide.paste(frame.convert("RGB").resize((1040, 585), Image.Resampling.LANCZOS), (120, 101))
        draw = ImageDraw.Draw(slide)
        draw.text((52, 29), title, font=title_font, fill="#f5f8ff")
        draw.text((52, 714), textwrap.fill(first, width=101), font=caption_font, fill="#ffffff", spacing=3)
        draw.text((52, 794), textwrap.fill(second, width=106), font=caption_font, fill="#a5d8f5", spacing=3)
        draw.text((1140, 851), f"{index + 1} / {len(pages)}", font=caption_font, fill="#a5d8f5")
        slide.save(chapters / f"{index:02d}.png")
    subprocess.run([ffmpeg, "-nostdin", "-loglevel", "error", "-y", "-framerate", "1/7",
                    "-i", str(chapters / "%02d.png"), "-c:v", "libx264", "-threads", "2",
                    "-r", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    str(out / "simulation.mp4")], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    destination = parser.parse_args().output
    video(destination, report(destination))
