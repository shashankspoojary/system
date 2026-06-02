# paddle_info_panel_ocr.py
"""
PaddleOCR-based OCR module ONLY for MPF Info Panel extraction.

Design goals:
- Used ONLY for info panel text extraction (not dropdowns, not input fields).
- "Turns on" only when called, then "turns off" after extraction:
  we create PaddleOCR instance, run OCR, then explicitly delete and gc.collect().
- Fix wrapped/continued values (especially Full Name / Father Name / Mother Name).
- Enforce safety rules:
    * Pincode: exactly 6 digits, numbers only
    * Name fields: letters + spaces only (keep spaces, do not collapse),
      allow '.' only if it exists in original value
    * Code fields: exactly 3 letters + 10 digits (MBI/RAI/PHI/FAI)
"""

from __future__ import annotations

import os
import re
import gc
import cv2
import numpy as np
from PIL import ImageGrab

# Paddle import happens inside the function as well for safer lazy load,
# but we keep it here too if environment supports it.
try:
    from paddleocr import PaddleOCR
except Exception:
    PaddleOCR = None
# --------------------------
# PaddleOCR engine cache (init once, reuse)
# --------------------------
_OCR_CACHE = {}  # key: bool(use_orientation) -> PaddleOCR instance

def _get_ocr(use_orientation: bool):
    """
    Creates PaddleOCR ONCE and reuses it.
    Speed focus:
      - disable doc orientation classify + doc unwarping (these load PP-LCNet_x1_0_doc_ori + UVDoc)
      - prefer PP-OCRv5_mobile_det instead of server det
      - optionally disable textline orientation (use_orientation=False when calling)
    """
    if PaddleOCR is None:
        return None

    key = bool(use_orientation)
    if key in _OCR_CACHE:
        return _OCR_CACHE[key]

    # Base args that are supported in PaddleOCR 3.x pipeline.
    # (These are exactly the modules you saw loading: doc_ori, UVDoc, textline_ori)
    kwargs = dict(
        lang="en",
        use_textline_orientation=key,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        # force lighter detector (default can be server_det)
        text_detection_model_name="PP-OCRv5_mobile_det",
    )

    # Some installs use this recognition name (you already saw it in logs)
    # If your version doesn't accept it, fallback below.
    kwargs_rec = dict(text_recognition_model_name="en_PP-OCRv5_mobile_rec")

    # Try a few compatible constructor variants (PaddleOCR API varies across 3.x)
    tries = [
        {**kwargs, **kwargs_rec},
        kwargs,  # if rec name is not accepted, Paddle will pick default rec
    ]

    last_err = None
    for kw in tries:
        try:
            _OCR_CACHE[key] = PaddleOCR(**kw)
            return _OCR_CACHE[key]
        except Exception as e:
            last_err = e

    raise RuntimeError(f"Failed to initialize PaddleOCR with speed settings. Last error: {last_err}")

def warmup_info_panel_ocr(use_orientation: bool = False):
    """
    Force PaddleOCR engine init at program start so F3 doesn't pay init cost.
    """
    ocr = _get_ocr(use_orientation=use_orientation)
    return ocr is not None


# --------------------------
# Helpers inspired by paddle_test.py
# --------------------------

def _clean_text(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"\s*:\s*", ": ", s)
    return s.strip()


