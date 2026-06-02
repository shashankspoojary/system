# smart_text_reader.py
"""
SMART TEXT READER (no mss)
Multi-pass OCR fusion using:
OpenCV, PIL, PyTesseract, PaddleOCR (if installed), TrOCR (if installed).
"""

import os
import time
import cv2
import numpy as np
import pytesseract
from pytesseract import Output
from PIL import Image, ImageEnhance, ImageFilter
import pyautogui  # used as a reliable screenshot fallback

# Tesseract path if needed (Windows)
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ---------------- Try initialize PaddleOCR (optional) ----------------
ocr_paddle = None

# ---------------- Try initialize TrOCR (optional & slow) ----------------
trocr_available = False
processor = None
trocr_model = None
# -------------------- TrOCR DISABLED --------------------
trocr_processor = None
trocr_model = None


# ---------------- Image enhancement ----------------
def enhance_image(pil_img):
    """Enhance PIL image for OCR: convert to grayscale, denoise, sharpen, and contrast boost."""
    img = pil_img.convert("L")  # grayscale
    img = ImageEnhance.Contrast(img).enhance(1.6)
    img = ImageEnhance.Sharpness(img).enhance(1.6)
    np_img = np.array(img)
    try:
        np_img = cv2.fastNlMeansDenoising(np_img, None, 15, 7, 21)
    except Exception:
        pass
    return Image.fromarray(np_img)

# ---------------- Safe region grab (no mss) ----------------
def grab_region_image(region):
    """
    region expected as (x1, y1, x2, y2).
    Uses PIL.ImageGrab where available, otherwise falls back to pyautogui.screenshot.
    Returns a PIL.Image.
    """
    x1, y1, x2, y2 = region
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)

    # Try PIL.ImageGrab first (works on Windows/macOS)
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        return img
    except Exception:
        # Fallback to pyautogui
        try:
            img = pyautogui.screenshot(region=(x1, y1, width, height))
            return img
        except Exception as e:
            raise RuntimeError(f"Failed to capture screen region: {e}")

# ---------------- Tesseract OCR (group words into lines) ----------------
def ocr_tesseract_lines(pil_img, debug_name=None):
    """Return list of lines: [{'text','left','top','width','height'}] using pytesseract."""
    try:
        prep = np.array(pil_img)
    except Exception:
        prep = pil_img

    data = pytesseract.image_to_data(prep, output_type=Output.DICT, config="--psm 6")
    lines = {}
    n = len(data['text'])
    for i in range(n):
        txt = str(data['text'][i]).strip()
        if not txt:
            continue
        key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
        if key not in lines:
            left = int(data['left'][i])
            top = int(data['top'][i])
            lines[key] = {'words': [], 'left': left, 'top': top, 'width': int(data['width'][i]), 'height': int(data['height'][i])}
        lines[key]['words'].append(txt)
        right = int(data['left'][i]) + int(data['width'][i])
        lines[key]['width'] = max(lines[key]['width'], right - lines[key]['left'])
        lines[key]['height'] = max(lines[key]['height'], int(data['height'][i]))
    out = []
    for k, v in lines.items():
        text = " ".join(v['words'])
        out.append({
            'text': text,
            'left': v['left'],
            'top': v['top'],
            'width': v['width'],
            'height': v['height']
        })
    out.sort(key=lambda x: x['top'])
    return out

# ---------------- PaddleOCR extraction (if available) ----------------
def ocr_paddle_lines(pil_img):
    if ocr_paddle is None:
        return []
    np_img = np.array(pil_img.convert("RGB"))
    try:
        result = ocr_paddle.ocr(np_img, cls=True)
    except Exception:
        return []
    lines = []
    for block in result:
        for line in block:
            coords = line[0]
            (x1, y1), (x2, y2), (x3, y3), (x4, y4) = coords
            txt = line[1][0]
            conf = line[1][1] if len(line[1]) > 1 else None
            lines.append({
                'text': txt,
                'left': int(x1),
                'top': int(y1),
                'width': int(abs(x2 - x1)),
                'height': int(abs(y3 - y1)),
                'conf': conf
            })
    lines.sort(key=lambda x: x['top'])
    return lines

# ---------------- TrOCR (transformer OCR) ----------------
def ocr_trocr_text(pil_img):
    """Return full text string using TrOCR (if available)."""
    if not trocr_available or processor is None or trocr_model is None:
        return ""
    try:
        device = next(trocr_model.parameters()).device
        pixel_values = processor(images=pil_img, return_tensors="pt").pixel_values.to(device)
        generated_ids = trocr_model.generate(pixel_values)
        text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        return text.strip()
    except Exception:
        return ""
