"""
image_to_gcode.py
------------------
Converts any image into G-code for a 2-axis (X/Y) stepper pen plotter
with a servo-controlled pen-lift.

Pipeline:
    image -> grayscale -> blur -> Canny edges -> contours -> simplify
          -> scale to plot bed (mm) -> G-code (G0 = pen up travel,
             G1 = pen down draw, M3/M5 = pen down/up)

Usage:
    python image_to_gcode.py input.jpg output.gcode --width 180 --height 180
"""

import argparse
import cv2
import numpy as np


def image_to_paths(image_path, canny_low=50, canny_high=150,
                    min_contour_len=6, approx_epsilon=1.5,
                    max_bed_px=800):
    """
    Load an image and turn it into a list of paths.
    Each path is a list of (x, y) pixel coordinates that should be
    drawn as one continuous pen-down stroke.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")

    # Downscale very large images so contour count / gcode size stays sane
    h, w = img.shape[:2]
    if max(h, w) > max_bed_px:
        scale = max_bed_px / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, canny_low, canny_high)

    # Thicken edges slightly so findContours gets clean closed lines
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    paths = []
    for c in contours:
        if len(c) < min_contour_len:
            continue
        # Simplify the contour so we don't emit a G-code line per pixel
        approx = cv2.approxPolyDP(c, approx_epsilon, closed=False)
        pts = [(int(p[0][0]), int(p[0][1])) for p in approx]
        if len(pts) >= 2:
            paths.append(pts)

    if not paths:
        raise ValueError(
            "No paths found. Try lowering canny_low/canny_high "
            "(the image may be too flat / low-contrast)."
        )

    return paths, img.shape[1], img.shape[0]  # paths, img_width_px, img_height_px


def paths_to_gcode(paths, img_w_px, img_h_px, bed_width_mm, bed_height_mm,
                    feed_draw=1500, feed_travel=3000,
                    pen_down_cmd="M3 S0", pen_up_cmd="M5",
                    pen_settle_s=0.15, origin_margin_mm=2.0):
    """
    Convert pixel-space paths into G-code, scaled + centered to fit the bed.
    Image Y (down) is flipped to machine Y (up).
    """
    usable_w = bed_width_mm - 2 * origin_margin_mm
    usable_h = bed_height_mm - 2 * origin_margin_mm

    scale = min(usable_w / img_w_px, usable_h / img_h_px)
    draw_w_mm = img_w_px * scale
    draw_h_mm = img_h_px * scale
    offset_x = (bed_width_mm - draw_w_mm) / 2
    offset_y = (bed_height_mm - draw_h_mm) / 2

    def to_mm(px, py):
        x_mm = offset_x + px * scale
        y_mm = offset_y + (img_h_px - py) * scale  # flip Y
        return round(x_mm, 2), round(y_mm, 2)

    lines = []
    lines.append("; Auto-generated plotter G-code")
    lines.append("G21 ; units = mm")
    lines.append("G90 ; absolute positioning")
    lines.append(pen_up_cmd + " ; pen up (safe state)")
    lines.append(f"G4 P{pen_settle_s}")
    lines.append(f"G0 F{feed_travel}")
    lines.append(f"G1 F{feed_draw}")

    for path in paths:
        start_x, start_y = to_mm(*path[0])
        # Travel move with pen UP to the start of this stroke
        lines.append(pen_up_cmd)
        lines.append(f"G0 X{start_x} Y{start_y}")
        # Put pen DOWN and draw the rest of the points
        lines.append(pen_down_cmd)
        lines.append(f"G4 P{pen_settle_s}")
        for (px, py) in path[1:]:
            x_mm, y_mm = to_mm(px, py)
            lines.append(f"G1 X{x_mm} Y{y_mm}")

    lines.append(pen_up_cmd + " ; pen up at end")
    lines.append("G0 X0 Y0 ; return home")

    return "\n".join(lines)


def convert(image_path, out_path, bed_width_mm=180, bed_height_mm=180,
            canny_low=50, canny_high=150):
    paths, w_px, h_px = image_to_paths(image_path, canny_low, canny_high)
    gcode = paths_to_gcode(paths, w_px, h_px, bed_width_mm, bed_height_mm)
    with open(out_path, "w") as f:
        f.write(gcode)
    print(f"Wrote {out_path}  ({len(paths)} strokes, "
          f"{sum(len(p) for p in paths)} points)")
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Convert an image to plotter G-code")
    ap.add_argument("image", help="Path to input image")
    ap.add_argument("output", help="Path to output .gcode file")
    ap.add_argument("--width", type=float, default=180, help="Bed width in mm")
    ap.add_argument("--height", type=float, default=180, help="Bed height in mm")
    ap.add_argument("--canny-low", type=int, default=50)
    ap.add_argument("--canny-high", type=int, default=150)
    args = ap.parse_args()

    convert(args.image, args.output, args.width, args.height,
            args.canny_low, args.canny_high)