def _try_extract_items(result):
    """
    Robustly extract (text, conf, box) from different PaddleOCR / PaddleX output formats.
    Returns list of tuples: (text, conf, box4pts or None)
    """

    items = []

    def add_item(text, conf=None, box=None):
        if text is None:
            return
        text = str(text).strip()
        if not text:
            return
        try:
            conf_val = float(conf) if conf is not None else 1.0
        except Exception:
            conf_val = 1.0
        items.append((text, conf_val, box))

    def walk(obj):
        # Classic PaddleOCR v2: [ [ [box, (text, conf)], ... ] ]
        if isinstance(obj, list):
            for x in obj:
                walk(x)
            return

        # Dict style outputs (PaddleX pipelines often use this)
        if isinstance(obj, dict):
            # Common keys seen across versions
            # 1) Single entry dict
            if "text" in obj:
                add_item(obj.get("text"), obj.get("score") or obj.get("confidence") or obj.get("conf"),
                         obj.get("box") or obj.get("bbox") or obj.get("points") or obj.get("poly"))
                return
            if "rec_text" in obj:
                add_item(obj.get("rec_text"), obj.get("rec_score"),
                         obj.get("dt_poly") or obj.get("dt_polys") or obj.get("box"))
                return

            # 2) Some pipelines store lists under keys
            for k in ("res", "results", "result", "data", "lines", "texts", "ocr", "predictions"):
                if k in obj:
                    walk(obj[k])
                    return

            # Otherwise walk all values
            for v in obj.values():
                walk(v)
            return

        # Tuple styles
        if isinstance(obj, tuple):
            # Sometimes (text, score) or (box, (text, score))
            if len(obj) == 2:
                a, b = obj
                # (text, score)
                if isinstance(a, str) and isinstance(b, (int, float)):
                    add_item(a, b, None)
                    return
                # (box, (text, score))
                if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(b) >= 2:
                    add_item(b[0], b[1], a)
                    return
            # Fallback: walk contents
            for x in obj:
                walk(x)
            return

        # Primitive: ignore
        return

    # First try a direct parse of classic form:
    if isinstance(result, list):
        # attempt classic exactly
        try:
            for page in result:
                if isinstance(page, list):
                    for item in page:
                        if (
                            isinstance(item, list)
                            and len(item) >= 2
                            and isinstance(item[0], (list, tuple))
                            and isinstance(item[1], (list, tuple))
                            and len(item[1]) >= 2
                        ):
                            box = item[0]
                            text = item[1][0]
                            conf = item[1][1]
                            add_item(text, conf, box)
            if items:
                return items
        except Exception:
            pass

    # If classic parse found nothing, walk recursively for dict/paddlex formats
    walk(result)
    return items



def _box_to_ltrb(box4):
    # box4 = [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    xs = [p[0] for p in box4]
    ys = [p[1] for p in box4]
    l = int(min(xs)); r = int(max(xs))
    t = int(min(ys)); b = int(max(ys))
    return l, t, r, b


def _group_items_to_lines(items, y_tol=12):
    """
    Group OCR boxes into visual lines by y-center proximity, then sort left->right.
    Returns: list of lines, where each line is list of dicts:
      {text, conf, left, top, width, height, cx, cy}
    """
    rows = []
    for text, conf, box in items:
        l, t, r, b = _box_to_ltrb(box)
        cx = (l + r) / 2.0
        cy = (t + b) / 2.0
        rows.append({
            "text": text,
            "conf": conf,
            "left": l,
            "top": t,
            "width": max(1, r - l),
            "height": max(1, b - t),
            "cx": cx,
            "cy": cy,
        })

    # sort by y
    rows.sort(key=lambda d: d["cy"])

    lines = []
    for r in rows:
        placed = False
        for ln in lines:
            if abs(ln["cy_mean"] - r["cy"]) <= y_tol:
                ln["items"].append(r)
                # update mean
                ln["cy_mean"] = sum(i["cy"] for i in ln["items"]) / float(len(ln["items"]))
                placed = True
                break
        if not placed:
            lines.append({"cy_mean": r["cy"], "items": [r]})

    # sort each line by x
    out = []
    for ln in lines:
        ln_items = sorted(ln["items"], key=lambda d: d["cx"])
        out.append(ln_items)

    # final sort by y again (stable)
    out.sort(key=lambda line: sum(i["cy"] for i in line) / float(len(line)))
    return out


def _join_line_items(line_items):
    # join items with spaces (do NOT collapse multiple spaces later for name fields)
    parts = []
    for it in line_items:
        txt = (it.get("text") or "").strip()
        if txt:
            parts.append(txt)
    return " ".join(parts).strip()


# --------------------------
# Wrapped-value parsing
# --------------------------