def enhance_image_profile(pil_img, profile: str = "default"):
    """
    Variant of enhance_image with simple profiles:
        - default: current behaviour (1.6 contrast/sharpness)
        - soft:    slightly lower contrast/sharpness (for over-sharpened edges)
        - strong:  slightly higher (for faint text)
    """
    img = pil_img.convert("L")

    if profile == "soft":
        c, s = 1.3, 1.3
    elif profile == "strong":
        c, s = 1.9, 1.9
    else:  # "default"
        c, s = 1.6, 1.6

    img = ImageEnhance.Contrast(img).enhance(c)
    img = ImageEnhance.Sharpness(img).enhance(s)
    np_img = np.array(img)
    try:
        np_img = cv2.fastNlMeansDenoising(np_img, None, 15, 7, 21)
    except Exception:
        pass
    return Image.fromarray(np_img)
def smart_ocr_lines_multi(region, debug_name=None, enable_trocr=False,
                          profiles=("default", "soft", "strong")):
    """
    Multi-profile OCR on a single screenshot.

    - Takes ONE screenshot with grab_region_image
    - Runs different enhancement profiles on the same image
    - For each enhanced image, runs Paddle + Tesseract (+ optional TrOCR)
    - Merges unique lines (text-based) into a single sorted list.

    This gives you 'multi-pass' diversity without extra screen capture overhead.
    """
    img = grab_region_image(region)
    unified = []
    seen = set()

    

    def add_lines(lines_src):
        nonlocal unified, seen
        for l in lines_src:
            txt = l.get('text', "").strip()
            if not txt:
                continue
            key = txt.lower()
            if key in seen:
                continue
            seen.add(key)
            unified.append({
                'text': txt,
                'left': int(l.get('left', 0)),
                'top': int(l.get('top', 0)),
                'width': int(l.get('width', 0)),
                'height': int(l.get('height', 0))
            })

    for idx, prof in enumerate(profiles):
        enhanced = enhance_image_profile(img, profile=prof)

        

        paddle_lines = ocr_paddle_lines(enhanced) if ocr_paddle else []
        tess_lines = ocr_tesseract_lines(enhanced)
        trocr_text = ocr_trocr_text(enhanced) if (enable_trocr and trocr_available) else ""

        add_lines(paddle_lines)
        add_lines(tess_lines)

        if trocr_text:
            t = trocr_text.strip()
            key = t.lower()
            if key not in seen:
                seen.add(key)
                unified.append({
                    'text': t,
                    'left': 0, 'top': 0,
                    'width': enhanced.width,
                    'height': enhanced.height
                })

    unified.sort(key=lambda x: x['top'])
    return unified

# ---------------- Fusion function (public) ----------------
def smart_ocr_lines(region, debug_name=None, enable_trocr=False):
    """
    Multi-engine OCR fusion.
    region: (x1, y1, x2, y2)
    Returns list of dicts: [{'text', 'left', 'top', 'width', 'height'}]
    """
    img = grab_region_image(region)
    enhanced = enhance_image(img)

    

    # Run engines
    paddle_lines = ocr_paddle_lines(enhanced) if ocr_paddle else []
    tess_lines = ocr_tesseract_lines(enhanced)
    trocr_text = ocr_trocr_text(enhanced) if (enable_trocr and trocr_available) else ""

    # Merge and deduplicate (prefer paddle -> tesseract -> trocr)
    unified = []
    seen = set()

    def add_lines(lines_src):
        for l in lines_src:
            txt = l.get('text', "").strip()
            key = txt.lower()
            if not txt:
                continue
            if key in seen:
                continue
            seen.add(key)
            unified.append({
                'text': txt,
                'left': int(l.get('left', 0)),
                'top': int(l.get('top', 0)),
                'width': int(l.get('width', 0)),
                'height': int(l.get('height', 0))
            })

    add_lines(paddle_lines)
    add_lines(tess_lines)

    # If trocr produced something unique, append as single large line (fallback)
    if trocr_text:
        if trocr_text.strip().lower() not in seen:
            unified.append({
                'text': trocr_text.strip(),
                'left': 0, 'top': 0, 'width': enhanced.width, 'height': enhanced.height
            })

    # final sort by top coordinate
    unified.sort(key=lambda x: x['top'])
    return unified

def smart_ocr_text(region):
    """Return combined text string for region (use for key-value extraction)."""
    lines = smart_ocr_lines(region)
    return "\n".join([l['text'] for l in lines])
