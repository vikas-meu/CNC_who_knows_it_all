"""
main.py  (Linux/MPU side - Arduino UNO Q, run via arduino-app-cli, no App Lab)
================================================================================
Hosts a small Flask web page (a "terminal you type into"). Whatever you
type is converted to pen strokes and sent to the STM32 MCU side (sketch.ino)
via the Bridge RPC - move_to() / pen_up() / pen_down() / is_moving().

Your plotter starts at (0,0) by default -> NO HOMING needed/sent.

Test without hardware first:
    python3 main.py --dry-run       # just prints the moves, no Bridge calls
"""

import argparse
import datetime
import json
import math
import os
import socket
import tempfile
import threading
import time

from flask import Flask, request, jsonify

from arduino.app_utils import *   # App, Bridge

# image_to_paths needs OpenCV, which currently fails to install on this
# board (a broken package index entry for opencv-python-headless). Import
# gracefully so the rest of the app - typing, write_text, scheduling -
# keeps working even without it; /draw_image just reports it's unavailable
# until the dependency issue is fixed and this import succeeds normally.
try:
    from image_to_gcode import image_to_paths
    IMAGE_DRAWING_AVAILABLE = True
except ImportError as e:
    IMAGE_DRAWING_AVAILABLE = False
    _image_import_error = str(e)