def _norm_key(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _build_key_aliases(canonical_fields):
    """
    Build a small alias map for common OCR label variants.
    (We keep this conservative to avoid wrong merges.)
    """
    aliases = { _norm_key(k): k for k in canonical_fields }

    # Add a few common variants you actually see
    manual = {
        "fullname": "Full Name",
        "full name": "Full Name",
        "fathername": "Father Name",
        "father name": "Father Name",
        "mothername": "Mother Name",
        "mother name": "Mother Name",
        "pincode": "Pincode",
        "pin code": "Pincode",
        "mbicode": "MBI Code",
        "rai code": "RAI Code",
        "phicode": "PHI Code",
        "faicode": "FAI Code",
        "app no": "App No",
        "application no": "App No",
        "date of birth": "Date of Birth",
        "dob": "Date of Birth",
        "gender": "Gender",
        "genlder": "Gender",
        "taluk": "Taluk",
        "raluk": "Taluk",
        "sub cast": "Sub Caste",
        "subcast": "Sub Caste",
    }
    for k, v in manual.items():
        aliases[_norm_key(k)] = v
    return aliases


def _looks_like_new_field(line_text, key_aliases) -> bool:
    line = (line_text or "").strip()
    if not line:
        return False

    # Normal case: "Key: Value"
    if ":" in line:
        left = line.split(":", 1)[0]
        nk = _norm_key(left)
        return nk in key_aliases

    # NEW: colon-missing case like "GenderMale" or "TalukJaynagar"
    ln = _norm_key(line).replace(" ", "")
    for k in key_aliases.keys():
        kk = k.replace(" ", "")
        if ln.startswith(kk) and len(ln) > len(kk):
            return True

    return False


def _parse_kv_with_wrapped_lines(ordered_lines, canonical_fields):
    """
    ordered_lines: list[str] in top-to-bottom reading order.
    Returns dict: canonical_field -> raw_value (as seen)
    """
    key_aliases = _build_key_aliases(canonical_fields)
    kv = {}

    i = 0
    while i < len(ordered_lines):
        line = (ordered_lines[i] or "").strip()
        if not line:
            i += 1
            continue

        if ":" not in line:
            i += 1
            continue

        left, right = line.split(":", 1)
        nk = _norm_key(left)
        field = key_aliases.get(nk)
        if not field:
            i += 1
            continue

        value = right.strip()

        # ---- Wrapped continuation fix for name fields ----
        if field in ("Full Name", "Father Name", "Mother Name"):
            j = i + 1
            while j < len(ordered_lines):
                nxt = (ordered_lines[j] or "").strip()
                if not nxt:
                    j += 1
                    continue

                # If next line looks like a new "Key: Value" -> stop
                if _looks_like_new_field(nxt, key_aliases):
                    break

                # Otherwise it is probably continuation of the name
                # Keep spaces and do NOT add punctuation.
                if value:
                    value = value + " " + nxt
                else:
                    value = nxt
                j += 1

            i = j
        else:
            i += 1

        kv[field] = value

    return kv


# --------------------------
# Safety rules
# --------------------------

_re_spaces = re.compile(r"[ \t]+")

def _sanitize_pincode(v: str) -> str:
    digits = re.sub(r"\D+", "", (v or ""))
    if len(digits) == 6:
        return digits
    # If OCR gave more, try last 6 (common if leading junk)
    if len(digits) > 6:
        tail = digits[-6:]
        if len(tail) == 6:
            return tail
    return ""  # invalid -> empty (bot should skip typing)

def _sanitize_code_3alpha_10digit(v: str, prefix: str) -> str:
    s = (v or "").strip().upper()

    # Keep only alnum
    s = re.sub(r"[^A-Z0-9]+", "", s)

    # Force prefix for first 3 letters
    if not prefix or len(prefix) != 3:
        prefix = s[:3] if len(s) >= 3 else (prefix or "")

    # Everything after prefix
    rest = s[3:] if len(s) >= 3 else ""

    # Strip trailing junk (common: trailing letters/punct)
    rest = re.sub(r'[^0-9A-Z]+$', '', rest)
    #rest = re.sub(r'[A-Z]+$', '', rest)

    # OCR noise correction (same spirit as your ECI cleaner in MPF_BOT_V7_3.py)
    ocr_map = str.maketrans({
        "I": "1", "L": "1", "|": "1", "!": "1",
        "O": "0", "Q": "0", "D": "0",
        "S": "5", "$": "5",
        "B": "8",
        "Z": "2",
        "G": "6",
        "T": "7",
        "A": "4",
    })

    rest = rest.translate(ocr_map)
    rest_digits = "".join(ch for ch in rest if ch.isdigit())

    if len(rest_digits) == 10:
        return prefix + rest_digits

    # If OCR gave extra digits, take last 10 (common)
    if len(rest_digits) > 10:
        return prefix + rest_digits[-10:]

    return ""  # invalid / incomplete

def _fix_common_label_typos(line: str) -> str:
    """Fix common OCR mistakes in field labels before parsing."""
    s = (line or "").strip()

    # Normalize spacing around ':'
    s = re.sub(r"\s*:\s*", ": ", s)

    # Common label OCR mistakes you showed
    # Genlder -> Gender
    s = re.sub(r"(?i)^genlder\s*:\s*", "Gender: ", s)
    s = re.sub(r"(?i)^genlder", "Gender", s)

    # raluk -> Taluk
    s = re.sub(r"(?i)^raluk\s*:\s*", "Taluk: ", s)
    s = re.sub(r"(?i)^raluk", "Taluk", s)

    # SubCast -> Sub Caste (your canonical key might be Sub-Caste; map later)
    s = re.sub(r"(?i)^subcast\s*:\s*", "Sub Cast: ", s)

    # If OCR ever merges key+value without colon like "GenlderMale"
    s = re.sub(r"(?i)^(genlder|gender)\s*(male|female)\b", r"Gender: \2", s)
    s = re.sub(r"(?i)^(raluk|taluk)\s*([a-z].+)$", r"Taluk: \2", s)

    return s

def _sanitize_name_keep_spaces(raw_value: str) -> str:
    """
    Enforce:
    - only letters + spaces
    - DO NOT remove spaces between tokens
    - DO NOT add punctuation
    - allow '.' ONLY if it exists in original (but requirement says names should be alphabetic;
      your note allows '.' if present in original, so we keep it if present).
    """
    s = (raw_value or "")

    allow_dot = "." in s
    # Keep exact spaces pattern as much as possible: we won't collapse multiple spaces,
    # but we will remove tabs and weird whitespace to normal spaces.
    s = s.replace("\t", " ")

    out_chars = []
    for ch in s:
        if ch.isalpha() or ch == " ":
            out_chars.append(ch)
        elif ch == "." and allow_dot:
            out_chars.append(ch)
        else:
            # drop digits/symbols like []
            continue

    # Do NOT collapse spaces like "R R" -> "RR". Keep as typed.
    cleaned = "".join(out_chars).strip()
    return cleaned

def apply_info_panel_safety(mapped: dict) -> dict:
    out = dict(mapped or {})

    # Pincode: exactly 6 digits
    if "Pincode" in out:
        out["Pincode"] = _sanitize_pincode(out.get("Pincode"))

    # Names: letters + spaces only (and '.' only if originally present)
    for k in ("Full Name", "Father Name", "Mother Name"):
        if k in out:
            out[k] = _sanitize_name_keep_spaces(out.get(k))

    # Codes: 3 letters + 10 digits
    code_map = {
        "MBI Code": "MBI",
        "RAI Code": "RAI",
        "PHI Code": "PHI",
        "FAI Code": "FAI",
    }
    for field, prefix in code_map.items():
        if field in out:
            out[field] = _sanitize_code_3alpha_10digit(out.get(field), prefix)

    return out


# --------------------------
# Main public function
# --------------------------
class PaddleInfoPanelSession:
    """
    Keeps PaddleOCR initialized for a short time (one form),
    so we can OCR multiple passes without re-initializing models.
    Call .close() when done.
    """
    def __init__(self, use_orientation=True):
        if PaddleOCR is None:
            raise RuntimeError("PaddleOCR import failed. Install paddleocr / paddlepaddle first.")
        # ✅ Reuse the cached PaddleOCR instance (loads once, reused forever)
        self.ocr = _get_ocr(bool(use_orientation))

    def ocr_and_parse(self, region_bbox, canonical_fields, debug_dir=None, debug_prefix="info_paddle",
                      min_conf=0.35):
        # --- everything below is the same screenshot+preprocess logic you already use ---
        x1, y1, x2, y2 = region_bbox

        pil = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        img_rgb = np.array(pil)
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

        if debug_dir:
            os.makedirs(debug_dir, exist_ok=True)
            cv2.imwrite(os.path.join(debug_dir, f"{debug_prefix}_crop.png"), img_bgr)

        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.convertScaleAbs(gray, alpha=1.4, beta=0)
        img_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        if debug_dir:
            cv2.imwrite(os.path.join(debug_dir, f"{debug_prefix}_pre.png"), img_bgr)
        # ✅ ADD THIS before result = self.ocr.ocr(img_bgr)
        h, w = img_bgr.shape[:2]
        mx = max(h, w)

        MAX_SIDE = 1600  # safer for accuracy than 1400
        if mx > MAX_SIDE:
            scale = MAX_SIDE / mx
            img_bgr = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            if debug_dir:
                cv2.imwrite(os.path.join(debug_dir, f"{debug_prefix}_resized.png"), img_bgr)

        result = None
        try:
            result = self.ocr.ocr(img_bgr)
            if debug_dir:
                with open(os.path.join(debug_dir, f"{debug_prefix}_paddle_result_dump.txt"), "w", encoding="utf-8") as f:
                    f.write(repr(result))
        except Exception:
            result = None

        # ---- SAME parsing logic you already had ----
        ordered_lines = []
        try:
            if isinstance(result, list) and result and isinstance(result[0], dict) and "rec_texts" in result[0]:
                rec_texts = result[0].get("rec_texts") or []
                rec_scores = result[0].get("rec_scores") or []
                if rec_scores and len(rec_scores) == len(rec_texts):
                    for t, s in zip(rec_texts, rec_scores):
                        if t and float(s) >= float(min_conf):
                            ordered_lines.append(str(t).strip())
                else:
                    for t in rec_texts:
                        t = str(t).strip()
                        if t:
                            ordered_lines.append(_fix_common_label_typos(t))
            else:
                items = _try_extract_items(result)
                if items and all(b is None for (_, _, b) in items):
                    ordered_lines = [t for (t, _, _) in items]
                else:
                    items = [(t, c, b) for (t, c, b) in items if (t or "").strip() and float(c) >= float(min_conf)]
                    grouped = _group_items_to_lines(items, y_tol=12)
                    ordered_lines = [_join_line_items(line) for line in grouped]
        except Exception:
            ordered_lines = []

        joined_text = _clean_text("\n".join(ordered_lines))

        if debug_dir:
            with open(os.path.join(debug_dir, f"{debug_prefix}_raw.txt"), "w", encoding="utf-8") as f:
                f.write(joined_text)

        kv = _parse_kv_with_wrapped_lines(ordered_lines, canonical_fields)
        kv = apply_info_panel_safety(kv)
        return kv, joined_text

    def close(self):
        # ✅ Do NOT delete the cached OCR model (deleting forces slow reload next time)
        self.ocr = None

def extract_info_panel_paddle(
    region_bbox,
    canonical_fields,
    debug_dir=None,
    debug_prefix="info_paddle",
    min_conf=0.10,
    use_orientation=True,
    session=None,   # ✅ NEW
):
    """
    Returns: (mapped_dict, raw_text)

    If session is provided -> reuse session.ocr (no new PaddleOCR is created).
    If session is None -> create a session internally (slower) and close it.
    """

    # --- Take screenshot / preprocess exactly like before ---
    x1, y1, x2, y2 = region_bbox
    pil = ImageGrab.grab(bbox=(x1, y1, x2, y2))
    img_rgb = np.array(pil)
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)
        cv2.imwrite(os.path.join(debug_dir, f"{debug_prefix}_crop.png"), img_bgr)

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.convertScaleAbs(gray, alpha=1.4, beta=0)
    img_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    if debug_dir:
        cv2.imwrite(os.path.join(debug_dir, f"{debug_prefix}_pre.png"), img_bgr)

    # ✅ IMPORTANT PART: do NOT create PaddleOCR if session already provided
    own_session = False
    if session is None:
        session = PaddleInfoPanelSession(use_orientation=use_orientation)
        own_session = True

    try:
        result = session.ocr.ocr(img_bgr)   # ✅ reuses already-loaded model

        if debug_dir:
            with open(os.path.join(debug_dir, f"{debug_prefix}_paddle_result_dump.txt"), "w", encoding="utf-8") as f:
                f.write(repr(result))

    finally:
        # Only close if we created it inside this function
        if own_session:
            session.close()

    # --- Parse output (your rec_texts dict format) ---
    ordered_lines = []
    try:
        if isinstance(result, list) and result and isinstance(result[0], dict) and "rec_texts" in result[0]:
            rec_texts = result[0].get("rec_texts") or []
            rec_scores = result[0].get("rec_scores") or []

            if rec_scores and len(rec_scores) == len(rec_texts):
                for t, s in zip(rec_texts, rec_scores):
                    t = str(t).strip()
                    if t and float(s) >= float(min_conf):
                        ordered_lines.append(_fix_common_label_typos(t))
            else:
                for t in rec_texts:
                    t = str(t).strip()
                    if t:
                        ordered_lines.append(_fix_common_label_typos(t))
        else:
            # fallback
            items = _try_extract_items(result)
            ordered_lines = [str(t).strip() for (t, _, _) in items if str(t).strip()]
    except Exception:
        ordered_lines = []

    joined_text = _clean_text("\n".join(ordered_lines))

    if debug_dir:
        with open(os.path.join(debug_dir, f"{debug_prefix}_raw.txt"), "w", encoding="utf-8") as f:
            f.write(joined_text)

    kv = _parse_kv_with_wrapped_lines(ordered_lines, canonical_fields)
    kv = apply_info_panel_safety(kv)

    return kv, joined_text


