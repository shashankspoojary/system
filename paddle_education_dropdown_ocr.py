# paddle_education_dropdown_ocr.py
"""
PaddleOCR ONLY for Education dropdown scrolling OCR.

Goal:
- Use cached PaddleOCR model (en_PP-OCRv5_mobile_rec) for Education dropdown lines.
- Return line dicts compatible with MPF_BOT dropdown clicking:
    [{'text','left','top','width','height','conf'}]
  where left/top are LOCAL to the dropdown region (NOT absolute screen coords).
- No fallback to any older OCR engine.
"""

from __future__ import annotations

import os
import cv2
import numpy as np
from PIL import ImageGrab

# Reuse the exact cached PaddleOCR initializer + parsing helpers you already have
# (this is where en_PP-OCRv5_mobile_rec is configured)
from paddle_info_panel_ocr import (
    _get_ocr,
    _try_extract_items,
    _group_items_to_lines,
    _join_line_items,
    _box_to_ltrb,
)

# Keep a local reference to the cached engine (still ultimately cached in paddle_info_panel_ocr)
_EDU_OCR = None


def _get_edu_engine():
    global _EDU_OCR
    if _EDU_OCR is None:
        # use_orientation=False for speed & stability (dropdown text is upright)
        _EDU_OCR = _get_ocr(use_orientation=False)
    return _EDU_OCR


def ocr_education_dropdown_lines(
    region_bbox,
    debug_dir: str | None = None,
    debug_name: str | None = None,
    min_conf: float = 0.20,
    max_side: int = 1400,
    y_tol: int = 12,
):
    """
    OCR the visible Education dropdown region and return merged visual lines
    with bounding boxes (local coords).

    region_bbox: (x1,y1,x2,y2) absolute screen coordinates.
    """
    ocr = _get_edu_engine()
    if ocr is None:
        # PaddleOCR not available -> return empty (NO fallback requested)
        return []

    x1, y1, x2, y2 = map(int, region_bbox)

    # 1) screenshot
    pil = ImageGrab.grab(bbox=(x1, y1, x2, y2))
    img_rgb = np.array(pil)
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

    # 2) light preprocess (helps small fonts)
    #gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    #gray = cv2.convertScaleAbs(gray, alpha=1.35, beta=0)
    #img_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    # 3) optional resize (accuracy without exploding compute)
    h, w = img_bgr.shape[:2]
    mx = max(h, w)
    scale = 1.0
    if mx > max_side:
        scale = max_side / float(mx)
        img_bgr = cv2.resize(
            img_bgr,
            (int(w * scale), int(h * scale)),
            interpolation=cv2.INTER_AREA,
        )

        # debug snapshot disabled
    pass


    # 4) run PaddleOCR (det+rec)
    try:
        result = ocr.ocr(img_bgr)

# NOTE: keep PNG crop logs, but disable raw paddle TXT dumps
# (these were only needed while debugging Education OCR)
# if debug_name:
#     try:
#         with open(os.path.join(debug_dir, f"{debug_name}_edu_paddle_dump.txt"), "w", encoding="utf-8") as f:
#             f.write(repr(result))
#     except Exception:
#         pass

    except Exception:
        return []

    # 5) parse items with boxes
    items = _try_extract_items(result)

    # Education dropdown often returns dict-style output with:
    #   rec_texts[], rec_scores[], rec_polys[] (or dt_polys[])
    # _try_extract_items may not map these into boxed items, so handle it here.
    if not items:
        try:
            if isinstance(result, list) and result and isinstance(result[0], dict):
                d = result[0]

                rec_texts = d.get("rec_texts") or []
                rec_scores = d.get("rec_scores") or []
                rec_polys = d.get("rec_polys") or d.get("dt_polys") or []

                if rec_texts and rec_polys:
                    # scores sometimes missing or wrong length
                    if not rec_scores or len(rec_scores) != len(rec_texts):
                        rec_scores = [1.0] * len(rec_texts)

                    items = []
                    for txt, conf, poly in zip(rec_texts, rec_scores, rec_polys):
                        # poly is a 4-point box (np array / list) -> valid "box"
                        items.append((str(txt).strip(), float(conf), poly))
        except Exception:
            items = []

    if not items:
        return []


    # keep only boxed items with confidence
    boxed = []
    for (txt, conf, box) in items:
        try:
            if not txt or box is None:
                continue
            if float(conf) < float(min_conf):
                continue
            boxed.append((str(txt).strip(), float(conf), box))
        except Exception:
            continue

    if not boxed:
        return []

    # 6) group to visual lines
    grouped = _group_items_to_lines(boxed, y_tol=y_tol)

    out_lines = []
    for line_items in grouped:
        text = _join_line_items(line_items).strip()
        if not text:
            continue

        # union bounding box of the whole line
        l = min(int(it["left"]) for it in line_items)
        t = min(int(it["top"]) for it in line_items)
        r = max(int(it["left"] + it["width"]) for it in line_items)
        b = max(int(it["top"] + it["height"]) for it in line_items)

        # average confidence
        confs = []
        for it in line_items:
            try:
                confs.append(float(it.get("conf", 1.0)))
            except Exception:
                pass
        avg_conf = sum(confs) / len(confs) if confs else 1.0

        # IMPORTANT:
        # coords are already local to the dropdown crop,
        # and MPF_BOT expects local coords (it adds region offset when clicking).
        out_lines.append(
            {
                "text": text,
                "left": l,
                "top": t,
                "width": max(1, r - l),
                "height": max(1, b - t),
                "conf": avg_conf,
            }
        )
        # If we resized the crop for OCR, rescale boxes back to the ORIGINAL crop coords (do this ONCE).
        # Without this, clicks can miss the target line due to coordinate mismatch.
        if scale != 1.0:
            inv = 1.0 / float(scale)
            for ln in out_lines:
                ln["left"] = int(round(ln.get("left", 0) * inv))
                ln["top"] = int(round(ln.get("top", 0) * inv))
                ln["width"] = max(1, int(round(ln.get("width", 1) * inv)))
                ln["height"] = max(1, int(round(ln.get("height", 1) * inv)))


    # sort top-to-bottom
    out_lines.sort(key=lambda d: d.get("top", 0))
    return out_lines