def get_local_ip():
    """Best-effort LAN IP for printing a clickable URL to the app logs."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no packet actually sent, just picks the route
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


# =========================================================================
# 1. BUILT-IN SINGLE-STROKE VECTOR FONT (Hershey-style, no extra deps)
#    Each glyph: list of strokes; each stroke: list of (x, y) points.
#    Glyph box: x = 0..12, y = 0..20 (baseline at y=0), advance = 14 units.
#    Lowercase is drawn as uppercase (simple, terminal look).
# =========================================================================

_UNKNOWN = [[(0, 0), (12, 0), (12, 20), (0, 20), (0, 0)]]   # box for unknown chars

GLYPHS = {
    'A': [[(1,0),(6,20),(11,0)], [(3,7),(9,7)]],
    'B': [[(1,0),(1,20)], [(1,20),(8,20),(10,17),(10,13),(8,10),(1,10)],
          [(1,10),(9,10),(11,7),(11,3),(9,0),(1,0)]],
    'C': [[(11,16),(8,20),(3,20),(1,16),(1,4),(3,0),(8,0),(11,4)]],
    'D': [[(1,0),(1,20),(7,20),(11,15),(11,5),(7,0),(1,0)]],
    'E': [[(11,20),(1,20),(1,0),(11,0)], [(1,10),(8,10)]],
    'F': [[(11,20),(1,20),(1,0)], [(1,10),(8,10)]],
    'G': [[(11,16),(8,20),(3,20),(1,16),(1,4),(3,0),(8,0),(11,4),(11,8),(6,8)]],
    'H': [[(1,0),(1,20)], [(11,0),(11,20)], [(1,10),(11,10)]],
    'I': [[(2,20),(10,20)], [(6,20),(6,0)], [(2,0),(10,0)]],
    'J': [[(7,20),(11,20)], [(11,20),(11,4),(9,0),(5,0),(3,3)]],
    'K': [[(1,0),(1,20)], [(11,20),(1,8)], [(4,12),(11,0)]],
    'L': [[(1,20),(1,0),(11,0)]],
    'M': [[(1,0),(1,20),(6,8),(11,20),(11,0)]],
    'N': [[(1,0),(1,20),(11,0),(11,20)]],
    'O': [[(3,0),(1,4),(1,16),(3,20),(9,20),(11,16),(11,4),(9,0),(3,0)]],
    'P': [[(1,0),(1,20),(9,20),(11,17),(11,13),(9,10),(1,10)]],
    'Q': [[(3,0),(1,4),(1,16),(3,20),(9,20),(11,16),(11,4),(9,0),(3,0)],
          [(7,4),(12,-2)]],
    'R': [[(1,0),(1,20),(9,20),(11,17),(11,13),(9,10),(1,10)], [(5,10),(11,0)]],
    'S': [[(11,16),(8,20),(3,20),(1,16),(1,12),(3,9),(9,7),(11,4),(11,0),(3,0)]],
    'T': [[(1,20),(11,20)], [(6,20),(6,0)]],
    'U': [[(1,20),(1,4),(3,0),(9,0),(11,4),(11,20)]],
    'V': [[(1,20),(6,0),(11,20)]],
    'W': [[(1,20),(3,0),(6,13),(9,0),(11,20)]],
    'X': [[(1,0),(11,20)], [(1,20),(11,0)]],
    'Y': [[(1,20),(6,10),(11,20)], [(6,10),(6,0)]],
    'Z': [[(1,20),(11,20),(1,0),(11,0)]],
    '0': [[(3,0),(1,4),(1,16),(3,20),(9,20),(11,16),(11,4),(9,0),(3,0)],
          [(2,3),(10,17)]],
    '1': [[(3,16),(6,20),(6,0)], [(4,0),(8,0)]],
    '2': [[(1,16),(3,20),(9,20),(11,16),(11,13),(1,0),(11,0)]],
    '3': [[(1,17),(3,20),(9,20),(11,17),(11,13),(8,10),(4,10)],
          [(8,10),(11,7),(11,3),(9,0),(3,0),(1,3)]],
    '4': [[(8,0),(8,20),(1,7),(11,7)]],
    '5': [[(11,20),(1,20),(1,11),(8,11),(11,9),(11,3),(8,0),(2,0)]],
    '6': [[(10,16),(7,20),(3,20),(1,16),(1,3),(3,0),(8,0),(11,3),(11,6),
           (8,9),(3,9),(1,6)]],
    '7': [[(1,20),(11,20),(4,0)]],
    '8': [[(3,10),(1,13),(1,17),(3,20),(9,20),(11,17),(11,13),(9,10),(3,10)],
          [(3,10),(1,7),(1,3),(3,0),(9,0),(11,3),(11,7),(9,10)]],
    '9': [[(2,4),(5,0),(9,0),(11,3),(11,16),(9,20),(5,20),(2,17),(2,14),
           (5,11),(10,11),(11,14)]],
    '.': [[(5,0),(6,1)]],
    ',': [[(5,1),(4,-3)]],
    '-': [[(2,10),(10,10)]],
    '=': [[(2,8),(10,8)], [(2,12),(10,12)]],
    '+': [[(6,4),(6,16)], [(2,10),(10,10)]],
    ':': [[(5,14),(6,14)], [(5,5),(6,5)]],
    ';': [[(5,14),(6,14)], [(5,5),(4,0)]],
    '/': [[(1,-2),(11,22)]],
    '!': [[(6,20),(6,5)], [(5,1),(6,1)]],
    '?': [[(1,15),(3,19),(9,19),(11,15),(11,12),(6,7),(6,5)], [(5,1),(6,1)]],
    '(': [[(8,22),(5,19),(4,11),(5,1),(8,-2)]],
    ')': [[(4,22),(7,19),(8,11),(7,1),(4,-2)]],
    '_': [[(0,-3),(12,-3)]],
    '*': [[(6,5),(6,15)], [(2,7),(10,13)], [(2,13),(10,7)]],
    '"': [[(3,16),(4,20)], [(8,16),(9,20)]],
    "'": [[(5,16),(6,20)]],
    '~': [[(2,11),(4,13),(6,11),(8,9),(10,11)]],
}

GLYPH_ADVANCE = 14   # horizontal units between characters
SPACE_ADVANCE = 10   # width of a space
FONT_UNITS_H = 20    # glyph box height (cap height)


def strokes_for_text(text, text_height=6.0):
    """Return a list of pen strokes [(x,y),...] for `text`, y-up, in mm."""
    scale = text_height / FONT_UNITS_H
    strokes = []
    x_cursor = 0.0
    for ch in text.upper():
        if ch == ' ':
            x_cursor += SPACE_ADVANCE * scale
            continue
        glyph = GLYPHS.get(ch, _UNKNOWN)
        for stroke in glyph:
            strokes.append([(x_cursor + x * scale, y * scale) for x, y in stroke])
        x_cursor += GLYPH_ADVANCE * scale
    return strokes


def text_width(strokes):
    pts = [x for s in strokes for x, y in s]
    return max(pts) if pts else 0.0


FEED_TRAVEL = 5000    # mm/min, pen-up rapid moves (independent of the speed slider)
CLEAN_FEED = 5000     # mm/min, wiping raster motion
CLEAN_ROW_SPACING_MM = 20   # gap between wipe passes - TUNE to your cloth's width
POLL_INTERVAL_S = 0.005   # was 0.05 - a 50ms floor was hiding your speed changes
                          # on short strokes; 5ms lets fast short segments show up
FIXED_ANGLE_DEG = 315  # writing angle, permanent - not adjustable from the UI

# Clamp ranges for the live UI controls / auto-fit
TEXT_HEIGHT_MIN, TEXT_HEIGHT_MAX = 4, 60
FEED_DRAW_MIN, FEED_DRAW_MAX = 100, 8000


class TaskCancelled(Exception):
    """Raised internally to unwind a write/draw loop immediately when a
    task is cancelled mid-execution."""
    pass


class Task:
    """Tracks one write_text/draw_image job so it can be cancelled, paused,
    resumed, and its progress queried - all from separate HTTP requests
    while the actual plotting runs in a background thread."""
    def __init__(self, task_id, kind):
        self.id = task_id
        self.kind = kind          # "write" or "draw"
        self.status = "PENDING"   # PENDING/RUNNING/PAUSED/COMPLETED/CANCELLED/FAILED
        self.progress = ""
        self.error = None
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()

    def as_dict(self):
        return {"id": self.id, "kind": self.kind, "status": self.status,
                "progress": self.progress, "error": self.error}


def check_task_control(task):
    """Call before every physical move: blocks while paused, raises
    TaskCancelled if cancellation was requested. No-op if task is None
    (manual web-UI actions aren't tracked as cancellable tasks)."""
    if task is None:
        return
    while task.pause_event.is_set():
        if task.cancel_event.is_set():
            raise TaskCancelled()
        time.sleep(0.2)
    if task.cancel_event.is_set():
        raise TaskCancelled()


def rotate_xy(x, y, angle_deg):
    """Rotate a point about the machine origin (0,0) by angle_deg.

    Used because the paper/writing surface is mounted at a fixed tilt
    relative to the machine's X/Y axes - every point laid out in
    "page space" gets rotated into real machine coordinates before
    it's sent to move_to().
    """
    a = math.radians(angle_deg)
    cos_a, sin_a = math.cos(a), math.sin(a)
    return x * cos_a - y * sin_a, x * sin_a + y * cos_a


def wrap_text(text, text_height, max_width):
    """Greedy word-wrap: split `text` into lines no wider than max_width
    at the given letter height (mm), measured with the vector font."""
    words = text.split()
    if not words:
        return [""]
    lines, current = [], ""
    for w in words:
        candidate = (current + " " + w).strip()
        if not current or text_width(strokes_for_text(candidate, text_height)) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def fit_text_to_page(text, bed_w, margin, usable_h,
                      min_fs=TEXT_HEIGHT_MIN, max_fs=30, step=1):
    """Find the largest font size (mm) that lets `text` word-wrap and fit
    within usable_h mm of vertical space (the caller decides whether that's
    a fresh full page or whatever's left below the current cursor). Falls
    back to the smallest size and trims lines if even that doesn't fit."""
    usable_w = bed_w - 2 * margin

    fs = max_fs
    while fs >= min_fs:
        lines = wrap_text(text, fs, usable_w)
        if len(lines) * (fs * 1.6) <= usable_h:
            return fs, lines
        fs -= step

    fs = min_fs
    lines = wrap_text(text, fs, usable_w)
    max_lines = max(1, int(usable_h // (fs * 1.6))) if usable_h > 0 else 1
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    return fs, lines


# =========================================================================
# 2. PLOTTER: text -> pen strokes -> Bridge calls to the STM32 MCU
# =========================================================================


class Plotter:
    def __init__(self, dry_run=False, bed_w=550, bed_h=400, margin=20,
                 text_height=10, feed_draw=1500, auto_clean=True):
        self.bed_w, self.bed_h = bed_w, bed_h
        self.margin = margin
        self.dry_run = dry_run
        self.text_height = text_height
        self.angle_deg = FIXED_ANGLE_DEG   # permanent, not user-adjustable
        self.feed_draw = feed_draw
        self.auto_clean = auto_clean       # False = never clean without being asked
        self._recompute_layout()
        self.cur_y = bed_h - margin - self.text_height   # baseline of first line
        self.lock = threading.Lock()                     # one plot at a time
        # NOTE: no homing is sent. The plotter is assumed to already be at (0,0).

    def _recompute_layout(self):
        self.line_spacing = self.text_height * 1.6
        self.max_chars_width = self.bed_w - 2 * self.margin

    def update_settings(self, text_height=None, feed_draw=None):
        if text_height is not None:
            self.text_height = max(TEXT_HEIGHT_MIN, min(TEXT_HEIGHT_MAX, float(text_height)))
        if feed_draw is not None:
            self.feed_draw = max(FEED_DRAW_MIN, min(FEED_DRAW_MAX, float(feed_draw)))
        self._recompute_layout()

    # ---- low-level moves, via Bridge instead of serial G-code ----
    def _wait_until_idle(self):
        while True:
            moving = Bridge.call("is_moving")
            if str(moving) in ("0", "False", "false"):
                break
            time.sleep(POLL_INTERVAL_S)

    def _move_to(self, x, y, feed, task=None):
        check_task_control(task)
        if self.dry_run:
            print(f"  [dry] move_to({x:.2f}, {y:.2f}, F{feed})")
            return
        Bridge.call("move_to", float(x), float(y), float(feed))
        self._wait_until_idle()

    def _pen_up(self):
        if self.dry_run:
            print("  [dry] pen_up")
        else:
            Bridge.call("pen_up")
        time.sleep(0.15)   # let the servo settle

    def _pen_down(self):
        if self.dry_run:
            print("  [dry] pen_down")
        else:
            Bridge.call("pen_down")
        time.sleep(0.15)

    def _cleaner_down(self):
        if self.dry_run:
            print("  [dry] cleaner_down")
        else:
            Bridge.call("cleaner_down")
        time.sleep(0.2)

    def _cleaner_up(self):
        if self.dry_run:
            print("  [dry] cleaner_up")
        else:
            Bridge.call("cleaner_up")
        time.sleep(0.2)

    def return_to_home(self):
        """Lift the pen and move to (0,0) without drawing anything - the
        one place all cancellation/error paths funnel through, so the
        machine never gets left mid-workspace or mid-stroke. Deliberately
        passes no task, so this itself can never be cancelled/paused."""
        try:
            self._pen_up()
            self._move_to(0, 0, FEED_TRAVEL)
        except Exception as e:
            print(f"return_to_home failed: {e}")

    def clean_page(self, task=None):
        """Wipe the whole writable area in a zig-zag raster (same 308-degree
        tilt as the writing itself), then reset the page cursor so new
        writing starts fresh at the top."""
        self._pen_up()          # keep the writing pen clear of the board
        self._cleaner_down()    # lower the cleaning cloth

        left, right = self.margin, self.bed_w - self.margin
        top, bottom = self.margin, self.bed_h - self.margin

        y = top
        going_right = True
        x = left if going_right else right
        mx, my = rotate_xy(x, y, self.angle_deg)
        self._move_to(mx, my, FEED_TRAVEL, task=task)   # get into position for the first pass

        while True:
            x = right if going_right else left
            mx, my = rotate_xy(x, y, self.angle_deg)
            self._move_to(mx, my, CLEAN_FEED, task=task)

            y += CLEAN_ROW_SPACING_MM
            if y > bottom:
                break
            mx, my = rotate_xy(x, y, self.angle_deg)
            self._move_to(mx, my, CLEAN_FEED, task=task)
            going_right = not going_right

        self._cleaner_up()      # lift the cloth back off the board
        self._move_to(0, 0, FEED_TRAVEL, task=task)

        self.cur_y = self.bed_h - self.margin - self.text_height

    # ---- write one line of text, advance cursor down ----
    def write_line(self, text, task=None):
        strokes = strokes_for_text(text, self.text_height)

        if text_width(strokes) > self.max_chars_width:     # truncate to fit bed
            while text and text_width(strokes_for_text(text, self.text_height)) > self.max_chars_width:
                text = text[:-1]
            strokes = strokes_for_text(text + "~", self.text_height)

        cleaned = False
        if self.cur_y < self.margin:
            if not self.auto_clean:
                return "PAGE FULL - clean manually (Clean now) to continue - line skipped"
            self.clean_page(task=task)   # board is full - wipe it and start fresh at the top
            cleaned = True

        for stroke in strokes:
            pts = [rotate_xy(self.margin + x, self.cur_y + y, self.angle_deg)
                   for x, y in stroke]
            self._pen_up()
            self._move_to(pts[0][0], pts[0][1], FEED_TRAVEL, task=task)
            self._pen_down()
            for x, y in pts[1:]:
                self._move_to(x, y, self.feed_draw, task=task)
        self._pen_up()

        self.cur_y -= self.line_spacing
        return "ok (board cleaned first)" if cleaned else "ok"

    def plot_text(self, text, text_height=None, feed_draw=None, task=None):
        """Thread-safe: plot several lines (one per \\n) at the current/given
        font size, stacking below whatever was written before. Returns status.
        Lines flow straight into each other - no pause between them beyond
        the pen lift/lower already needed for each stroke."""
        with self.lock:
            self.update_settings(text_height, feed_draw)
            lines = text.split("\n")
            notes = []
            for i, line in enumerate(lines, 1):
                if task:
                    task.progress = f"{i}/{len(lines)} lines"
                status = self.write_line(line, task=task)
                notes.append(status)
                if status != "ok" and not status.startswith("ok ("):
                    break
            return "; ".join(notes)

    def plot_response(self, text, feed_draw=None, task=None):
        """Thread-safe: auto-size `text` to fit in whatever vertical space is
        left below the current writing position (continuing on from the last
        thing written, not overwriting it), word-wrapping and shrinking the
        font until it fits. If there's essentially no room left and auto-clean
        is on, the board gets cleaned first and the response starts a fresh
        page; if auto-clean is off, the response is skipped instead.
        Lines transition straight into each other with no pause between them.
        Returns (status, font_size)."""
        with self.lock:
            if feed_draw is not None:
                self.feed_draw = max(FEED_DRAW_MIN, min(FEED_DRAW_MAX, float(feed_draw)))

            available_h = self.cur_y - self.margin
            if available_h < TEXT_HEIGHT_MIN * 1.6:   # essentially no room left
                if not self.auto_clean:
                    return ("PAGE FULL - clean manually (Clean now) to continue - "
                            "response skipped", self.text_height)
                self.clean_page(task=task)
                available_h = self.bed_h - 2 * self.margin

            fs, lines = fit_text_to_page(text, self.bed_w, self.margin, available_h)
            self.text_height = fs
            self._recompute_layout()
            # NOTE: cur_y is NOT reset here - the response continues below
            # whatever was written before, same as the manual typing mode.

            notes = []
            for i, line in enumerate(lines, 1):
                if task:
                    task.progress = f"{i}/{len(lines)} lines"
                status = self.write_line(line, task=task)
                notes.append(status)
            return "; ".join(notes), fs

    def draw_image_paths(self, paths, img_w_px, img_h_px, task=None):
        """Draw image_to_gcode's extracted stroke paths, scaled + centered
        to fill the whole writable area (same 308-degree tilt as text).
        Cleans the board first only when auto-clean is on - in manual mode
        the image is drawn straight onto whatever's already on the board,
        same as text/AI writing."""
        with self.lock:
            if self.auto_clean:
                self.clean_page(task=task)   # fresh, empty area for the image

            usable_w = self.bed_w - 2 * self.margin
            usable_h = self.bed_h - 2 * self.margin
            scale = min(usable_w / img_w_px, usable_h / img_h_px)
            draw_w = img_w_px * scale
            draw_h = img_h_px * scale
            offset_x = self.margin + (usable_w - draw_w) / 2
            offset_y = self.margin + (usable_h - draw_h) / 2

            def to_page_mm(px, py):
                x_mm = offset_x + px * scale
                y_mm = offset_y + (img_h_px - py) * scale   # flip Y
                return x_mm, y_mm

            for i, path in enumerate(paths, 1):
                if task:
                    task.progress = f"{i}/{len(paths)} strokes"
                pts = []
                for (px, py) in path:
                    x_mm, y_mm = to_page_mm(px, py)
                    pts.append(rotate_xy(x_mm, y_mm, self.angle_deg))

                self._pen_up()
                self._move_to(pts[0][0], pts[0][1], FEED_TRAVEL, task=task)
                self._pen_down()
                for x, y in pts[1:]:
                    self._move_to(x, y, self.feed_draw, task=task)
            self._pen_up()
            self._move_to(0, 0, FEED_TRAVEL, task=task)

            # next text write starts on a fresh line below the image
            self.cur_y = self.bed_h - self.margin - self.text_height
            return "ok" if self.auto_clean else "ok (board not cleaned - manual mode)"

    def manual_clean(self, task=None):
        """Entry point for the standalone 'Clean now' button/route - acquires
        the lock itself since, unlike clean_page(), it isn't called from
        inside an already-locked write_line/plot_response/draw_image_paths
        call. Accepts a task so cleaning is cancellable like everything else -
        this was previously missing, which meant a manual clean couldn't be
        interrupted and anything queued behind it just had to wait it out."""
        with self.lock:
            self.clean_page(task=task)
            return "board cleaned"

    def set_clean_mode(self, auto):
        with self.lock:
            self.auto_clean = bool(auto)
            return self.auto_clean

    def close(self):
        self._pen_up()


# =========================================================================
# 3. FLASK WEB UI (the "typer")
# =========================================================================

app = Flask(__name__)
PLOTTER = None   # set in main()

# ---- Task tracking: only one write/draw task runs at a time, in a
# background thread, so it can be cancelled/paused/queried from separate
# HTTP requests (e.g. a later Telegram message) without blocking on it. ----
current_task = None
current_task_lock = threading.Lock()
_next_task_id = 1


def run_task(kind, fn, *args, **kwargs):
    """Starts fn(*args, task=task, **kwargs) in a background thread as the
    tracked current task. Returns the Task, or None if one is already
    active (caller should report "busy" rather than starting a second one -
    the hardware can only do one thing at a time anyway)."""
    global current_task, _next_task_id
    with current_task_lock:
        if current_task is not None and current_task.status in ("PENDING", "RUNNING", "PAUSED"):
            return None
        task = Task(_next_task_id, kind)
        _next_task_id += 1
        current_task = task

    def worker():
        task.status = "RUNNING"
        try:
            fn(*args, task=task, **kwargs)
            if task.status != "CANCELLED":
                task.status = "COMPLETED"
                PLOTTER.return_to_home()   # park out of the way, don't block the view
        except TaskCancelled:
            task.status = "CANCELLED"
            PLOTTER.return_to_home()
        except Exception as e:
            task.status = "FAILED"
            task.error = str(e)
            PLOTTER.return_to_home()

    threading.Thread(target=worker, daemon=True).start()
    return task


PAGE = """<!doctype html>
<html><head><title>CNC Terminal</title>
<style>
  body{background:#111;color:#0f0;font-family:monospace;margin:40px auto;
       max-width:640px}
  h3{color:#0ff;margin-top:28px;margin-bottom:8px}
  #hist{border:1px solid #0f0;padding:12px;min-height:200px;
        white-space:pre-wrap;margin-bottom:12px}
  input[type=text]{width:100%;background:#000;color:#0f0;border:1px solid #0f0;
        font-family:monospace;font-size:18px;padding:8px}
  #status{color:#ff0;margin-top:8px}
  .controls{display:flex;gap:20px;margin-bottom:16px;flex-wrap:wrap}
  .ctrl{flex:1;min-width:150px}
  .ctrl label{display:block;font-size:12px;margin-bottom:4px}
  .ctrl span{float:right;color:#0ff}
  .ctrl input[type=range]{width:100%;accent-color:#0f0}
</style></head><body>
<h2>CNC WEB TERMINAL</h2>

<h3>Active task</h3>
<div class="controls">
  <div class="ctrl"><button id="pauseBtn">Pause</button></div>
  <div class="ctrl"><button id="resumeBtn">Resume</button></div>
  <div class="ctrl"><button id="cancelBtn">Cancel</button></div>
</div>
<div id="taskStatus">idle</div>

<h3>Board cleaning (applies to everything below)</h3>
<div class="controls">
  <div class="ctrl">
    <label>Mode</label>
    <label style="font-weight:normal;display:inline-block;margin-right:16px">
      <input type="radio" name="cleanMode" id="cleanAuto" value="auto" checked> Auto clean
    </label>
    <label style="font-weight:normal;display:inline-block">
      <input type="radio" name="cleanMode" id="cleanManual" value="manual"> Manual clean
    </label>
  </div>
  <div class="ctrl">
    <button id="cleanNowBtn">Clean now</button>
  </div>
</div>
<div id="cleanStatus"></div>

<h3>Type &amp; plot</h3>
<div class="controls">
  <div class="ctrl">
    <label>Font size (mm) <span id="fsVal">10</span></label>
    <input type="range" id="fontSize" min="4" max="40" step="1" value="10">
  </div>
  <div class="ctrl">
    <label>Speed (mm/min) <span id="spdVal">1500</span></label>
    <input type="range" id="speed" min="100" max="8000" step="100" value="1500">
  </div>
</div>
<input type="text" id="line" placeholder="type something + Enter -> plotter writes it" autofocus>
<div id="status"></div>

<h3>Draw an image</h3>
<input type="file" id="imageFile" accept="image/*">
<button id="drawImageBtn">Draw image</button>
<div id="imgStatus"></div>

<h3>History</h3>
<div id="hist"></div>


<script>
const hist = document.getElementById('hist');
const inp  = document.getElementById('line');
const st   = document.getElementById('status');
const imageFile   = document.getElementById('imageFile');
const drawImageBtn = document.getElementById('drawImageBtn');
const imgSt = document.getElementById('imgStatus');
const pauseBtn = document.getElementById('pauseBtn');
const resumeBtn = document.getElementById('resumeBtn');
const cancelBtn = document.getElementById('cancelBtn');
const taskSt = document.getElementById('taskStatus');
const cleanAuto = document.getElementById('cleanAuto');
const cleanManual = document.getElementById('cleanManual');
const cleanNowBtn = document.getElementById('cleanNowBtn');
const cleanSt = document.getElementById('cleanStatus');
const fontSize = document.getElementById('fontSize');
const speed    = document.getElementById('speed');
const fsVal  = document.getElementById('fsVal');
const spdVal = document.getElementById('spdVal');
fontSize.addEventListener('input', () => fsVal.textContent = fontSize.value);
speed.addEventListener('input', () => spdVal.textContent = speed.value);

inp.addEventListener('keydown', async e => {
  if (e.key !== 'Enter' || !inp.value) return;
  const text = inp.value;
  hist.textContent += '> ' + text + '\\n';
  inp.value = '';
  st.textContent = 'plotting...';
  const r = await fetch('/plot', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        text: text,
        font_size: parseFloat(fontSize.value),
        speed: parseFloat(speed.value)
      })});
  const j = await r.json();
  st.textContent = j.status;
});

drawImageBtn.addEventListener('click', async () => {
  if (!imageFile.files.length) { imgSt.textContent = 'choose an image first'; return; }
  const fd = new FormData();
  fd.append('image', imageFile.files[0]);
  imgSt.textContent = 'starting...';
  const r = await fetch('/draw_image', {method: 'POST', body: fd});
  const j = await r.json();
  if (j.status !== 'started') { imgSt.textContent = j.status; return; }
  imgSt.textContent = 'drawing (' + j.stroke_count + ' strokes)...';
  hist.textContent += '[image: ' + imageFile.files[0].name + '] started\\n';
  await pollTaskUntilDone();
  hist.textContent += '[image: ' + imageFile.files[0].name + '] ' + taskSt.textContent + '\\n';
});

async function pollTaskUntilDone() {
  while (true) {
    const r = await fetch('/task/status');
    const j = await r.json();
    if (j.status === 'idle') { imgSt.textContent = 'done'; return; }
    if (['COMPLETED', 'CANCELLED', 'FAILED'].includes(j.status)) {
      imgSt.textContent = j.status + (j.error ? (': ' + j.error) : '');
      return;
    }
    await new Promise(res => setTimeout(res, 500));
  }
}

async function refreshTaskStatus() {
  try {
    const r = await fetch('/task/status');
    const j = await r.json();
    taskSt.textContent = j.status === 'idle' ? 'idle'
      : j.status + (j.progress ? (' - ' + j.progress) : '') + (j.error ? (': ' + j.error) : '');
  } catch (e) { /* ignore */ }
}
setInterval(refreshTaskStatus, 1000);
refreshTaskStatus();

pauseBtn.addEventListener('click', async () => {
  const r = await fetch('/task/pause', {method: 'POST'});
  const j = await r.json();
  taskSt.textContent = j.status;
});
resumeBtn.addEventListener('click', async () => {
  const r = await fetch('/task/resume', {method: 'POST'});
  const j = await r.json();
  taskSt.textContent = j.status;
});
cancelBtn.addEventListener('click', async () => {
  const r = await fetch('/task/cancel', {method: 'POST'});
  const j = await r.json();
  taskSt.textContent = j.status;
});

async function setCleanMode(mode) {
  const r = await fetch('/set_clean_mode', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({mode: mode})});
  const j = await r.json();
  cleanSt.textContent = 'mode: ' + (j.auto_clean ? 'auto clean' : 'manual clean');
}
cleanAuto.addEventListener('change', () => { if (cleanAuto.checked) setCleanMode('auto'); });
cleanManual.addEventListener('change', () => { if (cleanManual.checked) setCleanMode('manual'); });

cleanNowBtn.addEventListener('click', async () => {
  cleanSt.textContent = 'starting clean...';
  const r = await fetch('/clean', {method: 'POST'});
  const j = await r.json();
  if (j.status !== 'started') { cleanSt.textContent = j.status; return; }
  cleanSt.textContent = 'cleaning... (use Cancel above to stop)';
  await pollTaskUntilDone();
  cleanSt.textContent = taskSt.textContent;
});

// sync the radio buttons to whatever the server's actual mode is on page load
(async () => {
  try {
    const r = await fetch('/status');
    const j = await r.json();
    cleanAuto.checked = !!j.auto_clean;
    cleanManual.checked = !j.auto_clean;
  } catch (e) { /* ignore - defaults to auto */ }
})();
</script></body></html>"""


@app.route("/")
def index():
    return PAGE


@app.route("/plot", methods=["POST"])
def plot():
    data = request.json or {}
    text = data.get("text", "")
    status = PLOTTER.plot_text(
        text,
        text_height=data.get("font_size"),
        feed_draw=data.get("speed"),
    )
    PLOTTER.return_to_home()   # park out of the way, don't block the view
    return jsonify({"status": status})


@app.route("/write_text", methods=["POST"])
def write_text():
    """Simple hook for external agents (e.g. an OpenClaw skill over Telegram):
    takes text that's already been generated elsewhere (a cloud AI's answer,
    a scheduled reminder, etc.) and just writes it on the board, auto-fitting
    the font. No LLM call happens in this app for this route - by design,
    the "thinking" is expected to have already happened upstream.
    Runs as a background task - returns immediately with a task_id so it
    can be cancelled/paused/queried via /task/* while it's still writing."""
    data = request.json or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"status": "empty text"})
    task = run_task("write", PLOTTER.plot_response, text, feed_draw=data.get("speed"))
    if task is None:
        return jsonify({"status": "busy - a task is already running, cancel or wait for it first"})
    return jsonify({"status": "started", "task_id": task.id})


@app.route("/task/status")
def task_status():
    """Poll the current/most recent task's state and progress."""
    if current_task is None:
        return jsonify({"status": "idle"})
    return jsonify(current_task.as_dict())


@app.route("/task/cancel", methods=["POST"])
def task_cancel():
    """Stop the active task as soon as safely possible, then return the
    machine to HOME. Takes priority over anything else - a cancelled task
    never resumes."""
    if current_task is None or current_task.status not in ("PENDING", "RUNNING", "PAUSED"):
        return jsonify({"status": "no active task to cancel"})
    current_task.cancel_event.set()
    current_task.pause_event.clear()   # unblock a paused task so it notices the cancellation
    return jsonify({"status": "cancel requested"})


@app.route("/task/pause", methods=["POST"])
def task_pause():
    """Pause after the current stroke completes - pen lifts, position and
    progress are kept, does NOT return home. Only a running task can pause."""
    if current_task is None or current_task.status != "RUNNING":
        return jsonify({"status": "no running task to pause"})
    current_task.pause_event.set()
    current_task.status = "PAUSED"
    return jsonify({"status": "paused"})


@app.route("/task/resume", methods=["POST"])
def task_resume():
    """Continue a paused task from exactly where it left off."""
    if current_task is None or current_task.status != "PAUSED":
        return jsonify({"status": "no paused task to resume"})
    current_task.pause_event.clear()
    current_task.status = "RUNNING"
    return jsonify({"status": "resumed"})


@app.route("/estimate", methods=["POST"])
def estimate():
    """Check whether given text would fit in the remaining board space
    WITHOUT actually writing it - lets an agent warn the user or shrink a
    request before committing to a task."""
    data = request.json or {}
    text = data.get("text", "")
    with PLOTTER.lock:
        available_h = PLOTTER.cur_y - PLOTTER.margin
        bed_w, margin = PLOTTER.bed_w, PLOTTER.margin
    fits_without_cleaning = available_h >= TEXT_HEIGHT_MIN * 1.6
    fs, lines = fit_text_to_page(text, bed_w, margin,
                                  max(available_h, bed_w - 2 * margin))
    return jsonify({
        "font_size": fs,
        "line_count": len(lines),
        "fits_in_remaining_space": fits_without_cleaning,
        "would_need_cleaning_first": not fits_without_cleaning,
    })


SCHEDULE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedule.json")
SCHEDULE_CHECK_INTERVAL_S = 30
schedule_lock = threading.Lock()


def load_schedule():
    try:
        with open(SCHEDULE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_schedule(jobs):
    with open(SCHEDULE_FILE, "w") as f:
        json.dump(jobs, f, indent=2)


def scheduler_loop():
    """Runs forever in a background thread: every 30s, checks whether any
    scheduled job's time-of-day matches right now and hasn't already run
    today, and if so writes it on the board. Jobs repeat daily."""
    while True:
        time.sleep(SCHEDULE_CHECK_INTERVAL_S)
        now = datetime.datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        current_hm = now.strftime("%H:%M")
        with schedule_lock:
            jobs = load_schedule()
            changed = False
            for job in jobs:
                if job.get("time") == current_hm and job.get("last_run_date") != today_str:
                    try:
                        PLOTTER.plot_response(job["text"])
                        PLOTTER.return_to_home()   # park out of the way afterward
                    except Exception as e:
                        print(f"scheduled job {job.get('id')} failed: {e}")
                    job["last_run_date"] = today_str
                    changed = True
            if changed:
                save_schedule(jobs)


@app.route("/schedule", methods=["GET"])
def get_schedule():
    """List all scheduled daily writes - e.g. for an agent to read back or
    to write out on the board itself when asked "what's my schedule"."""
    with schedule_lock:
        jobs = load_schedule()
    return jsonify({"jobs": jobs})


@app.route("/schedule", methods=["POST"])
def add_schedule():
    data = request.json or {}
    text = data.get("text", "").strip()
    run_time = data.get("time", "").strip()   # "HH:MM", 24-hour, board's local time
    if not text or not run_time:
        return jsonify({"status": "need both 'text' and 'time' (HH:MM, 24-hour)"})
    try:
        datetime.datetime.strptime(run_time, "%H:%M")
    except ValueError:
        return jsonify({"status": "time must be in HH:MM 24-hour format"})

    with schedule_lock:
        jobs = load_schedule()
        new_id = max((j["id"] for j in jobs), default=0) + 1
        jobs.append({"id": new_id, "text": text, "time": run_time, "last_run_date": None})
        save_schedule(jobs)
    return jsonify({"status": "scheduled", "id": new_id})


@app.route("/schedule/<int:job_id>", methods=["DELETE"])
def delete_schedule(job_id):
    with schedule_lock:
        jobs = load_schedule()
        remaining = [j for j in jobs if j["id"] != job_id]
        found = len(remaining) != len(jobs)
        save_schedule(remaining)
    return jsonify({"status": "deleted" if found else "not found"})


@app.route("/home", methods=["POST"])
def go_home():
    """Explicit on-demand move to home (pen up, to 0,0) - for when the user
    just asks the plotter to get out of the way, without cancelling or
    cleaning anything. Refuses while a task is actively running/paused,
    since that would collide with whatever it's in the middle of - cancel
    first in that case (which already homes automatically anyway)."""
    if current_task is not None and current_task.status in ("PENDING", "RUNNING", "PAUSED"):
        return jsonify({"status": "a task is active - cancel it first (that homes automatically)"})
    PLOTTER.return_to_home()
    return jsonify({"status": "home"})


@app.route("/clean", methods=["POST"])
def clean_now():
    """Runs as a background task, same as write_text/draw_image - so it can
    actually be cancelled mid-clean via /task/cancel instead of blocking
    for the full ~2 minute wipe cycle uninterruptibly."""
    task = run_task("clean", PLOTTER.manual_clean)
    if task is None:
        return jsonify({"status": "busy - a task is already running, cancel or wait for it first"})
    return jsonify({"status": "started", "task_id": task.id})


@app.route("/set_clean_mode", methods=["POST"])
def set_clean_mode():
    data = request.json or {}
    mode = data.get("mode", "auto")
    auto_clean = PLOTTER.set_clean_mode(mode == "auto")
    return jsonify({"status": "ok", "auto_clean": auto_clean})


@app.route("/status")
def status():
    return jsonify({"auto_clean": PLOTTER.auto_clean})


@app.route("/draw_image", methods=["POST"])
def draw_image():
    if not IMAGE_DRAWING_AVAILABLE:
        return jsonify({"status": f"image drawing unavailable: {_image_import_error}"})
    if "image" not in request.files:
        return jsonify({"status": "no image uploaded"})
    file = request.files["image"]
    if file.filename == "":
        return jsonify({"status": "no image selected"})

    suffix = os.path.splitext(file.filename)[1] or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        paths, w_px, h_px = image_to_paths(tmp_path)
    except Exception as e:
        os.remove(tmp_path)
        return jsonify({"status": f"image processing error: {e}"})
    os.remove(tmp_path)

    task = run_task("draw", PLOTTER.draw_image_paths, paths, w_px, h_px)
    if task is None:
        return jsonify({"status": "busy - a task is already running, cancel or wait for it first"})
    return jsonify({"status": "started", "task_id": task.id, "stroke_count": len(paths)})


@app.route("/preview")
def preview():
    """Debug: see the move sequence a line would produce, without sending."""
    text = request.args.get("text", "HELLO")
    saved = PLOTTER.dry_run
    PLOTTER.dry_run = True
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        PLOTTER.write_line(text)
    PLOTTER.dry_run = saved
    return "<pre>" + buf.getvalue() + "</pre>"


def run_flask(host, port):
    # use_reloader=False is required - Flask's reloader spawns a subprocess,
    # which breaks the single-process Bridge connection the App runtime expects.
    app.run(host=host, port=port, threaded=True, use_reloader=False)


def main():
    global PLOTTER
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Print moves instead of calling the Bridge (for testing)")
    ap.add_argument("--width", type=float, default=550,
                    help="Bed width in mm")
    ap.add_argument("--height", type=float, default=400,
                    help="Bed height in mm")
    ap.add_argument("--text-height", type=float, default=10,
                    help="Initial letter height in mm for typed text (adjustable live in the UI)")
    ap.add_argument("--speed", type=float, default=1500,
                    help="Initial drawing speed in mm/min (adjustable live in the UI)")
    ap.add_argument("--clean-mode", choices=["auto", "manual"], default="auto",
                    help="Auto-clean the board when full, or wait for the Clean now button")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--web-port", type=int, default=5000)
    args = ap.parse_args()

    PLOTTER = Plotter(dry_run=args.dry_run,
                       bed_w=args.width, bed_h=args.height,
                       text_height=args.text_height,
                       feed_draw=args.speed,
                       auto_clean=(args.clean_mode == "auto"))

    flask_thread = threading.Thread(
        target=run_flask, args=(args.host, args.web_port), daemon=True
    )
    flask_thread.start()

    scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler_thread.start()

    time.sleep(1)  # give Flask a moment to bind before printing the URL
    ip = get_local_ip()
    print("=" * 50)
    print(f"  CNC Web Terminal running at: http://{ip}:{args.web_port}")
    print("=" * 50)

    # App.run() connects the Bridge and keeps the process alive; it must be
    # called (even with no user_loop) or the MCU side / Bridge never starts.
    try:
        App.run()
    except KeyboardInterrupt:
        PLOTTER.close()


if __name__ == "__main__":
    main()
