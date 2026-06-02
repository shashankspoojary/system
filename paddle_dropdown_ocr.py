# paddle_dropdown_ocr.py
"""
PaddleOCR ONLY for ALL dropdown scrolling OCR (District / Taluk / Cast / Sub Cast / etc).

Goal:
- Use cached PaddleOCR model (en_PP-OCRv5_mobile_rec via paddle_info_panel_ocr._get_ocr)
  for dropdown visible-page OCR.
- Return line dicts compatible with MPF_BOT dropdown clicking:
    [{'text','left','top','width','height','conf'}]
  where left/top are LOCAL to the dropdown region (NOT absolute screen coords).
- No fallback to any older OCR engine (Tesseract / etc) inside this module.
"""

from __future__ import annotations

import os
import cv2
import numpy as np
from PIL import ImageGrab

# Reuse the exact cached PaddleOCR initializer + parsing helpers you already have
from paddle_info_panel_ocr import (
    _get_ocr,
    _try_extract_items,
    _group_items_to_lines,
    _join_line_items,
)

_DD_OCR = None

def _get_dropdown_engine():
    global _DD_OCR
    if _DD_OCR is None:
        # dropdown text is upright; disabling orientation improves speed & stability
        _DD_OCR = _get_ocr(use_orientation=False)
    return _DD_OCR


def ocr_dropdown_lines(
    region_bbox,
    debug_dir: str = "debug_logs",
    debug_name: str | None = None,
    min_conf: float = 0.20,
    max_side: int = 1400,
    y_tol: int = 12,
):
    """
    OCR the visible dropdown region and return merged visual lines with bboxes (local coords).

    region_bbox: (x1,y1,x2,y2) absolute screen coordinates.
    """
    ocr = _get_dropdown_engine()
    if ocr is None:
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

    # debug snapshot
    if debug_name:
        try:
            os.makedirs(debug_dir, exist_ok=True)
            cv2.imwrite(os.path.join(debug_dir, f"{debug_name}_dd_crop.png"), img_bgr)
        except Exception:
            pass

    # 4) run PaddleOCR (det+rec)
    try:
        result = ocr.ocr(img_bgr)
    except Exception:
        return []

    # 5) parse items with boxes
    items = _try_extract_items(result)

    # Handle dict-style output: rec_texts/rec_scores/rec_polys (or dt_polys)
    if not items:
        try:
            if isinstance(result, list) and result and isinstance(result[0], dict):
                d = result[0]
                rec_texts = d.get("rec_texts") or []
                rec_scores = d.get("rec_scores") or []
                rec_polys = d.get("rec_polys") or d.get("dt_polys") or []
                if rec_texts and rec_polys:
                    if (not rec_scores) or (len(rec_scores) != len(rec_texts)):
                        rec_scores = [1.0] * len(rec_texts)
                    items = []
                    for txt, conf, poly in zip(rec_texts, rec_scores, rec_polys):
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

    # rescale boxes back to ORIGINAL crop coords (do this ONCE)
    if scale != 1.0:
        inv = 1.0 / float(scale)
        for ln in out_lines:
            ln["left"] = int(round(ln.get("left", 0) * inv))
            ln["top"] = int(round(ln.get("top", 0) * inv))
            ln["width"] = max(1, int(round(ln.get("width", 1) * inv)))
            ln["height"] = max(1, int(round(ln.get("height", 1) * inv)))

    return out_lines
