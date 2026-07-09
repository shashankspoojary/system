
# (Your complete script with DOB/mapping fixes)
# Paste this entire block into your mpf_bot file (it is your original script with targeted fixes)

"""
MPF Autofill Bot — Learning Mode with explicit scroll triggers + Autofill
- Learning Mode (F2): voice-guided, records fields and explicit scroll anchors for
  main/info scroll after specific fields (Religion, Father Name, Pada, ECI Code).
- Autofill Mode (F3): uses saved memory to fill fields, and reproduces recorded scrolls.
- Memory file: bot_memory.json
- Debug screenshots/logs: debug_logs/
"""

import os
import builtins

# =======================================================================
# GLOBALLY DISABLE DEBUG LOG DIRECTORIES (Monkey Patch)
# =======================================================================

# 1. Silently block the creation of the debug folders
_orig_makedirs = os.makedirs
def _block_debug_makedirs(name, mode=0o777, exist_ok=False):
    if "debug_logs" in str(name) or "name_verification_debug" in str(name):
        return  # Do nothing
    _orig_makedirs(name, mode, exist_ok)
os.makedirs = _block_debug_makedirs

# 2. Provide a dummy file object so the bot doesn't crash when it tries to save text
_orig_open = builtins.open
class DummyFile:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def write(self, *args): pass
    def close(self): pass

def _block_debug_open(file, mode='r', *args, **kwargs):
    if "debug_logs" in str(file) or "name_verification_debug" in str(file):
        return DummyFile() # Pretend the file opened successfully
    return _orig_open(file, mode, *args, **kwargs)
builtins.open = _block_debug_open

# =======================================================================
import os
import time
import json
import re
import difflib

import cv2
import numpy as np
import time
import pyautogui

from paddle_info_panel_ocr import _get_ocr

import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
from pytesseract import Output
from PIL import ImageGrab, Image
import cv2
import numpy as np
import pyautogui
import keyboard
import pyttsx3
import queue
import difflib
from difflib import SequenceMatcher
import ctypes
import platform
from dropdown_data import DROPDOWN_OPTIONS
from cast_data import CAST_OPTIONS
from subcast_data import SUBCAST_OPTIONS
from education_data import EDUCATION_OPTIONS
from dropdown_reasoner import should_activate_reasoning, choose_visible_option
from prediction_memory import bump_field_value
import threading
from smart_text_reader import smart_ocr_text, smart_ocr_lines
from paddle_info_panel_ocr import extract_info_panel_paddle, warmup_info_panel_ocr
from reasoning_core import normalize_text as rc_normalize_text  # NEW: for robust button label matching
from info_normalizer import normalize_info_panel_targets
from paddle_education_dropdown_ocr import ocr_education_dropdown_lines
from paddle_dropdown_ocr import ocr_dropdown_lines
# --- Telegram Alerts (No-Forms Termination) ---
try:
    from telegram_alerts import send_telegram_message
except Exception:
    send_telegram_message = None
# --- UI Grace Guard (Take Screenshot / Load Another Form waits) ---
try:
    from ui_grace_guard import wait_button_with_grace
except Exception:
    wait_button_with_grace = None

SPEAK_ENABLED = True

# ---------------- Pause / Resume System ----------------
PAUSED = False
PAUSE_KEY = "F9"
PAUSE_LOCK = threading.Lock()
# ---------------- Skip Current Field (F5) ----------------
SKIP_EVENT = threading.Event()
SKIP_ENABLED = False  # only True while autofill is filling a field

class SkipFieldException(Exception):
    """Raised to abort current field and move to next one."""
    pass
def _telegram_notify_no_forms(reason: str, force: bool = False):
    """Sends a Telegram alert if telegram_alerts module is available."""
    try:
        if send_telegram_message:
            try:
                send_telegram_message(
                    "🚨 MPF BOT ALERT\n"
                    "❗ Bot encountered an issue / Timeout\n"
                    f"📌 Reason: {reason}",
                    force=force  # Passes the force instruction down
                )
            except TypeError:
                print("[TG DEBUG] Warning: telegram_alerts.py doesn't support 'force' argument.")
    except Exception:
        pass

def _telegram_notify_recovery(msg: str):
    """Sends a Telegram message announcing that an error was solved."""
    try:
        if send_telegram_message:
            try:
                send_telegram_message(
                    "✅ MPF BOT RECOVERY\n"
                    "🔄 Automation Resumed Successfully\n"
                    f"📌 {msg}",
                    force=True  # FORCES bypass of the 5-minute timer
                )
            except TypeError:
                print("[TG DEBUG] Warning: telegram_alerts.py doesn't support 'force' argument.")
    except Exception:
        pass

def skip_listener():
    """Background thread: when F5 pressed, request skip of current field."""
    while True:
        try:
            if keyboard.is_pressed("F5"):
                time.sleep(0.25)  # debounce
                SKIP_EVENT.set()
                # don't speak here (autofill is muted), but keep log
                print("[SKIP] F5 pressed -> will skip current field.")
            time.sleep(0.08)
        except:
            time.sleep(0.2)

def pause_listener():
    """Background thread that toggles pause state when F9 pressed."""
    global PAUSED
    while True:
        try:
            if keyboard.is_pressed(PAUSE_KEY):
                time.sleep(0.25)  # debounce
                with PAUSE_LOCK:
                    PAUSED = not PAUSED
                    if PAUSED:
                        print("\n=== BOT PAUSED ===\n")
                        system_speak("Bot paused. Press F9 again to resume.")
                    else:
                        print("\n=== BOT RESUMED ===\n")
                        system_speak("Resuming bot operations.")
            time.sleep(0.15)
        except:
            time.sleep(0.3)

def detect_screen_movement(wait_time=0.5, pixel_threshold=25, min_changed_pixels=100):
    """
    Takes two screenshots slightly apart in time and compares them.
    If enough pixels have changed, it means something on the screen is moving (like a loading bar).
    """
    # Grab first frame and convert to grayscale
    img1 = np.array(pyautogui.screenshot())
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    
    # Wait half a second to let the loading bar move
    time.sleep(wait_time)
    
    # Grab second frame
    img2 = np.array(pyautogui.screenshot())
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    
    # Calculate the absolute difference between the two frames
    diff = cv2.absdiff(gray1, gray2)
    
    # Filter out minor noise, only keep distinct changes
    _, thresh = cv2.threshold(diff, pixel_threshold, 255, cv2.THRESH_BINARY)
    changed_pixels = np.count_nonzero(thresh)
    
    # If the number of changed pixels is higher than our minimum, movement is detected!
    return changed_pixels > min_changed_pixels

def check_pause():
    """If paused, stop all actions until resumed.
       If skip requested during autofill, raise SkipFieldException."""
    global PAUSED, SKIP_ENABLED

    while True:
        with PAUSE_LOCK:
            if not PAUSED:
                break
        time.sleep(0.2)

    # --- NEW: skip support (only during autofill field fill) ---
    if SKIP_ENABLED and SKIP_EVENT.is_set():
        SKIP_EVENT.clear()
        try:
            # close any open dropdown safely
            pyautogui.press("esc")
        except Exception:
            pass
        raise SkipFieldException()


def safe_sleep(seconds):
    """Pause-aware replacement for time.sleep

    IMPORTANT: paused time does NOT count toward the sleep duration.
    """
    remaining = float(seconds)
    while remaining > 0:
        check_pause()
        step = 0.05 if remaining > 0.05 else remaining
        t0 = time.time()
        time.sleep(step)
        remaining -= (time.time() - t0)


# Merge large dropdowns
DROPDOWN_OPTIONS["Cast"] = CAST_OPTIONS
DROPDOWN_OPTIONS["Sub Cast"] = SUBCAST_OPTIONS
DROPDOWN_OPTIONS["Education"] = EDUCATION_OPTIONS


# ---------------- Config ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BOT_MEMORY_FILE = os.path.join(BASE_DIR, "bot_memory.json")
# ---------------- Debug logs permanently disabled ----------------
# Keep the symbol for compatibility, but NOTHING is written to disk.
DEBUG_DIR = None

def _log_mapping_debug(tag: str, data):
    """Append mapping debug snapshots regardless of OCR path."""
    try:
        
        p = os.path.join(DEBUG_DIR, "mapping_debug.txt")
        with open(p, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Tag : {tag}\n")
            f.write(f"Data: {repr(data)}\n")
    except Exception:
        pass

# Set path if needed on Windows:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

VOICE = "en-US-GuyNeural"

def scroll_info_panel_until_rashi_disappears_precise(
    mem,
    check_text="Rashi",
    step_scroll=-1,
    max_steps=120,
    pause_per_step=0.04,
):
    """
    Precisely scroll info panel until `check_text` disappears.
    Uses small scroll steps and OCR check after EACH step.
    Does NOT modify existing scroll rules.
    """

    if "info_panel_region" not in mem:
        return False
    if "scrollbars" not in mem or "info" not in mem["scrollbars"]:
        return False

    region = tuple(mem["info_panel_region"])
    anchor = tuple(mem["scrollbars"]["info"])

    for _ in range(max_steps):
        check_pause()

        # OLD OCR ONLY (fast)
        raw = smart_ocr_text(region) or ""
        if check_text.lower() not in raw.lower():
            return True  # STOP immediately

        # Tiny controlled scroll
        scroll_at(anchor, step_scroll)
        safe_sleep(pause_per_step)

    return False


def scroll_until_disappears(scroll_anchor, region, field_name, next_field=None, step=-120, max_attempts=120,pada_step=-55):
    """
    Scroll until field_name disappears.
    - Religion (input panel): fast safe stop with small fine-step + UI settle.
    - Info panel fields (Pada, ECI Code): scan whole panel, stop when field missing.
    - Others: fallback behavior.
    """
    lname = field_name.lower().strip()

    # --- Religion logic (FAST main scroll, SAFE stop) ---
    if "religion" in lname:
        x1, y1, x2, y2 = region
        label_region = (x1, y1, x1 + 200, y2)

        target = field_name.lower().strip()
        next_target = next_field.lower().strip() if next_field else None

        disappeared_count = 0
        scrolled_once = False

        # ✅ fine-step is ALWAYS small, regardless of fast main step
        fine_step = -18 if step < 0 else 18

        for attempt in range(max_attempts):
            check_pause()

            lines = ocr_region_lines(label_region, debug_name=f"scrollcheck_{field_name}_{attempt}")
            texts = [ln['text'].lower().strip() for ln in lines if ln.get('text') and ln['text'].strip()]

            def fuzzy_contains(tar, txts):
                return any(difflib.SequenceMatcher(None, tar, t).ratio() > 0.6 for t in txts)

            found = fuzzy_contains(target, texts)

            # after at least one scroll, confirm disappearance without scrolling
            if scrolled_once and not found:
                disappeared_count += 1

                # ✅ DO NOT scroll during confirmation
                if disappeared_count >= 2:
                    speak(f"{field_name} disappeared after {attempt} scrolls.")

                    # If next field is provided, we do SMALL safe fine scrolls
                    if next_target:
                        for fine_try in range(10):
                            check_pause()
                            lines2 = ocr_region_lines(label_region, debug_name=f"fine_{field_name}_{fine_try}")
                            texts2 = [ln['text'].lower().strip() for ln in lines2 if ln.get('text') and ln['text'].strip()]

                            if fuzzy_contains(next_target, texts2):
                                speak(f"{next_field} is visible, stopping here.")
                                safe_sleep(1.0)  # ✅ settle before next field work
                                return True

                            # ✅ use safe fine-step, not big fast step
                            scroll_at(scroll_anchor, fine_step)
                            safe_sleep(0.05)

                    safe_sleep(0.2)  # ✅ settle even when no next_field
                    return True

                safe_sleep(0.2)
                continue
            else:
                disappeared_count = 0

            # ✅ main fast scroll (you can increase step safely now)
            scroll_at(scroll_anchor, step)
            scrolled_once = True

        speak(f"Warning: {field_name} still visible after max scrolls.")
        return False

    # --- Info panel (Pada, ECI Code) fast-safe stop ---
    if lname in ["pada", "eci code"]:
        target = lname
        disappeared_count = 0
        scrolled = 0
        scrolled_once = False

        for attempt in range(max_attempts):
            check_pause()
            lines = ocr_region_lines(region, debug_name=f"scrollcheck_{field_name}_{attempt}")
            texts = [ln['text'].lower().strip() for ln in lines if ln.get('text') and ln['text'].strip()]

            found = any(target in t for t in texts)

            if scrolled_once and not found:
                disappeared_count += 1
                if disappeared_count >= 2:
                    speak(f"{field_name} disappeared after {scrolled} scrolls.")
                    return True
                safe_sleep(0.03)
                continue
            else:
                disappeared_count = 0

            # Use a different step only for Pada if provided
            local_step = step
            if pada_step is not None and "pada" in lname:
                local_step = pada_step

            scroll_at(scroll_anchor, local_step)
            scrolled += 1
            scrolled_once = True

        speak(f"Warning: {field_name} still visible after max scrolls.")
        return False

    # --- General fallback for other fields ---
    x1, y1, x2, y2 = region
    label_region = (x1, y1, x1 + 200, y2)
    target = field_name.lower().strip()

    disappeared_count = 0
    scrolled = 0

    for attempt in range(max_attempts):
        check_pause()
        lines = ocr_region_lines(label_region, debug_name=f"scrollcheck_{field_name}_{attempt}")
        texts = [ln['text'].lower().strip() for ln in lines if ln.get('text') and ln['text'].strip()]
        found = any(target in t for t in texts)

        if scrolled >= 2 and not found:
            disappeared_count += 1
            if disappeared_count >= 2:
                speak(f"{field_name} disappeared after {scrolled} scrolls.")
                return True
        else:
            disappeared_count = 0

        scroll_at(scroll_anchor, step)
        scrolled += 1

    speak(f"Warning: {field_name} still visible after max scrolls.")
    return False


def scroll_to_end(scroll_anchor, region, step=-100, max_attempts=60):
    """
    Scroll until the bottom of the panel is reached.
    Uses OCR on the whole region to detect when text stops changing.
    """
    last_text = ""
    stable_count = 0

    for attempt in range(max_attempts):
        # OCR the whole panel
        lines = ocr_region_lines(region, debug_name=f"scrolltoend_{attempt}")
        texts = [ln['text'].strip().lower() for ln in lines if ln['text'].strip()]
        joined = " ".join(texts)

        if joined == last_text:
            stable_count += 1
            if stable_count >= 1:
                speak(f"Reached end after {attempt} scrolls.")
                return True
        else:
            stable_count = 0
            last_text = joined

        scroll_at(scroll_anchor, step)
        time.sleep(0.05)

    speak("Warning: max scrolls reached but end not detected.")
    return False
def scroll_dropdown_to_end(region, scroll_anchor_abs, desired_value=None):
    """
    Scroll a dropdown until end (isolated from main/info scrollbars).
    - region: bounding box of dropdown
    - scroll_anchor_abs: point on dropdown scrollbar or inside options list
    - desired_value: if given, will try to select it while scrolling
    """
    last_snapshot = ""
    stable_count = 0
    scrolled_once = False

    for attempt in range(DROPDOWN_MAX_SCROLLS):
        lines = ocr_region_lines_dropdown(region, debug_name=f"dropdown_scroll_a{attempt}")
        visible_texts = [ln['text'].strip().lower() for ln in lines if ln['text'].strip()]

        # If searching for a value
        if desired_value:
            for ln in lines:
                if desired_value.strip().lower() in ln['text'].strip().lower():
                    click_x = region[0] + max(5, ln.get('left', 10))
                    click_y = region[1] + int(ln['top'] + ln['height'] / 2)
                    pyautogui.moveTo(click_x, click_y)
                    pyautogui.click()
                    speak(f"Selected {desired_value}")
                    return True

        # detect if dropdown stopped changing
        joined = " ".join(visible_texts)
        if scrolled_once and joined == last_snapshot:
            stable_count += 1
            if stable_count >= 2:
                if desired_value:
                    speak(f"Reached end of dropdown. '{desired_value}' not found.")
                    return False
                else:
                    speak("Reached end of dropdown.")
                    return True
        else:
            stable_count = 0
            last_snapshot = joined

        # real scroll (mouse wheel style)
        pyautogui.moveTo(scroll_anchor_abs[0], scroll_anchor_abs[1])
        pyautogui.scroll(DROPDOWN_SCROLL_STEP)
        time.sleep(SCROLL_SLEEP)
        scrolled_once = True

    speak("Max scrolls reached in dropdown.")
    return False
'''
def scroll_info_panel_to_top(mem, steps=35):
    if "info_panel_region" not in mem or "info" not in mem.get("scrollbars", {}):
        return
    anchor = tuple(mem["scrollbars"]["info"])
    for _ in range(steps):
        check_pause()
        scroll_at(anchor, +6)   # + = scroll up (based on your usage of - for down)
        safe_sleep(0.03)
'''



# ---------------- TTS system with selective mute ----------------
SPEAK_ENABLED = True  # normal speaking (Learning Mode)
SYSTEM_SPEAK_ALWAYS = True  # system-level messages (Pause/Resume always spoken)
# =========================
# TTS ENGINE (pyttsx3)
# =========================

class TTSEngine:
    def __init__(self, rate=175, volume=1.0):
        self.rate = rate
        self.volume = volume
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        # FIX: pyttsx3 MUST be initialized INSIDE the background thread on Windows.
        # Otherwise, the Windows COM object will silently crash.
        try:
            self.engine = pyttsx3.init(driverName="sapi5")
            self.engine.setProperty("rate", self.rate)
            self.engine.setProperty("volume", self.volume)
        except Exception as e:
            print(f"[TTS INIT ERROR] {e}")
            return

        while True:
            text = self.queue.get()
            if text is None:
                break
            try:
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception as e:
                print(f"[TTS ERROR] {e}")

    def speak(self, text):
        if text:
            self.queue.put(str(text))

# 🔧 Global TTS instance (ONE only)
TTS = TTSEngine(rate=175, volume=1.0)
def speak(text):
    """Normal speaking — muted in Autofill mode."""
    if not SPEAK_ENABLED:
        return
    print("Jarvis:", text)
    TTS.speak(text)


def system_speak(text):
    """Always speaks — Pause/Resume, critical alerts."""
    if not SYSTEM_SPEAK_ALWAYS:
        return
    print("SYSTEM:", text)
    TTS.speak(text)


pyautogui.PAUSE = 0.05
pyautogui.FAILSAFE = True

# OCR/scroll parameters
DROPDOWN_MAX_SCROLLS = 30
DROPDOWN_SCROLL_STEP = -15    # negative scrolls down
SCROLL_SLEEP = 0.5
# Dropdown tuning (for fast+precise scrolling)
DROPDOWN_FAST_PULSES = 5        # number of wheel notches for fast jumps
DROPDOWN_PRECISE_PULSES = 1     # step-by-step scroll in precise mode
DROPDOWN_FAST_SLEEP = 0.02       # tiny pause after fast scrolls
DROPDOWN_FAST_ATTEMPTS_MULT = 4  # how many times more fast attempts we allow
# Tuning for alphabet slowdown / reverse tracking
ALPHABET_DOMINANCE = 0.7   # require >=70% of visible items to be previous-letter to trigger slowdown
REVERSE_STEPS = 3          # how many upward steps to reverse-track when slowdown triggers
# --- HEAVY DROPDOWN SCROLL PROFILES (District, Cast, Sub Cast) ---
HEAVY_DROPDOWN_PROFILES = {
    "District": {
        "FAST_PULSES": 5.75,
        "FAST_SLEEP": 0.7,
        "FAST_TICKS": 140,
        "PRECISE_PULSES": 2,
        "PRECISE_SLEEP": 0.8,
        "MAX_TOTAL_TICKS": 1200,
        "OCR_COOLDOWN": 0.00,
        "TOP_EDGE_GUARD": 18,

        # --- NEW: single-jump controls (adjust while testing) ---
        "JUMP_ENABLE": True,
        # --- bucketed single big jump pulses (manual tuning) ---
        "JUMP_30_40_PULSES": 59,
        "JUMP_40_50_PULSES": 79,
        "JUMP_50_60_PULSES": 99,
        "JUMP_60_70_PULSES": 119,
        "JUMP_70_80_PULSES": 139,
        "JUMP_80_90_PULSES": 159,
        "JUMP_GT90_PULSES": 179,   # optional
        "JUMP_SLEEP": 0.8,
        "JUMP_SNAPSHOTS": 1,
        "JUMP_PREV_WATCH": 8,
        "JUMP_NEXT_WATCH": 8,
        "JUMP_USE_REASONING": True,
        "JUMP_REASONING_MIN": 0.88,

        "JUMP_PREWAIT": 0.04,
        "JUMP_EVENT_SLEEP": 0.05,   # increase if still “same place”
        "JUMP_BURST_EVERY": 35,      # every N pulses pause briefly
        "JUMP_BURST_SLEEP": 0.06,
        "JUMP_FINAL_SLEEP": 0.03,
    },

    "Cast": {
        "FAST_PULSES": 7.5,
        "FAST_SLEEP": 0.5,
        "FAST_TICKS": 220,
        "PRECISE_PULSES": 2,
        "PRECISE_SLEEP": 0.8,
        "MAX_TOTAL_TICKS": 2200,
        "OCR_COOLDOWN": 0.00,

        # --- NEW ---
        "JUMP_ENABLE": True,
         # --- bucketed single big jump pulses (manual tuning) ---
        "JUMP_30_40_PULSES": 95,
        "JUMP_40_50_PULSES": 131,
        "JUMP_50_60_PULSES": 160,
        "JUMP_60_70_PULSES": 194,
        "JUMP_70_80_PULSES": 222,
        "JUMP_80_90_PULSES": 258,
        "JUMP_GT90_PULSES": 286,   # optional
        "JUMP_SLEEP": 0.7,
        "JUMP_SNAPSHOTS": 1,
        "JUMP_PREV_WATCH": 10,
        "JUMP_NEXT_WATCH": 10,
        "JUMP_USE_REASONING": True,
        "JUMP_REASONING_MIN": 0.88,

        "JUMP_PREWAIT": 0.04,
        "JUMP_EVENT_SLEEP": 0.1,   # increase if still “same place”
        "JUMP_BURST_EVERY": 35,      # every N pulses pause briefly
        "JUMP_BURST_SLEEP": 0.06,
        "JUMP_FINAL_SLEEP": 0.03,
    },

    "Sub Cast": {
        "FAST_PULSES": 11,
        "FAST_SLEEP": 0.7,
        "FAST_TICKS": 260,
        "PRECISE_PULSES": 1.6,
        "PRECISE_SLEEP": 0.8,
        "MAX_TOTAL_TICKS": 2600,
        "OCR_COOLDOWN": 0.00,

        # --- NEW ---
        "JUMP_ENABLE": True,
        # --- NEW fine buckets (you can tune these manually) ---
        "JUMP_30_40_PULSES": 232,
        "JUMP_40_50_PULSES": 314,
        "JUMP_50_60_PULSES": 393,
        "JUMP_60_70_PULSES": 473,
        "JUMP_70_80_PULSES": 552,
        "JUMP_80_90_PULSES": 632,
        "JUMP_GT90_PULSES": 712,   # optional (only used when target > 90%)
        "JUMP_SLEEP": 0.8,
        "JUMP_SNAPSHOTS": 1,
        "JUMP_PREV_WATCH": 12,
        "JUMP_NEXT_WATCH": 12,
        "JUMP_USE_REASONING": True,
        "JUMP_REASONING_MIN": 0.88,

        "JUMP_PREWAIT": 0.04,
        "JUMP_EVENT_SLEEP": 0.05,   # increase if still “same place”
        "JUMP_BURST_EVERY": 35,      # every N pulses pause briefly
        "JUMP_BURST_SLEEP": 0.06,
        "JUMP_FINAL_SLEEP": 0.03,
    },
}




# canonical fields (kept for mapping)
FIELD_ORDER = [
    "App No", "MBI Code", "Full Name", "Gender", "Date of Birth", "Marital Status",
    "State", "District", "Taluk", "Pincode", "House Type", "RAI Code",
    "Mother Tongue", "Religion", "Cast", "Sub Cast", "Nakshatra", "Rashi",
    "Pada", "PHI Code", "Health Info", "Any Disability", "Diet", "Height",
    "Weight", "FAI Code", "Father Status", "Father Name", "Mother Status",
    "Mother Name", "Sister", "Brother", "Children Boy", "Children Girl",
    "ECI Code", "Education", "Emp Status", "Annual Income"
]

# Which canonical fields should prompt main/info scrollbar capture during learning
MAIN_SCROLL_FIELDS = {"Religion", "Father Name"}   # accept 'Religion' or 'Religious'
INFO_SCROLL_FIELDS = {"Pada", "ECI Code"}

# ---------------- Helpers: OCR preprocessing ----------------
def preprocess_for_ocr(pil_img, scale=2):
    img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2GRAY)
    try:
        proc = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 11, 2)
    except Exception:
        _, proc = cv2.threshold(img, 150, 255, cv2.THRESH_BINARY)
    h, w = proc.shape
    resized = cv2.resize(proc, (w * scale, h * scale), interpolation=cv2.INTER_LINEAR)
    return resized, scale

# At top-level config:
USE_MULTI_PASS_OCR_FOR_DROPDOWNS = False  # set True only if needed


def ocr_region_lines(region_bbox, debug_name=None):
    """Wrapper around the smart OCR reader."""
    from smart_text_reader import smart_ocr_lines, smart_ocr_lines_multi
    try:
        if USE_MULTI_PASS_OCR_FOR_DROPDOWNS:
            # You can also restrict this to special fields if you want
            lines = smart_ocr_lines_multi(region_bbox, debug_name=debug_name, enable_trocr=False)
        else:
            lines = smart_ocr_lines(region_bbox, debug_name=debug_name, enable_trocr=False)
        return lines
    except Exception as e:
        print(f"[OCR ERROR] {e}")
        return []
def ocr_region_lines_education(region_bbox, debug_name=None):
    """
    Education dropdown OCR ONLY (Paddle en_PP-OCRv5_mobile_rec cached).
    No fallback to old OCR.
    """
    try:
        return ocr_education_dropdown_lines(
            region_bbox,
            debug_dir=DEBUG_DIR,
            debug_name=debug_name
        )
    except Exception as e:
        print(f"[EDU OCR ERROR] {e}")
        return []
def ocr_region_lines_dropdown(region_bbox, debug_name=None):
    """
    Generic dropdown OCR ONLY (Paddle en_PP-OCRv5_mobile_rec cached).
    No fallback to old OCR.
    """
    try:
        return ocr_dropdown_lines(
            region_bbox,
            debug_dir=DEBUG_DIR,
            debug_name=debug_name
        )
    except Exception as e:
        print(f"[DROPDOWN OCR ERROR] {e}")
        return []




def extract_kv_from_text(raw_text):
    kv = {}
    for line in raw_text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        left, right = line.split(":", 1)
        key = re.sub(r'[^A-Za-z0-9 ]+', '', left).strip()
        val = right.strip()
        if key:
            kv[key] = val
    return kv

# ---------------- Improved fuzzy map (DOB strict) ----------------
def fuzzy_map_kv(kv, canonical_list):
    """
    Map OCR key->value pairs into canonical fields.
    Special handling for Date of Birth: only map when OCR key contains 'date', 'dob' or 'birth'.
    For other fields use stricter fuzzy cutoff to avoid bad matches.
    """
    mapped = {}
    keys = list(kv.keys())
    for canonical in canonical_list:
        if canonical == "Date of Birth":
            # strict alias detection for DOB
            for k,v in kv.items():
                kl = k.lower()
                if "dob" in kl or "date" in kl or "birth" in kl:
                    mapped[canonical] = v
                    break
            # continue - don't fallback to fuzzy for DOB to avoid incorrect mapping
            continue

        # normal strict fuzzy mapping for other fields
        matches = difflib.get_close_matches(canonical, keys, n=1, cutoff=0.7)
        if matches:
            mapped[canonical] = kv[matches[0]]
    
    return mapped
# ---------------- Field-specific value normalizers (add this block) ----------------
import re

_ANNUAL_INCOME_CANON = set(DROPDOWN_OPTIONS.get("Annual Income", {}).get("options", []))

def _normalize_annual_income(value: str) -> str:
    """
    Clean up noisy OCR for Annual Income so it matches dropdown labels exactly.
    Examples fixed:
      "4 Lakh to 7 Lakh Annually a"  -> "4 Lakh to 7 Lakh Annually"
      "1 Crore & Above annually."    -> "1 Core & Above Annually"
      "dont like to specify"         -> "Dont Like To Specify"
    """
    if not value:
        return value

    s = str(value).strip()

    # common whitespace/punctuation noise at the end (including single trailing letters)
    s = re.sub(r'[\s\.\-_,;:]*[a-zA-Z]?\s*$', lambda m: '' if len(m.group(0).strip()) <= 2 else m.group(0), s)
    s = s.rstrip(". ").strip()

    # normalize inner spaces
    s = re.sub(r'\s+', ' ', s)

    # standardize keywords/variants the OCR might alter
    s = re.sub(r'\bLac(?:h|hs)?\b', 'Lakh', s, flags=re.IGNORECASE)           # Lac/Lachs/Lakhs -> Lakh
    s = re.sub(r'\bLakhs\b', 'Lakh', s, flags=re.IGNORECASE)
    s = re.sub(r'\bAnnually\b', 'Annually', s, flags=re.IGNORECASE)           # case only
    s = re.sub(r'\band\b', '&', s, flags=re.IGNORECASE)                       # "and" -> "&" (dataset uses &)
    s = re.sub(r'\bCrore\b', 'Core', s, flags=re.IGNORECASE)                  # dataset uses "Core"
    s = re.sub(r"\bDon't Like To Specify\b", 'Dont Like To Specify', s, flags=re.IGNORECASE)

    # Ensure common endings are capitalized to match options list
    s = re.sub(r'\bannually\b', 'Annually', s, flags=re.IGNORECASE)
    s = re.sub(r'\bnot applicable\b', 'Not Applicable', s, flags=re.IGNORECASE)

    # If it's one of the named options, return as-is
    if s in _ANNUAL_INCOME_CANON:
        return s

    # Final fallback: fuzzy to the closest official label (strict-ish)
    try:
        import difflib
        hit = difflib.get_close_matches(s, list(_ANNUAL_INCOME_CANON), n=1, cutoff=0.75)
        if hit:
            return hit[0]
    except Exception:
        pass

    return s
# ---------------- Field-specific value normalizers (add this block) ----------------
import re

_ANNUAL_INCOME_CANON = set(DROPDOWN_OPTIONS.get("Annual Income", {}).get("options", []))
def _append_info_panel_raw(*_args, **_kwargs):
    return


def _normalize_annual_income(value: str) -> str:
    """
    Clean up noisy OCR for Annual Income so it matches dropdown labels exactly.
    Examples fixed:
      "4 Lakh to 7 Lakh Annually a"  -> "4 Lakh to 7 Lakh Annually"
      "1 Crore & Above annually."    -> "1 Core & Above Annually"
      "dont like to specify"         -> "Dont Like To Specify"
    """
    if not value:
        return value

    s = str(value).strip()

    # common whitespace/punctuation noise at the end (including single trailing letters)
    s = re.sub(r'[\s\.\-_,;:]*[a-zA-Z]?\s*$', lambda m: '' if len(m.group(0).strip()) <= 2 else m.group(0), s)
    s = s.rstrip(". ").strip()

    # normalize inner spaces
    s = re.sub(r'\s+', ' ', s)

    # standardize keywords/variants the OCR might alter
    s = re.sub(r'\bLac(?:h|hs)?\b', 'Lakh', s, flags=re.IGNORECASE)           # Lac/Lachs/Lakhs -> Lakh
    s = re.sub(r'\bLakhs\b', 'Lakh', s, flags=re.IGNORECASE)
    s = re.sub(r'\bAnnually\b', 'Annually', s, flags=re.IGNORECASE)           # case only
    s = re.sub(r'\band\b', '&', s, flags=re.IGNORECASE)                       # "and" -> "&" (dataset uses &)
    s = re.sub(r'\bCrore\b', 'Core', s, flags=re.IGNORECASE)                  # dataset uses "Core"
    s = re.sub(r"\bDon't Like To Specify\b", 'Dont Like To Specify', s, flags=re.IGNORECASE)

    # Ensure common endings are capitalized to match options list
    s = re.sub(r'\bannually\b', 'Annually', s, flags=re.IGNORECASE)
    s = re.sub(r'\bnot applicable\b', 'Not Applicable', s, flags=re.IGNORECASE)

    # If it's one of the named options, return as-is
    if s in _ANNUAL_INCOME_CANON:
        return s

    # Final fallback: fuzzy to the closest official label (strict-ish)
    try:
        import difflib
        hit = difflib.get_close_matches(s, list(_ANNUAL_INCOME_CANON), n=1, cutoff=0.75)
        if hit:
            return hit[0]
    except Exception:
        pass

    return s


# ---- NEW HELPERS FOR CODE PREFIX + TRAILING DOT FIX ------------------------------

def _normalize_code_prefix(value: str, prefix: str) -> str:
    """
    Fix the first 3 letters + clean the numeric part from OCR noise.
    Example:
      MB12I3S45.  -> MBI123545
      RA|2456B31  -> RAI2456831
      PHl234O987. -> PHI2340987
    """

    if not value:
        return value

    s = str(value).strip().upper()
    s = s.rstrip(" .")  # remove trailing dot

    # Force prefix (first 3 letters)
    rest = s[3:] if len(s) > 3 else ""

    # OCR noise correction table for the numeric part
    ocr_map = str.maketrans({
        "I": "1", "L": "1", "|": "1",
        "O": "0", "Q": "0", "D": "0",
        "S": "5", "$": "5",
        "B": "8",
        "Z": "2",
        "G": "6",
    })

    # Cleanup numeric part
    cleaned_rest = rest.translate(ocr_map)

    # Remove non-digits
    cleaned_rest = "".join(ch for ch in cleaned_rest if ch.isdigit())

    return prefix + cleaned_rest

def _normalize_eci_code(value: str) -> str:
    """
    ECI-specific cleanup:
    - Remove trailing OCR junk letters BEFORE letter->digit translation
    - Then apply normal OCR map to the remaining part.
    This prevents cases like '...S' becoming a fake trailing '5'.
    """
    if not value:
        return value

    s = str(value).strip().upper()
    s = s.rstrip(" .")  # remove trailing dot/space

    # keep whatever comes after 'ECI'
    rest = s[3:] if len(s) > 3 else ""

    # ✅ IMPORTANT: drop trailing letters/symbols FIRST
    rest = re.sub(r'[^0-9A-Z]+$', '', rest)  # strip trailing symbols
    rest = re.sub(r'[A-Z]+$', '', rest)      # strip trailing letters

    # OCR noise correction table (same as _normalize_code_prefix)
    ocr_map = str.maketrans({
        "I": "1", "L": "1", "|": "1",
        "O": "0", "Q": "0", "D": "0",
        "S": "5", "$": "5",
        "B": "8",
        "Z": "2",
        "G": "6",
    })

    cleaned_rest = rest.translate(ocr_map)
    cleaned_rest = "".join(ch for ch in cleaned_rest if ch.isdigit())

    return "ECI" + cleaned_rest


def _strip_trailing_dot(value: str) -> str:
    """
    Remove a single trailing dot from the end of the string, if present.

    "SHASHANK."      -> "SHASHANK"
    "MBI254235."     -> "MBI254235"
    "Mr. SHASHANK"   -> "Mr. SHASHANK"   (internal dots untouched)
    """
    if value is None:
        return value
    s = str(value)
    s = s.rstrip()  # remove trailing spaces
    if s.endswith('.'):
        s = s[:-1].rstrip()
    return s


def _normalize_info_panel_mapping(mapped: dict) -> dict:
    """
    Apply all info-panel value cleanups:
      - Fix MBI/RAI/PHI/FAI prefixes (first 3 chars only)
      - Normalize Annual Income text
      - Remove trailing dots for *all* fields
    """
    if not isinstance(mapped, dict):
        return mapped

    out = dict(mapped)  # shallow copy

    # 1) Fix code prefixes using only the first 3 characters
    code_fields = [
        ("MBI Code", "MBI"),
        ("RAI Code", "RAI"),
        ("PHI Code", "PHI"),
        ("FAI Code", "FAI"),
    ]

    for field_name, prefix in code_fields:
        if field_name in out and out[field_name]:
            out[field_name] = _normalize_code_prefix(out[field_name], prefix)

    # ✅ ECI handled separately (stricter trailing-junk removal)
    if "ECI Code" in out and out["ECI Code"]:
        out["ECI Code"] = _normalize_eci_code(out["ECI Code"])

    # 2) Fix Annual Income (re-use existing normalizer)
    if "Annual Income" in out and out["Annual Income"]:
        out["Annual Income"] = _normalize_annual_income(out["Annual Income"])

    # 3) Strip a trailing dot for *every* field value
    for k, v in list(out.items()):
        if v is not None:
            out[k] = _strip_trailing_dot(v)
    try:
        out = normalize_info_panel_targets(out, only_dropdown_fields=True)
    except Exception as e:
        print("[INFO_NORMALIZER ERROR]", e)

    return out

# ---- ANNUAL INCOME STRICT FIX (isolated) --------------------------------
def fill_annual_income_dropdown_strict(field_meta, field_abs_pos, desired_value) -> bool:
    """
    Dedicated handler for 'Annual Income'.

    Goals:
      - Normalize the target text using _normalize_annual_income
      - Use OCR + reasoning_core.choose_visible_option to pick the correct line
      - Click with top-biased helper so it does NOT land on the row below
      - Fallback scrolls page-by-page (precise pulses) until found
    """
    desired_raw = (desired_value or "").strip()
    if not desired_raw:
        speak("Annual Income: empty target.")
        return False

    # Normalize noisy OCR -> canonical label from dropdown_data
    try:
        want = _normalize_annual_income(desired_raw)
    except Exception:
        want = desired_raw

    if not want:
        speak(f"Annual Income: could not normalize '{desired_raw}'.")
        return False

    # Open the dropdown (single click)
    click_abs(field_abs_pos[0], field_abs_pos[1])
    safe_sleep(0.35)

    # Same fast resolver we use for Pada fix
    region, scroll_anchor_abs = _resolve_dropdown_region_and_anchor_fast(field_meta, field_abs_pos)

    # Try a generous number of pages (Annual Income list isn't huge)
    for attempt in range(DROPDOWN_MAX_SCROLLS * 3):
        check_pause()
        lines = ocr_region_lines_dropdown(region, debug_name=f"AnnualIncome_FIX_{attempt}")

        if not lines:
            # If OCR is blank, just scroll and try again
            hardware_scroll_at(scroll_anchor_abs, steps=-1, pulses=DROPDOWN_PRECISE_PULSES, fast=False)
            safe_sleep(0.15)
            continue

        candidate = None

        # 1) Strict exact match against normalized 'want'
        for ln in lines:
            txt = (ln.get("text") or "").strip()
            if not txt:
                continue
            if txt.lower() == want.lower():
                candidate = ln
                break

        # 2) If no exact hit, let the reasoning core pick best visible line
        if candidate is None:
            try:
                reason = choose_visible_option("Annual Income", want, lines)
            except Exception:
                reason = None

            if reason and reason.get("status") == "ok" and reason.get("line_dict"):
                candidate = reason["line_dict"]

        # 3) If we have a candidate, micro-verify & click using on-screen text
        if candidate is not None:
            raw_screen = (candidate.get("text") or "").strip()
            # Micro verify uses raw_screen so it aligns with OCR exactly
            if _verified_click_option_annual(region, candidate, raw_screen):
                speak(f"Annual Income: Selected {raw_screen}")
                return True

        # 4) Not found on this page -> small precise scroll down and retry
        hardware_scroll_at(scroll_anchor_abs, steps=-1, pulses=DROPDOWN_PRECISE_PULSES, fast=False)
        safe_sleep(0.15)

    speak(f"Annual Income: could not find '{want}' after scrolling.")
    return False

# ---------------- Memory helpers ----------------
def save_memory(mem):
    with open(BOT_MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=2)
    speak("Saved memory to bot_memory.json")

def load_memory():
    if not os.path.exists(BOT_MEMORY_FILE):
        return None
    with open(BOT_MEMORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# ---------------- Low-level actions ----------------
def clear_field_by_backspace(n=40):
    pyautogui.press('backspace', presses=n, interval=0.01)

def click_and_type_abs(x, y, text):
    pyautogui.click(x, y)
    safe_sleep(0.05)

    # Clear field without using Ctrl
    clear_field_by_backspace(40)
    pyautogui.typewrite(str(text), interval=0.02)
    time.sleep(0.06)
    speak(f"Typed {text}")

def click_abs(x, y):
    pyautogui.click(x, y)
    safe_sleep(0.05)
# ---------- VERIFIED, PRECISE OPTION CLICK (stabilize -> verify -> smooth click) ----------
def _clamp(v, a, b):
    return max(a, min(b, v))

def _safe_center(x, y, w, h, pad=4):
    """
    Choose a point safely inside the row (avoid touching top/bottom edges or scrollbars).

    NOTE:
    - We used to bias vertically at 0.55*h (slightly downwards).
    - On some dropdowns with tight row hitboxes (Rashi, Annual Income, etc.)
      that was overshooting into the next row.
    - Now we bias a bit ABOVE the middle (~0.35*h) to stay firmly inside
      the correct row.
    """
    cx = x + max(pad, min(w - pad, int(w * 0.25)))
    # 0.35 instead of 0.55 to avoid overshooting into the row below
    cy = y + max(pad, min(h - pad, int(h * 0.35)))
    return cx, cy


def _micro_verify_text(region_abs, box_local, required_text, tol_casefold=True):
    """
    Pre-click micro verification:
    - OCR a tiny patch around the target line box INSIDE the dropdown region.
    - Confirm the exact required text is present in that patch.
    This is not a post-click recheck—it happens BEFORE the click.
    """
    rx1, ry1, rx2, ry2 = region_abs
    lx, ly, lw, lh = box_local

    # tiny expansion for OCR stability
    ex = max(0, lx - 2); ey = max(0, ly - 2)
    ew = min(lw + 4, (rx2 - rx1) - ex)
    eh = min(lh + 4, (ry2 - ry1) - ey)
    patch = (rx1 + ex, ry1 + ey, rx1 + ex + ew, ry1 + ey + eh)

    lines = ocr_region_lines_dropdown(patch, debug_name=None)
    want = (required_text or "").strip()
    if not want:
        return False
    if tol_casefold:
        w = want.casefold()
        return any((ln.get('text','').strip().casefold() == w) for ln in lines)
    return any((ln.get('text','').strip() == want) for ln in lines)

def verified_click_option(region_abs, line_dict, required_text, move_duration=0.12):
    """
    Final, single, precise click with pre-click micro verification.
    - Clamps local box to region bounds
    - Picks a safe interior click point
    - Smooth move + one clean click (mouseDown/Up)
    Returns True if clicked, False if verification failed (no click).
    """
    rx1, ry1, rx2, ry2 = region_abs
    lx = int(line_dict.get('left', 0))
    ly = int(line_dict.get('top',  0))
    lw = max(1, int(line_dict.get('width',  1)))
    lh = max(1, int(line_dict.get('height', 1)))

    # clamp local box to be fully inside region
    lx = _clamp(lx, 0, (rx2 - rx1) - lw)
    ly = _clamp(ly, 0, (ry2 - ry1) - lh)

    # verify the text exists exactly inside this micro-patch
    if not _micro_verify_text(region_abs, (lx, ly, lw, lh), required_text):
        return False

    # safe interior click point
    cx_local, cy_local = _safe_center(lx, ly, lw, lh, pad=4)
    cx = _clamp(rx1 + cx_local, rx1 + 2, rx2 - 2)
    cy = _clamp(ry1 + cy_local, ry1 + 2, ry2 - 2)

    # smooth, single click
    pyautogui.moveTo(cx, cy, duration=move_duration)
    pyautogui.mouseDown(); time.sleep(0.02); pyautogui.mouseUp()
    return True
def reasoning_click_option(region_abs, reason, move_duration=0.12):
    """
    Use dropdown_reasoner result to actually click the chosen line.

    Priority:
      1) Micro-verify using the *visible* text from reasoning (what OCR saw on screen).
      2) If that fails, perform a single safe click inside that row anyway.

    This guarantees that when reasoning_core says "status == ok"
    we actually click that row.
    """
    if not reason or reason.get("status") != "ok":
        return False

    line_dict = reason.get("line_dict")
    if not line_dict:
        return False

    # Prefer the text that was actually on screen when reasoning ran
    required_text = (reason.get("visible_text") or line_dict.get("text") or "").strip()

    # 1) Try normal verified click using the visible text
    if required_text:
        if verified_click_option(region_abs, line_dict, required_text, move_duration=move_duration):
            return True

    # 2) Fallback: blind but safe single click inside the same row
    rx1, ry1, rx2, ry2 = region_abs
    lx = int(line_dict.get('left', 0))
    ly = int(line_dict.get('top', 0))
    lw = max(1, int(line_dict.get('width', 1)))
    lh = max(1, int(line_dict.get('height', 1)))

    lx = _clamp(lx, 0, (rx2 - rx1) - lw)
    ly = _clamp(ly, 0, (ry2 - ry1) - lh)

    cx_local, cy_local = _safe_center(lx, ly, lw, lh, pad=4)
    cx = _clamp(rx1 + cx_local, rx1 + 2, rx2 - 2)
    cy = _clamp(ry1 + cy_local, ry1 + 2, ry2 - 2)

    pyautogui.moveTo(cx, cy, duration=move_duration)
    pyautogui.mouseDown(); time.sleep(0.02); pyautogui.mouseUp()
    return True
def wait_for_button_and_click(label, region, timeout=30, poll_interval=0.6,
                              debug_prefix="flow", click_pos=None):
    target_norm = rc_normalize_text(label)
    target_tokens = target_norm.split()
    remaining = float(timeout)

    best_line = None
    best_score = 0.0

    while remaining > 0:
        check_pause()
        t_loop = time.time()

        lines = ocr_region_lines(region, debug_name=f"{debug_prefix}_{int(time.time())}")

        if lines and debug_prefix in ("take_screenshot", "load_another_form"):
            norm_texts = [rc_normalize_text((ln.get("text") or "")) for ln in lines if ln.get("text")]
            print(f"[FLOW DEBUG] OCR lines for {debug_prefix}: {norm_texts}")

        for ln in lines:
            txt = (ln.get("text") or "").strip()
            if not txt:
                continue

            norm = rc_normalize_text(txt)
            if not norm:
                continue

            tokens = norm.split()
            if not tokens:
                continue

            overlap = 0.0
            if target_tokens:
                overlap = len(set(target_tokens) & set(tokens)) / float(len(target_tokens))

            seq_score = difflib.SequenceMatcher(None, target_norm, norm).ratio()
            score = max(overlap, seq_score)

            if score > best_score:
                best_score = score
                best_line = ln

        # count only active time
        remaining -= max(0.0, time.time() - t_loop)

        if best_line is not None and best_score >= 0.55:
            if click_pos:
                cx, cy = click_pos
                pyautogui.moveTo(cx, cy, duration=0.12)
                pyautogui.click()
            else:
                if not verified_click_option(region, best_line, label):
                    rx1, ry1, rx2, ry2 = region
                    lx = int(best_line.get("left", 0))
                    ly = int(best_line.get("top", 0))
                    w = max(1, int(best_line.get("width", 1)))
                    h = max(1, int(best_line.get("height", 1)))
                    cx = rx1 + lx + w // 2
                    cy = ry1 + ly + h // 2
                    pyautogui.moveTo(cx, cy, duration=0.12)
                    pyautogui.click()

            print(f"[FLOW] Detected and clicked '{label}' with score {best_score:.2f}")
            return True

        step = poll_interval if remaining > poll_interval else remaining
        safe_sleep(step)
        remaining -= step

    print(f"[FLOW] Timeout waiting for '{label}' in region {region}. Best score={best_score:.2f}")
    return False


def smart_error_recovery(target_button_text, wait_region):
    """
    Intelligent recovery that looks for TEXT and MOTION to decide whether to click 
    'Start MPF' (Blank Page) or 'Internet Error OK' (Stuck Page).
    """
    print("\n[RECOVERY] Initiating Advanced Smart Vision Recovery (Text + Motion)...")
    
    # ⚠️ IMPORTANT: REPLACE THESE WITH YOUR ACTUAL GLOBAL VARIABLES!
    # I don't know what you named them, but you need the variables where you saved your F6 coords.
    global is_paused, start_mpf_x, start_mpf_y, error_ok_x, error_ok_y 

    recovery_start_time = time.time()
    max_recovery_time = 7 * 60  # 7 minutes

    while (time.time() - recovery_start_time) < max_recovery_time:
        
        # 1. Check if you manually pressed F9 to pause (Update variable name if needed)
        while is_paused:
            time.sleep(1)
            
        print("[RECOVERY] Scanning screen for Text and Motion...")
        
        # 2. Check for Motion (Loading bar)
        is_moving = detect_screen_movement()
        
        # 3. Read the screen safely using raw PyAutoGUI and your imported OCR
        screen_img = cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)
        ocr_engine = _get_ocr("fast") 
        ocr_results = ocr_engine.ocr(screen_img)
        
        # Safely extract all the text strings from PaddleOCR's complex data output
        texts = []
        if ocr_results and ocr_results[0]:
            for line in ocr_results[0]:
                texts.append(line[1][0]) # Grabs just the text string
        
        # 4. Did the target button finally load? (Pure Python lowercase check)
        for text in texts:
            if target_button_text.lower() in text.lower():
                print(f"[RECOVERY] SUCCESS! Target button '{target_button_text}' finally loaded.")
                return True

        # 5. The Ultimate Decision Logic
        text_count = len(texts)
        
        if text_count < 2 and not is_moving:
            # BLANK PAGE: No text AND no moving loading bar
            print(f"[RECOVERY] Status: BLANK PAGE (Texts: {text_count}, Motion: False). Clicking 'Start MPF'...")
            
            # ⚠️ CHANGE THESE TO YOUR ACTUAL START MPF COORDINATE VARIABLES
            pyautogui.click(start_mpf_x, start_mpf_y) 
            
        else:
            # INTERNET ERROR: Text is visible OR the loading bar is moving
            motion_status = "True" if is_moving else "False"
            print(f"[RECOVERY] Status: STUCK/INTERNET ERROR (Texts: {text_count}, Motion: {motion_status}). Pressing 'Enter'...")
            
            # Pressing enter instead of clicking coordinates
            pyautogui.press('enter')

        time.sleep(3)

    print("[RECOVERY] FATAL: 7-minute recovery timeout reached. Aborting.")
    return False


def run_upload_and_next_form(mem):
    upload_pos = mem.get("upload_button_pos")
    ok_pos = mem.get("upload_ok_button_pos")
    flow_region = mem.get("upload_flow_region")

    ts_pos = mem.get("take_screenshot_button_pos")
    la_pos = mem.get("load_another_form_button_pos")
    start_mpf_pos = mem.get("start_mpf_button_pos")  # NEW

    if not (upload_pos and ok_pos and flow_region):
        speak("Upload flow not configured in memory. Skipping upload automation.")
        return False

    upload_pos = tuple(upload_pos)
    ok_pos = tuple(ok_pos)
    flow_region = tuple(flow_region)
    ts_pos = tuple(ts_pos) if ts_pos else None
    la_pos = tuple(la_pos) if la_pos else None

    def click_ie_ok():
        print("[RECOVERY] Pressing Enter to clear Internet Error...")
        pyautogui.press('enter')
        safe_sleep(1.0)

    def click_start_mpf():
        if start_mpf_pos:
            print("[RECOVERY] Blank page detected. Clicking Start MPF button...")
            click_abs(start_mpf_pos[0], start_mpf_pos[1])
            safe_sleep(2.0)

    state = "UPLOAD"
    deadline = time.time() + 40.0
    error_alerted = False
    ie_recovery_attempted = False  # Tracks if we are in Stage 2 (Blank Page)

    while True:
        check_pause()

        if state == "UPLOAD":
            ie_recovery_attempted = False  # Reset on successful state change
            print("[FLOW] Clicking Upload Details button…")
            click_abs(upload_pos[0], upload_pos[1])
            
            deadline_ok = time.time() + 2.0
            while time.time() < deadline_ok:
                check_pause()
                click_abs(ok_pos[0], ok_pos[1])
                break

            print("[FLOW] Waiting for 'Take Screenshot' button…")
            state = "WAIT_SCREENSHOT"
            deadline = time.time() + 40.0

        elif state == "WAIT_SCREENSHOT":
            if wait_for_button_and_click("Take Screenshot", flow_region, timeout=1.0, poll_interval=0.7, click_pos=ts_pos):
                if error_alerted:
                    _telegram_notify_recovery("Take Screenshot button found. Termination cancelled.")
                    error_alerted = False
                ie_recovery_attempted = False
                print("[FLOW] Take Screenshot clicked.")
                state = "WAIT_LOAD_ANOTHER"
                deadline = time.time() + 40.0
                print("[FLOW] Waiting for 'Load Another Form' button…")
                continue

            if time.time() > deadline:
                if not error_alerted:
                    _telegram_notify_no_forms("Timeout waiting for Take Screenshot (Internet Error Trigger)", force=True)
                    error_alerted = True
                
                # STAGE 2: If we already pressed Enter and waited 40s, it's a blank page
                if ie_recovery_attempted:
                    click_start_mpf()
                    deadline = time.time() + 40.0  # Reset timer to wait for UI to load
                    ie_recovery_attempted = False  # Reset so it alternates if it fails again
                else:
                    # STAGE 1: Standard Internet Error (Press Enter)
                    click_ie_ok()
                    ie_recovery_attempted = True
                    safe_sleep(2.0)

                    lines = ocr_region_lines(flow_region, debug_name="check_loading")
                    visible_text = " ".join([ln.get("text", "") for ln in lines]).strip()

                    if visible_text:
                        print("[RECOVERY] Text detected instead of loading bar. Retrying Upload.")
                        state = "UPLOAD"
                    else:
                        print("[RECOVERY] No text detected, continuing to wait for Take Screenshot.")
                        deadline = time.time() + 40.0

        elif state == "WAIT_LOAD_ANOTHER":
            if wait_for_button_and_click("Load Another Form", flow_region, timeout=1.0, poll_interval=0.7, click_pos=la_pos):
                if error_alerted:
                    _telegram_notify_recovery("Load Another Form found. Termination cancelled.")
                    error_alerted = False
                ie_recovery_attempted = False
                print("[FLOW] Load Another Form clicked, expecting a new form.")
                safe_sleep(2.5)
                return True

            if time.time() > deadline:
                if not error_alerted:
                    _telegram_notify_no_forms("Timeout waiting for Load Another Form (Internet Error Trigger)", force=True)
                    error_alerted = True
                
                # STAGE 2: Blank Page Recovery
                if ie_recovery_attempted:
                    click_start_mpf()
                    deadline = time.time() + 40.0
                    ie_recovery_attempted = False
                else:
                    # STAGE 1: Internet Error Recovery
                    click_ie_ok()
                    ie_recovery_attempted = True
                    safe_sleep(2.0)

                    if wait_for_button_and_click("Load Another Form", flow_region, timeout=4.0, poll_interval=0.7, click_pos=la_pos):
                        print("[RECOVERY] Load Another Form found after pressing Enter. Clicked.")
                        if error_alerted:
                            _telegram_notify_recovery("Load Another Form found after popup fix. Termination cancelled.")
                            error_alerted = False
                        safe_sleep(2.5)
                        return True
                    else:
                        print("[RECOVERY] Load Another Form still not found. Looping back to wait.")
                        deadline = time.time() + 40.0

# ---------- SPECIAL CLICK HELPER FOR ANNUAL INCOME (top-biased) ----------
def _safe_center_top(x, y, w, h, pad=4):
    """
    Variant of _safe_center but clicks slightly HIGHER inside the row.
    This is only used for 'Annual Income' where clicking with 0.55*h
    tends to land on the next row.
    """
    cx = x + max(pad, min(w - pad, int(w * 0.25)))
    # 0.30 instead of 0.55 -> bias higher inside the box
    cy = y + max(pad, min(h - pad, int(h * 0.30)))
    return cx, cy


def _verified_click_option_annual(region_abs, line_dict, required_text, move_duration=0.12):
    """
    Annual Income–specific verified click:
      - Same micro-verification logic as verified_click_option
      - But uses _safe_center_top() so we don't overshoot into the row below.
    """
    rx1, ry1, rx2, ry2 = region_abs
    lx = int(line_dict.get('left', 0))
    ly = int(line_dict.get('top',  0))
    lw = max(1, int(line_dict.get('width',  1)))
    lh = max(1, int(line_dict.get('height', 1)))

    # clamp local box to be fully inside region
    lx = _clamp(lx, 0, (rx2 - rx1) - lw)
    ly = _clamp(ly, 0, (ry2 - ry1) - lh)

    # pre-click micro OCR check using the *on-screen* text
    if not _micro_verify_text(region_abs, (lx, ly, lw, lh), required_text):
        return False

    # safe, slightly upper interior click point
    cx_local, cy_local = _safe_center_top(lx, ly, lw, lh, pad=4)
    cx = _clamp(rx1 + cx_local, rx1 + 2, rx2 - 2)
    cy = _clamp(ry1 + cy_local, ry1 + 2, ry2 - 2)

    pyautogui.moveTo(cx, cy, duration=move_duration)
    pyautogui.mouseDown(); time.sleep(0.02); pyautogui.mouseUp()
    return True


def scroll_at(point, steps):
    pyautogui.moveTo(point[0], point[1])
    pyautogui.scroll(steps)
    time.sleep(SCROLL_SLEEP)
# Detect platform
_IS_WINDOWS = platform.system().lower().startswith("win")

# low-level hardware-like wheel scroller (Windows uses mouse_event for real wheel pulses)
import platform
_IS_WINDOWS = platform.system().lower().startswith("win")

def hardware_scroll_at(point, steps, pulses=3, fast=False):
    """
    Send hardware-like wheel events at `point`.
    - steps sign defines direction (positive = up, negative = down)
    - pulses = number of 120-unit pulses to send
    - fast = True -> shorter sleeps between pulses and smaller final sleep
    """
    try:
        # move cursor into position first
        pyautogui.moveTo(point[0], point[1])
    except Exception:
        if _IS_WINDOWS:
            try:
                ctypes.windll.user32.SetCursorPos(int(point[0]), int(point[1]))
            except Exception:
                pass
    # small pre-wait so UI binds wheel to this control
    time.sleep(0.01 if fast else 0.05)

    # Determine direction
    sign = 1 if steps > 0 else -1

    if _IS_WINDOWS:
        MOUSEEVENTF_WHEEL = 0x0800
        # ensure pulses is int >=1
        pulses = max(1, int(abs(pulses)))
        for i in range(pulses):
            try:
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, sign * 120, 0)
            except Exception:
                # fallback to pyautogui if lower-level fails
                try:
                    pyautogui.scroll(sign * 120)
                except Exception:
                    pass
            # tiny pause between pulses
            time.sleep(0.008 if fast else 0.03)
    else:
        # non-windows fallback: use pyautogui.scroll aggregated
        try:
            pyautogui.scroll(int(sign * 120 * pulses))
        except Exception:
            pyautogui.scroll(int(steps * pulses))

    # final sleep after the pulses
    time.sleep(DROPDOWN_FAST_SLEEP if fast else SCROLL_SLEEP)



def scroll_dropdown_to_end(region, scroll_anchor_abs, desired_value=None):
    """
    Scroll a dropdown until end (isolated from main/info scrollbars).
    - region: (x1,y1,x2,y2) bounding box of the dropdown visible area
    - scroll_anchor_abs: absolute (x,y) point to place the cursor for pulses
    - desired_value: optional target string to find & click while scrolling
    Returns True if desired_value was found and selected (or no desired_value and end reached),
    Returns False if desired_value not found after reaching end.
    """
    last_snapshot = None
    stable_count = 0
    scrolled_once = False

    for attempt in range(DROPDOWN_MAX_SCROLLS):
        lines = ocr_region_lines_dropdown(region, debug_name=f"dropdown_scroll_a{attempt}")
        visible_texts = [ln['text'].strip().lower() for ln in lines if ln.get('text') and ln['text'].strip()]

        # If looking for a specific option, try selecting it on this page
        if desired_value:
            target = desired_value.strip().lower()
            for ln in lines:
                if target in ln['text'].strip().lower():
                    click_x = region[0] + max(5, ln.get('left', 10))
                    click_y = region[1] + int(ln.get('top', 0) + ln.get('height', 10) / 2)
                    pyautogui.moveTo(click_x, click_y)
                    pyautogui.click()
                    speak(f"Selected {desired_value}")
                    return True

        joined = " ".join(visible_texts).strip()

        # Don't judge end until we've actually scrolled at least once.
        if scrolled_once and last_snapshot is not None and joined == last_snapshot:
            stable_count += 1
            if stable_count >= 2:
                # End detected
                if desired_value:
                    speak(f"Reached end of dropdown. '{desired_value}' not found.")
                    return False
                else:
                    speak("Reached end of dropdown.")
                    return True
        else:
            stable_count = 0
            last_snapshot = joined

        # Perform a real wheel scroll at the dropdown anchor
        # Use a few pulses to make sure the UI responds
        hardware_scroll_at(scroll_anchor_abs, DROPDOWN_SCROLL_STEP, pulses=10)
        scrolled_once = True

    speak("Max dropdown scroll attempts reached.")
    return False
def search_with_context(data_list, target, context=5):
    """Search for a target in the list and return 5 previous and next elements."""
    if target not in data_list:
        return None, [], []
    index = data_list.index(target)
    prev_elements = data_list[max(0, index - context): index]
    next_elements = data_list[index + 1: index + 1 + context]
    return target, prev_elements, next_elements
def _resolve_dropdown_region_and_anchor(field_meta, field_abs_pos):
    """Return (region_box, scroll_anchor_abs) for an MPF dropdown field."""
    rel = field_meta['dropdown_region_rel']
    region = (
        int(field_abs_pos[0] + rel[0]),
        int(field_abs_pos[1] + rel[1]),
        int(field_abs_pos[0] + rel[2]),
        int(field_abs_pos[1] + rel[3])
    )
    if field_meta.get('scroll_anchor_rel'):
        scroll_anchor_abs = (
            int(field_abs_pos[0] + field_meta['scroll_anchor_rel'][0]),
            int(field_abs_pos[1] + field_meta['scroll_anchor_rel'][1])
        )
    else:
        scroll_anchor_abs = ((region[0] + region[2]) // 2, (region[1] + region[3]) // 2)
    return region, scroll_anchor_abs
def _district_first_precise_probe(region, scroll_anchor_abs, desired_value,
                                  neighbors_prev, neighbors_next, profile):
    """
    District-only pre-phase:
    - Do 2 precise (slow) scrolls first.
    - If reasoning/exact match hits -> done.
    - If neighbor blocks appear -> jump directly to precise phase.
    - If nothing triggers after 2 tries -> tell caller to go FAST.
    Returns:
        ("done", True/False) or ("precise", forward_bool) or ("fast", None)
    """
    target_value = (desired_value or "").strip()
    target_norm = target_value.lower()

    for probe in range(2):
        check_pause()
        lines = ocr_region_lines_dropdown(region, debug_name=f"District_PROBE_{probe}")

        # 1) reasoning first (same style as heavy precise)
        if should_activate_reasoning("District", phase="precise"):
            reason = choose_visible_option("District", target_value, lines)
            if reasoning_click_option(region, reason):
                speak(f"District: Selected {target_value} (probe reasoning).")
                return ("done", True)

        # 2) exact fallback
        for ln in lines:
            txt = (ln.get("text") or "").strip()
            if txt.lower() == target_norm:
                if verified_click_option(region, ln, target_value):
                    speak(f"District: Selected {target_value} (probe exact).")
                    return ("done", True)

        # 3) neighbor triggers -> go precise immediately
        visible_texts = [ln.get("text","").strip().lower() for ln in lines if ln.get("text","").strip()]
        vis_set = set(visible_texts)

        if any(p in vis_set for p in neighbors_prev):
            speak("District: prev-neighbor seen in probe -> go precise forward.")
            return ("precise", True)

        if any(n in vis_set for n in neighbors_next):
            speak("District: next-neighbor seen in probe -> go precise reverse.")
            return ("precise", False)

        # 4) one slow precise scroll (down)
        hardware_scroll_at(
            scroll_anchor_abs,
            steps=-1,
            pulses=profile["PRECISE_PULSES"],
            fast=False
        )
        time.sleep(profile["PRECISE_SLEEP"])

    # after 2 precise probes, no trigger -> use fast phase
    return ("fast", None)


def _heavy_dropdown_fast_phase(field_name, region, scroll_anchor_abs, desired_value,
                               neighbors_prev, neighbors_next, profile):
    """
    FAST PHASE:
    - Do aggressive wheel pulses to skim the list.
    - At each page, OCR and try:
        1) exact match
        2) detect neighbor blocks (prev / next) to decide where to switch to precise phase
    Returns:
        ("done", True/False)  -> selected / not found
        ("precise", direction)-> go to precise phase; direction=True means forward (down), False up
    """
    fast_ticks = 0
    while fast_ticks < profile["FAST_TICKS"]:
        check_pause()
        # OCR visible page
        lines = ocr_region_lines_dropdown(region, debug_name=f"{field_name}_FAST_{fast_ticks}")
        visible_texts = [ln['text'].strip() for ln in lines if ln.get('text') and ln['text'].strip()]
        vis_lower = [t.lower() for t in visible_texts]

        # Exact match on page
        for ln in lines:
            txt = (ln.get('text') or "").strip()
            if txt.lower() == desired_value.lower():
                if verified_click_option(region, ln, desired_value):
                    speak(f"{field_name}: Selected {desired_value} (fast phase).")
                    return ("done", True)


        # Check neighbor blocks to decide direction for precise
        hit_prev = any(x in set(vis_lower) for x in neighbors_prev)
        hit_next = any(x in set(vis_lower) for x in neighbors_next)
        if hit_prev:
            # We have scrolled past the block just above target; go forward (down) precisely
            return ("precise", True)
        if hit_next:
            # We are already beyond target; go reverse (up) precisely
            return ("precise", False)
        

        # Wheel skim (down)
        hardware_scroll_at(scroll_anchor_abs, steps=-1, pulses=profile["FAST_PULSES"], fast=True)
        time.sleep(profile["FAST_SLEEP"])
        if profile["OCR_COOLDOWN"] > 0:
            time.sleep(profile["OCR_COOLDOWN"])
        fast_ticks += 1

    # Fast phase exhausted, fall back to precise downwards first
    return ("precise", True)


def _heavy_dropdown_precise_phase(field_name, region, scroll_anchor_abs, desired_value,
                                  forward, profile):
    """
    PRECISE PHASE (with reasoning):
    - Small, step-by-step pulses in chosen direction until the target is found.
    - For heavy, scrollable lists like District / Cast / Sub Cast, the reasoning
      module evaluates every visible page and chooses the best noisy OCR line.
    """
    ticks = 0
    direction = -1 if forward else +1
    target_value = (desired_value or "").strip()
    target_norm = target_value.lower()

    while ticks < profile["MAX_TOTAL_TICKS"]:
        check_pause()
        lines = ocr_region_lines_dropdown(region, debug_name=f"{field_name}_PRECISE_{ticks}")

        # --- REASONING: use the brain first for heavy dropdowns ---
        if should_activate_reasoning(field_name, phase="precise"):
            reason = choose_visible_option(field_name, target_value, lines)
            if reasoning_click_option(region, reason):
                speak(f"{field_name}: Selected {target_value} (precise reasoning).")
                return True

        # ---------------------------------------------------------

        # Fallback 1: simple normalized match (old behavior, backup only)
        for ln in lines:
            txt = (ln.get("text") or "").strip()
            if txt.lower() == target_norm:
                if verified_click_option(region, ln, target_value):
                    speak(f"{field_name}: Selected {target_value} (precise fallback).")
                    return True

        # One precise scroll step in chosen direction
        hardware_scroll_at(
            scroll_anchor_abs,
            steps=direction,
            pulses=profile["PRECISE_PULSES"],
            fast=False,
        )
        time.sleep(profile["PRECISE_SLEEP"])
        ticks += 1

    speak(f"{field_name}: precise phase exhausted without finding '{target_value}'.")
    return False

def _heavy_dropdown_precise_phase_with_reverse(field_name, region, scroll_anchor_abs,
                                               desired_value, forward,
                                               neighbors_prev, neighbors_next, profile):
    """
    Heavy precise with reverse tracking.
    Delegates to reverse_precise_tracker but keeps heavy tuning.
    """
    from reverse_precise_tracker import precise_dropdown_scan_with_reverse

    return precise_dropdown_scan_with_reverse(
        field_name=field_name,
        region=region,
        scroll_anchor_abs=scroll_anchor_abs,
        target=desired_value,
        prev_neighbors=neighbors_prev,
        next_neighbors=neighbors_next,
        forward=forward,
        max_attempts=profile["MAX_TOTAL_TICKS"],
        vanish_threshold=3
    )


def fill_heavy_dropdown(field_name, field_meta, field_abs_pos, desired_value):
    """
    High-volume dropdown selector for: District, Cast, Sub Cast
    - Uses dataset neighbors to lock onto the target quickly
    - Two phases: fast skim -> precise step
    """
    profile = HEAVY_DROPDOWN_PROFILES.get(field_name)
    if not profile:
        speak(f"{field_name}: no heavy profile configured.")
        return False

    # sanity
    if 'dropdown_region_rel' not in field_meta:
        speak(f"No dropdown region stored for {field_name}.")
        return False
    desired_value = (desired_value or "").strip()
    if not desired_value:
        speak(f"{field_name}: empty target.")
        return False
    if field_name not in DROPDOWN_OPTIONS:
        speak(f"No dataset mapped for {field_name}.")
        return False

    # open dropdown
    click_abs(field_abs_pos[0], field_abs_pos[1])
    safe_sleep(0.4)

    # region/anchor
    region, scroll_anchor_abs = _resolve_dropdown_region_and_anchor(field_meta, field_abs_pos)

    # neighbor context (10 each side)
    options = DROPDOWN_OPTIONS[field_name]["options"]
    target, prev_list, next_list = search_with_context(options, desired_value, context=30)
    if not target:
        speak(f"{field_name}: '{desired_value}' not found in dataset.")
        return False
    neighbors_prev = [p.lower() for p in prev_list]
    neighbors_next = [n.lower() for n in next_list]
    # ---------------- NEW: edge-guard for top/bottom targets ----------------
    try:
        target_index = options.index(target)
    except ValueError:
        target_index = None

    if target_index is not None:
        from heavy_dropdown_guard import heavy_dropdown_edge_plan

        activated, selected, forward = heavy_dropdown_edge_plan(
            field_name=field_name,
            region=region,
            desired_value=desired_value,
            scroll_anchor_abs=scroll_anchor_abs,
            target_index=target_index,
            total_options=len(options),
            profile=profile,
        )

        if activated:
            # if selected already -> done
            if selected:
                return True

            # edge-phase active but not selected on open screen:
            # ✅ SKIP FAST phase
            # ✅ GO PRECISE directly (reasoning auto-runs in precise for scrollables)
            return _heavy_dropdown_precise_phase(
                field_name, region, scroll_anchor_abs, desired_value, forward, profile
            )
            # ---------------- NEW: mid/bottom jump rule (50% / 70%) ----------------
    if target_index is not None:
        from heavy_dropdown_jump import heavy_dropdown_midbottom_jump

        mode, payload = heavy_dropdown_midbottom_jump(
            field_name=field_name,
            region=region,
            desired_value=desired_value,
            scroll_anchor_abs=scroll_anchor_abs,
            target_index=target_index,
            options=options,
            neighbors_prev=neighbors_prev,
            neighbors_next=neighbors_next,
            profile=profile,
        )

        if mode == "done":
            return payload

        if mode == "precise":
            forward = bool(payload)
            return _heavy_dropdown_precise_phase_with_reverse(
                field_name, region, scroll_anchor_abs, desired_value, forward,
                neighbors_prev, neighbors_next, profile
            )

        # mode == "fast" or "none" -> fall through to existing flow



      # District-only: first 2 scrolls are precise probes.
    # Only runs when edge-guard did NOT activate.
    if field_name == "District":
        mode, payload = _district_first_precise_probe(
            region, scroll_anchor_abs, desired_value,
            neighbors_prev, neighbors_next, profile
        )
        if mode == "done":
            return payload
        if mode == "precise":
            forward = bool(payload)
            return _heavy_dropdown_precise_phase_with_reverse(
                field_name, region, scroll_anchor_abs, desired_value, forward,
                neighbors_prev, neighbors_next, profile
            )
        # mode == "fast" -> fall through to normal fast phase

    # Phase A: FAST (unchanged for all fields)
    mode, payload = _heavy_dropdown_fast_phase(
        field_name, region, scroll_anchor_abs, desired_value, neighbors_prev, neighbors_next, profile
    )
    if mode == "done":
        return payload

    # Phase B: PRECISE (unchanged)
    forward = bool(payload)
    return _heavy_dropdown_precise_phase_with_reverse(
        field_name, region, scroll_anchor_abs, desired_value, forward,
        neighbors_prev, neighbors_next, profile
    )
  


SPECIAL_PRECISE_ONLY = {
    "gender", "marital status", "house type", "mother tongue", "religion",
    "nakshatra", "rashi", "pada", "health info", "any disability", "diet",
    "father status", "mother status", "sister", "brother",
    "children boy", "children girl", "emp status", "annual income"
}


def search_with_context(data_list, target, context=15):
    """Search for a target in the list and return 10 previous and next elements."""
    if target not in data_list:
        return None, [], []
    index = data_list.index(target)
    prev_elements = data_list[max(0, index - context): index]
    next_elements = data_list[index + 1: index + 1 + context]
    return target, prev_elements, next_elements


SPECIAL_PRECISE_ONLY = {
    "gender", "marital status", "house type", "mother tongue", "religion",
    "nakshatra", "rashi", "pada", "health info", "any disability", "diet",
    "father status", "mother status", "sister", "brother",
    "children boy", "children girl", "emp status", "annual income"
}
# --- Normalizers for dropdown text (tolerant to spaces around slashes) ---
import re

def _norm_option_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r'\s*/\s*', '/', s)     # "5.08 / 68 in" -> "5.08/68 in"
    s = re.sub(r'\s+', ' ', s)         # collapse multiple spaces
    return s

# --- STABILIZED PICK & CLICK (drop into MPF_BOT_V7.3.py) ---
# ====================== EDUCATION ONLY PATCH ======================
# ====================== EDUCATION ONLY PATCH ======================
def _norm_edu_text(s: str) -> str:
    """
    Education-only normalizer (DOT-PRESERVING).

    Why: Education has real dot-variants that must remain distinct in matching:
      - "PhD" vs "Ph.D"
      - "BVSc" vs "BVSc."
      - "B.Pharma" vs "B.PHARMA."

    So we only normalize whitespace + case.
    """
    if s is None:
        return ""
    t = str(s).strip()
    # Keep punctuation, only normalize spaces and slash spacing
    t = re.sub(r"\s*/\s*", "/", t)
    t = re.sub(r"\s+", " ", t)
    t = t.replace(" ", "")   # remove whitespace entirely for stable match
    return t.casefold()


def education_precise_bidi_scan(field_name, region, scroll_anchor_abs, target):
    """Education-only: ALWAYS try precise mode in both directions."""
    # Down/forward first
    if precise_dropdown_scan(field_name, region, scroll_anchor_abs, target, forward=True):
        return True
    # Then reverse/up
    return precise_dropdown_scan(field_name, region, scroll_anchor_abs, target, forward=False)
# ==================== END EDUCATION ONLY PATCH ====================



def search_with_context_edu(data_list, target, context=15):
    """
    Education-only context search that matches using _norm_edu_text.
    Returns (found_value_from_dataset, prev_list, next_list) like the normal function.
    """
    nt = _norm_edu_text(target)
    idx = None
    for i, opt in enumerate(data_list or []):
        if _norm_edu_text(opt) == nt:
            idx = i
            break
    if idx is None:
        return None, [], []
    found = data_list[idx]
    prev_list = data_list[max(0, idx - context): idx]
    next_list = data_list[idx + 1: idx + 1 + context]
    return found, prev_list, next_list


def _micro_verify_text_edu(region_abs, box_local, required_text):
    """
    Education-only micro verification using Paddle Education OCR.
    (Old micro verify uses old OCR and fails on short abbreviations like AA/AET.)
    """
    rx1, ry1, rx2, ry2 = region_abs
    lx, ly, lw, lh = box_local

    ex = max(0, lx - 2); ey = max(0, ly - 2)
    ew = min(lw + 4, (rx2 - rx1) - ex)
    eh = min(lh + 4, (ry2 - ry1) - ey)
    patch = (rx1 + ex, ry1 + ey, rx1 + ex + ew, ry1 + ey + eh)

    want = (required_text or "").strip()
    if not want:
        return False

    lines = ocr_region_lines_education(patch, debug_name=None)
    w = _norm_edu_text(want)
    return any(_norm_edu_text((ln.get("text") or "").strip()) == w for ln in lines)


def verified_click_option_edu(region_abs, line_dict, required_text, move_duration=0.12):
    """
    Education-only click:
    1) Micro-verify using Paddle Education OCR.
    2) If still fails, do a safe 'blind click' in that row (Education-only fallback).

    IMPORTANT FIX:
    Paddle line boxes for dropdown rows are often VERY wide (union boxes).
    Clicking the center can land near the scrollbar and fail to select.
    So we click LEFT-BIASED (inside the text area).
    """
    rx1, ry1, rx2, ry2 = region_abs
    lx = int(line_dict.get('left', 0))
    ly = int(line_dict.get('top',  0))
    lw = max(1, int(line_dict.get('width',  1)))
    lh = max(1, int(line_dict.get('height', 1)))

    lx = _clamp(lx, 0, (rx2 - rx1) - lw)
    ly = _clamp(ly, 0, (ry2 - ry1) - lh)

    # Click point: LEFT-BIASED (union boxes can be very wide; center can land near scrollbar)
    click_x_local = int(lx + max(12, min(24, lw * 0.15)))
    click_y_local = int(ly + (lh // 2))
    cx = _clamp(rx1 + click_x_local, rx1 + 2, rx2 - 2)
    cy = _clamp(ry1 + click_y_local, ry1 + 2, ry2 - 2)

    # 1) Paddle micro verify (still useful, but click point stays left-biased)
    if _micro_verify_text_edu(region_abs, (lx, ly, lw, lh), required_text):
        pyautogui.moveTo(cx, cy, duration=move_duration)
        pyautogui.mouseDown(); time.sleep(0.02); pyautogui.mouseUp()
        return True

    # 2) fallback: blind click in the same row (left-biased)
    pyautogui.moveTo(cx, cy, duration=move_duration)
    pyautogui.mouseDown(); time.sleep(0.02); pyautogui.mouseUp()
    return True

# ==================== END EDUCATION ONLY PATCH ====================

def _stabilize_exact_match(region, target_text, passes=3, prefer_y=None):
    """
    Take a few OCR snapshots and return ONE stable bbox for an EXACT (normalized) match.
    - region: (x1,y1,x2,y2)
    - target_text: raw desired value; compared via _norm_option_text equality
    - passes: OCR passes to intersect/median for stability
    - prefer_y: absolute Y (px) to bias towards (e.g., sample line y) if several matches
    Returns: dict {left, top, width, height} in absolute screen coords, or {} if none
    """
    tnorm = _norm_option_text(target_text)
    snapshots = []
    for i in range(max(2, passes)):
        lines = ocr_region_lines_dropdown(region, debug_name=f"lock_{tnorm}_{i}")
        hits = []
        for ln in lines:
            if _norm_option_text(ln.get('text','')) == tnorm:
                # map to ABSOLUTE screen coords
                abs_left = region[0] + int(ln.get('left',0))
                abs_top  = region[1] + int(ln.get('top',0))
                hits.append({
                    'left': abs_left,
                    'top': abs_top,
                    'width': int(ln.get('width',0)),
                    'height': int(ln.get('height',0))
                })
        snapshots.append(hits)
        time.sleep(0.03)  # tiny spacing so UI updates settle

    # Keep only boxes that appear in MOST snapshots (by proximity)
    def near(a,b,tol=4):
        return abs(a['left']-b['left'])<=tol and abs(a['top']-b['top'])<=tol

    candidates = []
    all_first = snapshots[0]
    for cand in all_first:
        votes = 1
        for s in snapshots[1:]:
            if any(near(cand, x) for x in s):
                votes += 1
        if votes >= len(snapshots)-0:  # seen in all passes OR all but 0
            candidates.append(cand)

    if not candidates:
        # try union across snapshots if first-pass strict failed
        pool = [x for snap in snapshots for x in snap]
        if not pool:
            return {}
        candidates = pool

    # Choose one: bias to prefer_y (closest row center), else the tallest box
    def score(c):
        cy = c['top'] + c['height']/2
        bias = -abs(cy - prefer_y) if prefer_y is not None else 0
        return (c['height'], bias)  # taller + nearer

    candidates.sort(key=score, reverse=True)
    return candidates[0] if candidates else {}

def _precise_single_click(box):
    """
    Smooth approach from the left, settle, then perform a single, controlled click.
    box: {left, top, width, height} in absolute coords
    """
    if not box: return False
    cx = int(box['left'] + max(12, min(24, box['width'] * 0.15)))  # a bit inside text, away from scrollbar
    cy = int(box['top']  + box['height'] // 2)

    # approach path: left edge -> just-left of target -> target center
    approach_x = max(0, cx - 40)
    pyautogui.moveTo(approach_x, cy, duration=0.08)  # quick approach
    pyautogui.moveTo(cx - 6, cy, duration=0.06)      # edge hover
    time.sleep(0.12)                                  # settle hover
    pyautogui.moveTo(cx, cy, duration=0.04)          # final nudge
    time.sleep(0.08)
    pyautogui.mouseDown(); time.sleep(0.07); pyautogui.mouseUp()
    return True

def _extract_inches(s: str):
    m = re.search(r'(\d+(?:\.\d+)?)\s*in\b', (s or '').lower())
    return float(m.group(1)) if m else None
def _canonicalize_education_target(raw_target: str, options: list):
    """
    Education-only target canonicalizer (DOT-PRESERVING).

    Why: Education contains both dot and non-dot variants as distinct options
    (e.g., "PhD" vs "Ph.D"). We must NOT collapse dots here.

    Returns (canonical_value, tag_or_None)
    """
    raw_target = (raw_target or "").strip()
    if not raw_target:
        return raw_target, None

    # 1) exact case-sensitive
    if raw_target in options:
        return raw_target, "exact"

    # 2) exact casefold (unique only)
    cf = raw_target.casefold()
    hits = [o for o in options if (o or "").strip().casefold() == cf]
    if len(hits) == 1:
        return hits[0], "casefold_exact"

    # 3) dot-preserving fuzzy match on _norm_edu_text
    tnorm = _norm_edu_text(raw_target)
    best_raw, best_ratio = None, 0.0
    for o in options:
        r = SequenceMatcher(None, tnorm, _norm_edu_text(o)).ratio()
        if r > best_ratio:
            best_ratio, best_raw = r, o

    if best_raw and best_ratio >= 0.86:
        return best_raw, f"fuzzy:{best_ratio:.2f}"

    return raw_target, None



def _education_ocr_fallback(region, scroll_anchor_abs, desired_value):
    """
    If Education isn't found in dataset (due to OCR variant),
    go straight to Education precise scan (both directions).
    NOTE: This is Education-only and does not affect other fields.
    """
    # Use the same Education precise routine to avoid mismatched logic.
    speak(f"Education: dataset miss → using precise scan for '{desired_value}'.")
    ok = education_precise_bidi_scan("Education", region, scroll_anchor_abs, desired_value)
    if not ok:
        speak(f"Education precise scan failed for '{desired_value}'. Closing dropdown.")
        try:
            pyautogui.press("esc")
            safe_sleep(0.2)
        except Exception:
            pass
    return ok


def fill_dropdown_by_memory(field_meta, field_abs_pos, desired_value):
    
    """
    Unified dropdown filler.
    - SPECIAL_PRECISE_ONLY fields: OCR-only precise scan (ignore dataset).
    - All other fields: dataset-based context scroll (prev/next 10 neighbors).
    """

    if 'dropdown_region_rel' not in field_meta:
        speak(f"No dropdown region stored for {field_meta.get('name','field')}.")
        return False

    field_name = field_meta.get("name", "")
    desired_value = (desired_value or "").strip()
    if not desired_value:
        speak("Empty desired value for dropdown.")
        return False
    # Height: accept small format variations by standardizing compare target
    if field_name.strip().lower() == "height":
        # Keep desired_value as-is for speech, but future compares will be normalized
        pass

# --- NEW: route heavy lists to specialized handler ---
    if field_name in ("District", "Cast", "Sub Cast"):
        return fill_heavy_dropdown(field_name, field_meta, field_abs_pos, desired_value)
    
    # Resolve dropdown region absolute
    rel = field_meta['dropdown_region_rel']
    region = (
        int(field_abs_pos[0] + rel[0]),
        int(field_abs_pos[1] + rel[1]),
        int(field_abs_pos[0] + rel[2]),
        int(field_abs_pos[1] + rel[3])
    )

    # Scroll anchor absolute
    if 'scroll_anchor_rel' in field_meta and field_meta['scroll_anchor_rel']:
        scroll_anchor_abs = (
            int(field_abs_pos[0] + field_meta['scroll_anchor_rel'][0]),
            int(field_abs_pos[1] + field_meta['scroll_anchor_rel'][1])
        )
    else:
        scroll_anchor_abs = ((region[0] + region[2]) // 2, (region[1] + region[3]) // 2)

    # Open dropdown
    click_abs(field_abs_pos[0], field_abs_pos[1])
    safe_sleep(0.4)
    


    # -------- CASE: Special precise-only fields (OCR only) --------
    if field_name.strip().lower() in SPECIAL_PRECISE_ONLY:
        speak(f"Special field {field_name} → precise scan with reasoning.")
        for attempt in range(DROPDOWN_MAX_SCROLLS * 2):
            check_pause()
            lines = ocr_region_lines_dropdown(
                region,
                debug_name=f"dropdown_special_{field_name}_{attempt}"
            )


            # --- Reasoning on OPEN for non-scrollable dropdowns ---
            # First snapshot right after opening the dropdown.
            if attempt == 0 and should_activate_reasoning(field_name, phase="open"):
                reason = choose_visible_option(field_name, desired_value, lines)
                if reasoning_click_option(region, reason):
                    speak(f"Selected {desired_value} using reasoning (open phase).")
                    return True


            # --- Reasoning in PRECISE mode for scrollable dropdowns ---
            if should_activate_reasoning(field_name, phase="precise"):
                reason = choose_visible_option(field_name, desired_value, lines)
                if reasoning_click_option(region, reason):
                    speak(f"Selected {desired_value} using reasoning (precise phase).")
                    return True


            # --- Fallback: old OCR substring behaviour ---
            for ln in lines:
                if desired_value.lower() in ln.get("text", "").strip().lower():
                    if verified_click_option(region, ln, desired_value):
                        speak(f"Selected {desired_value} (OCR fallback).")
                        return True

            # keep original scroll behaviour
            hardware_scroll_at(scroll_anchor_abs, steps=-1, pulses=1, fast=False)
            safe_sleep(0.4)

        speak(f"Option '{desired_value}' not found in {field_name}.")
        return False

    # -------- CASE: Normal dataset-driven fields --------
    if field_name not in DROPDOWN_OPTIONS:
        speak(f"No predefined options stored for {field_name}")
        return False

    options = DROPDOWN_OPTIONS[field_name]["options"]

    # ✅ Education-only canonicalization BEFORE context search
    lname = field_name.strip().lower()
    if lname == "education":
        canon, tag = _canonicalize_education_target(desired_value, options)
        if tag:
            speak(f"Education normalized '{desired_value}' -> '{canon}' ({tag})")
        # Always lock to canonical label for downstream matching
        desired_value = canon


    if lname == "education":
        found, prev_list, next_list = search_with_context_edu(options, desired_value, context=15)
    else:
        found, prev_list, next_list = search_with_context(options, desired_value, context=15)


    # ✅ Education-only OCR fallback instead of early exit
    if not found:
        if lname == "education":
            speak(f"Education: '{desired_value}' not found in dataset. Using OCR fallback.")
            return _education_ocr_fallback(region, scroll_anchor_abs, desired_value)

        speak(f"Value '{desired_value}' not found in {field_name} dataset.")
        return False


    if lname == "education":
        prev_set = set(_norm_edu_text(p) for p in prev_list)
        next_set = set(_norm_edu_text(n) for n in next_list)
    else:
        prev_set = set(p.lower() for p in prev_list)
        next_set = set(n.lower() for n in next_list)

    # --- SPECIAL CASE: Height → skip context fast scan, go straight to precise reasoning ---
    lname = field_name.strip().lower()
    if lname == "height":
        speak("Height dropdown: using reasoning-guided precise scan.")
        from reverse_precise_tracker import precise_dropdown_scan_with_reverse

        # when prev block triggers (forward)
        return precise_dropdown_scan_with_reverse(
            field_name, region, scroll_anchor_abs, desired_value,
            prev_neighbors=prev_list,
            next_neighbors=next_list,
            forward=True
        )

    # --- SPECIAL CASE: District / Cast / Sub Cast → also go straight to precise reasoning ---
    if lname in ("District", "Cast", "Sub Cast"):
        speak(f"{field_name} dropdown: using reasoning-guided precise scan.")
        # when next block triggers (reverse)
        return precise_dropdown_scan_with_reverse(
            field_name, region, scroll_anchor_abs, desired_value,
            prev_neighbors=prev_list,
            next_neighbors=next_list,
            forward=False
        )
    # --- Education: DO NOT force precise on open ---
    # Education should fast-scan first, and only enter precise when neighbor triggers fire
    # (prev/next block) or as a fallback after scan exhaustion.



    # --- Fast scroll until trigger ---
    for attempt in range(DROPDOWN_MAX_SCROLLS * 9):
        check_pause()
        if lname == "education":
            lines = ocr_region_lines_education(region, debug_name=f"dropdown_fast_{field_name}_{attempt}")
        else:
            lines = ocr_region_lines_dropdown(region, debug_name=f"dropdown_fast_{field_name}_{attempt}")



        # --- REASONING: open-phase for Height + non-scrollable dropdowns ---
        # Runs only on the very first snapshot after opening the dropdown.
        if attempt == 0 and should_activate_reasoning(field_name, phase="open"):
            reason = choose_visible_option(field_name, desired_value, lines)
            if reasoning_click_option(region, reason):
                speak(f"Selected {desired_value} using reasoning on open.")
                return True

        # -------------------------------------------------------------------

        visible_texts_raw = [
            ln["text"].strip()
            for ln in lines
            if ln.get("text") and ln["text"].strip()
        ]

        # IMPORTANT: Education must use the SAME normalization as prev_set/next_set
        if lname == "education":
            visible_texts = [_norm_edu_text(t) for t in visible_texts_raw]
        else:
            visible_texts = [t.lower() for t in visible_texts_raw]



        # End-guard to avoid infinite scrolling when the page stops changing
        global _dropdown_last_joined, _dropdown_stable_count
        try:
            _dropdown_last_joined
        except NameError:
            _dropdown_last_joined = ""
            _dropdown_stable_count = 0

        if lname == "education":
            joined = " ".join([_norm_edu_text(ln.get("text", "")) for ln in lines if ln.get("text", "").strip()])
        else:
            joined = " ".join([_norm_option_text(ln.get("text", "")) for ln in lines if ln.get("text", "").strip()])

        if joined == _dropdown_last_joined:
            _dropdown_stable_count += 1
            if _dropdown_stable_count >= 2:
                # Flip direction briefly to break dead-ends, then continue
                hardware_scroll_at(scroll_anchor_abs, steps=-1, pulses=8, fast=False)
                _dropdown_stable_count = 0
                _dropdown_last_joined = ""  # force recheck
                continue
        else:
            _dropdown_stable_count = 0
            _dropdown_last_joined = joined


        # Exact match (Education uses stronger normalization + Paddle-click)
        lname = field_name.strip().lower()

        if lname == "education":
            n_desired = _norm_edu_text(desired_value)
        else:
            n_desired = _norm_option_text(desired_value)

        short_target = (lname == "education" and len(n_desired) <= 4)

        for ln in lines:
            raw_txt = (ln.get('text','') or '').strip()
            if not raw_txt:
                continue

            n_raw = _norm_edu_text(raw_txt) if lname == "education" else _norm_option_text(raw_txt)
            if n_raw != n_desired:
                continue

            # --- Education short-abbrev guard (AA / AET / IIT etc.) ---
            if short_target:
                try:
                    box_w = float(ln.get("width", 0))
                    txt_len = max(1, len(raw_txt))
                    avg_char_w = box_w / txt_len
                    expected_w = avg_char_w * len(desired_value.strip())
                    if box_w > expected_w * 1.25:
                        continue
                except Exception:
                    pass

            if lname == "education":
                # IMPORTANT: verify + click using the visible OCR text (raw_txt)
                if verified_click_option_edu(region, ln, raw_txt):
                    speak(f"Selected {desired_value} directly.")
                    return True
            else:
                if verified_click_option(region, ln, desired_value):
                    speak(f"Selected {desired_value} directly.")
                    return True



                # Previous block trigger
        if any(txt in prev_set for txt in visible_texts):
            speak(f"Detected previous block for {desired_value}, switching to precise forward scan.")
            return precise_dropdown_scan(field_name, region, scroll_anchor_abs, desired_value, forward=True)

        # Next block trigger
        if any(txt in next_set for txt in visible_texts):
            speak(f"Detected next block for {desired_value}, switching to precise reverse scan.")
            return precise_dropdown_scan(field_name, region, scroll_anchor_abs, desired_value, forward=False)


        # Fast scroll (Education should move faster)
        if lname == "education":
            hardware_scroll_at(scroll_anchor_abs, steps=-1, pulses=4, fast=True)
            safe_sleep(0.75)
        else:
            hardware_scroll_at(scroll_anchor_abs, steps=-1, pulses=3.5, fast=False)
            safe_sleep(0.5)


    lname_end = field_name.strip().lower()

    # Education must NEVER fail without attempting precise scan
    if lname_end == "education":
        speak("Education: fast scan exhausted → forcing precise scan (both directions).")
        return education_precise_bidi_scan(field_name, region, scroll_anchor_abs, desired_value)


    speak(f"Failed to select {desired_value} after full dropdown scan in {field_name}.")
    return False

def precise_dropdown_scan(field_name, region, scroll_anchor_abs, target, forward=True):
    """
    Precise-phase: step-by-step OCR scanning until the target is found.

    - For big scrollable dropdowns (State, District, Cast, Sub Cast, Education, etc.),
      the reasoning module is used first on each page.
    - Then we fall back to normalized exact match.
    - For Height, we also use inches-based fallback.
    """
    direction = -1 if forward else +1
    is_height = (field_name or "").strip().lower() == "height"
    lname = (field_name or "").strip().lower()
    target_norm = _norm_edu_text(target) if lname == "education" else _norm_option_text(target)


    for attempt in range(DROPDOWN_MAX_SCROLLS * 6):
        check_pause()
        if (field_name or "").strip().lower() == "education":
            lines = ocr_region_lines_education(region, debug_name=f"dropdown_precise_{field_name}_{attempt}")
        else:
            lines = ocr_region_lines_dropdown(region, debug_name=f"dropdown_precise_{field_name}_{attempt}")


        # --- REASONING: precise-phase for scrollable dropdowns ---
        # Education: ALWAYS run reasoning (and log), even if profile/heuristic disables it.
        run_reasoning = (lname == "education") or should_activate_reasoning(field_name, phase="precise")
        if run_reasoning:
            reason = choose_visible_option(field_name, target, lines)

            

            if reasoning_click_option(region, reason):
                speak(f"Precisely selected {target} using reasoning.")
                return True


        # ----------------------------------------------------------

        # Fallback 1: normalized exact match (old behavior)
        

        for ln in lines:
            raw_txt = (ln.get("text", "") or "").strip()
            if not raw_txt:
                continue

            n_raw = _norm_edu_text(raw_txt) if lname == "education" else _norm_option_text(raw_txt)
            if n_raw != target_norm:
                continue

            if lname == "education":
                if verified_click_option_edu(region, ln, raw_txt):
                    # Education-only success trace
                    
                    speak(f"Precisely selected {target}")
                    return True

            else:
                if verified_click_option(region, ln, target):
                    speak(f"Precisely selected {target}")
                    return True


        # Fallback 2: Height-only inches matching (precise phase)
        if is_height:
            want_in = _extract_inches(target)
            if want_in is not None:
                for ln in lines:
                    got_in = _extract_inches(ln.get("text", ""))
                    if got_in is not None and abs(got_in - want_in) < 0.01:
                        if verified_click_option(region, ln, ln.get("text", "").strip()):
                            speak(f"Precisely selected {target} (height by inches).")
                            return True

        # Step-by-step scroll in chosen direction
        hardware_scroll_at(scroll_anchor_abs, steps=direction,
                           pulses=DROPDOWN_PRECISE_PULSES, fast=False)
        safe_sleep(0.4)

    speak(f"Failed to select {target} in precise scan for {field_name}.")
    return False


# ---------------- DOB helpers (REPLACE existing month_name_to_number, normalize_year, parse_dob, fill_dob_by_memory) ----------------
MONTHS_LIST = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
]

def month_name_to_number(m):
    """
    Return month number as integer (1..12) for a month name / abbreviation.
    Tolerant to OCR noise using startswith + fuzzy fallback.
    """
    if not m:
        return None
    mm = re.sub(r'[^A-Za-z]', '', str(m)).title().strip()
    if not mm:
        return None
    # direct startswith match (handles "Jul" -> "July")
    for idx, mn in enumerate(MONTHS_LIST, start=1):
        if mn.lower().startswith(mm.lower()):
            return idx
    # fuzzy fallback
    cand = difflib.get_close_matches(mm, MONTHS_LIST, n=1, cutoff=0.45)
    if cand:
        return MONTHS_LIST.index(cand[0]) + 1
    return None

def normalize_year(y):
    y = re.sub(r'[^0-9]', '', str(y))
    if not y:
        return None
    if len(y) == 2:
        yi = int(y)
        return str(1900 + yi) if yi > 30 else str(2000 + yi)
    if len(y) == 3:
        # avoid guessing 3-digit years
        return None
    return y

def parse_dob(value_str):
    """
    Return (day_int, month_int, year_str) or (None, None, None)
    Robust to formats like:
      - "25 July 1975", "25 Jul 75"
      - "25/07/1975", "25-07-1975"
      - "July 25 1975", "1975 July 25"
      - tolerant loose-token fallback
    """
    if not value_str:
        return None, None, None
    s = str(value_str).strip()
    s = s.replace(',', ' ').replace('.', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    sl = s.lower()

    # Try: 25 July 1975  (day month year)
    m = re.search(r'(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+)\s+(?P<year>\d{2,4})', sl)
    if m:
        try:
            day = int(m.group('day'))
        except:
            day = None
        month = month_name_to_number(m.group('month'))
        year = normalize_year(m.group('year'))
        if day and 1 <= day <= 31 and month and year:
            return day, month, year

    # Try: July 25 1975  (month day year)
    m = re.search(r'(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2})\s+(?P<year>\d{2,4})', sl)
    if m:
        try:
            day = int(m.group('day'))
        except:
            day = None
        month = month_name_to_number(m.group('month'))
        year = normalize_year(m.group('year'))
        if day and 1 <= day <= 31 and month and year:
            return day, month, year

    # numeric dd/mm/yyyy or dd-mm-yyyy
    m = re.search(r'(?P<day>\d{1,2})[\/\-](?P<month>\d{1,2})[\/\-](?P<year>\d{2,4})', sl)
    if m:
        try:
            day = int(m.group('day')); month = int(m.group('month'))
        except:
            day = month = None
        year = normalize_year(m.group('year'))
        if day and 1 <= day <= 31 and month and 1 <= month <= 12 and year:
            return day, month, year

    # Try year month day
    m = re.search(r'(?P<year>\d{4})\s+(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2})', sl)
    if m:
        try:
            day = int(m.group('day'))
        except:
            day = None
        month = month_name_to_number(m.group('month'))
        year = normalize_year(m.group('year'))
        if day and 1 <= day <= 31 and month and year:
            return day, month, year

    # Loose token-based fallback (scan tokens for day/month/year)
    tokens = sl.split()
    day = None; month = None; year = None
    for t in tokens:
        if day is None and re.fullmatch(r'\d{1,2}', t):
            di = int(t)
            if 1 <= di <= 31:
                day = di; continue
        if year is None and re.fullmatch(r'\d{2,4}', t):
            ny = normalize_year(t)
            if ny:
                year = ny; continue
        if month is None and re.fullmatch(r'[a-z]{3,}', t):
            mn = month_name_to_number(t)
            if mn:
                month = mn; continue

    if day and month and year:
        return day, month, year

   

    return None, None, None

def fill_dob_by_memory(field_meta, value_str):
    """
    Simplified DOB filler for numeric fields:
    - Day: 01..31 (always 2 digits)
    - Month: 01..12 (always 2 digits)
    - Year: YYYY (always 4 digits)
    """
    day, month, year = parse_dob(value_str)
    if not (day and month and year):
        speak(f"Could not parse DOB: {value_str}")
        return False

    if not ('day_pos' in field_meta and 'month_pos' in field_meta and 'year_pos' in field_meta):
        speak("DOB positions missing in memory.")
        return False

    dpos = tuple(field_meta['day_pos'])
    mpos = tuple(field_meta['month_pos'])
    ypos = tuple(field_meta['year_pos'])

    # Normalize to correct formats
    day_str   = f"{int(day):02d}"
    month_str = f"{int(month):02d}"
    year_str  = str(year).zfill(4)

    def type_value(pos, val, label):
        pyautogui.click(pos[0], pos[1])
        time.sleep(0.08)
        clear_field_by_backspace(10)
        pyautogui.typewrite(val, interval=0.1)
        time.sleep(0.1)
        speak(f"Entered {label}: {val}")

    # 🔴 IMPORTANT: set YEAR first to avoid MPF rejecting “future” dates
    type_value(ypos, year_str, "Year")
    type_value(mpos, month_str, "Month")
    type_value(dpos, day_str, "Day")

    

    speak(f"Final DOB = {day_str}/{month_str}/{year_str}")
    return True



# ---------------- Info panel calibration via two clicks ----------------
def calibrate_info_panel_via_clicks(mem):
    speak("Hover top-left of information panel and press '1'.")
    print("Hover top-left and press 1")
    keyboard.wait('1')
    p1 = pyautogui.position()
    speak(f"Top-left recorded at {p1.x},{p1.y}. Now hover bottom-right and press '2'.")
    print("Hover bottom-right and press 2")
    keyboard.wait('2')
    p2 = pyautogui.position()
    x1, y1 = min(p1.x, p2.x), min(p1.y, p2.y)
    x2, y2 = max(p1.x, p2.x), max(p1.y, p2.y)
    mem['info_panel_region'] = [x1, y1, x2, y2]
    save_memory(mem)
    speak("Information panel region saved.")

# ---------------- Learning Mode (voice-guided) ----------------
def learning_mode():
    global SPEAK_ENABLED
    SPEAK_ENABLED = True
    speak("Starting Learning Mode. I will lead you through anchor, spacing, fields and scroll trigger captures.")
    mem = {
        "anchor": None,
        "spacing": None,
        "fields": [],
        "scrollbars": {},
        "main_scroll_triggers": [],
        "info_scroll_triggers": []
    }
    

    # anchor capture
    speak("Hover the top-most input field and press F to capture anchor.")
    print("Hover top-most input and press F")
    keyboard.wait('f')
    p = pyautogui.position()
    mem['anchor'] = [p.x, p.y]
    speak(f"Anchor set to {p.x},{p.y}")

    # spacing capture
    speak("Hover the second input field (below the first) and press G to capture spacing.")
    print("Hover second field and press G")
    keyboard.wait('g')
    p2 = pyautogui.position()
    mem['spacing'] = abs(p2.y - mem['anchor'][1])
    speak(f"Spacing saved: {mem['spacing']} pixels")

    # optional info panel calibration
    speak("To calibrate information panel region now press C, otherwise press F5 to skip.")
    print("Press C to calibrate info panel region or F5 to skip")
    start = time.time(); did = False
    while time.time() - start < 6:
        if keyboard.is_pressed('c'):
            calibrate_info_panel_via_clicks(mem)
            did = True; time.sleep(0.3); break
        if keyboard.is_pressed('f5'):
            speak("Skipping info panel calibration.")
            did = True; time.sleep(0.2); break
        time.sleep(0.05)
    if not did:
        speak("Proceeding without info calibration.")
    # optional input panel calibration
    speak("Now hover top-left of the INPUT panel and press '7'.")
    keyboard.wait('7')
    p1 = pyautogui.position()
    speak(f"Top-left recorded at {p1.x},{p1.y}. Now hover bottom-right and press '8'.")
    keyboard.wait('8')
    p2 = pyautogui.position()
    x1, y1 = min(p1.x, p2.x), min(p1.y, p2.y)
    x2, y2 = max(p1.x, p2.x), max(p1.y, p2.y)
    mem['input_panel_region'] = [x1, y1, x2, y2]
    save_memory(mem)
    speak("Input panel region saved.")

    # optional capture general scrollbar anchors
    speak("If you want to capture main scrollbar now hover it and press M (8 sec window) or press F5 to skip.")
    print("Hover main scrollbar and press M or F5 to skip")
    start = time.time(); captured = False
    while time.time() - start < 8:
        if keyboard.is_pressed('m'):
            sp = pyautogui.position(); mem['scrollbars']['main'] = [sp.x, sp.y]; speak("Main scrollbar anchor saved."); captured = True; time.sleep(0.3); break
        if keyboard.is_pressed('f5'):
            speak("Main scrollbar skipped."); captured = True; time.sleep(0.2); break
        time.sleep(0.05)

    speak("If you want to capture info scrollbar now hover it and press N (8 sec window) or press F5 to skip.")
    print("Hover info scrollbar and press N or F5 to skip")
    start = time.time(); captured = False
    while time.time() - start < 8:
        if keyboard.is_pressed('n'):
            sp = pyautogui.position(); mem['scrollbars']['info'] = [sp.x, sp.y]; speak("Info scrollbar anchor saved."); captured = True; time.sleep(0.3); break
        if keyboard.is_pressed('f5'):
            speak("Info scrollbar skipped."); captured = True; time.sleep(0.2); break
        time.sleep(0.05)

    # iterate fields
    speak("Now I will walk through canonical fields. For each field hover on it and press: T=typing, D=dropdown, B=dob, K=skip.")
    time.sleep(0.6)

    for canonical in FIELD_ORDER:
        check_pause()
        speak(f"Hover over the field for {canonical} and press T, D, B or K.")
        print(f"Hover field: {canonical} and press T/D/B/K")
        while True:
            if keyboard.is_pressed('t'):
                posf = pyautogui.position()
                idx = round((posf.y - mem['anchor'][1]) / mem['spacing']) if mem['anchor'] and mem['spacing'] else None
                mem['fields'].append({"name": canonical, "type": "typing", "pos": [posf.x, posf.y], "index": idx})
                speak(f"Saved typing field {canonical}")
                time.sleep(0.3)
                # check for main/info triggers
                if canonical in MAIN_SCROLL_FIELDS:
                    speak(f"After {canonical} you want a MAIN scroll. Hover main scrollbar and press M to record its current location.")
                    print(f"Hover main scrollbar and press M to record trigger for {canonical}")
                    keyboard.wait('m')
                    sp = pyautogui.position()
                    mem['main_scroll_triggers'].append({"after_field": canonical, "anchor": [sp.x, sp.y]})
                    speak("Recorded main-scroll trigger.")
                if canonical in INFO_SCROLL_FIELDS:
                    speak(f"After {canonical} you want an INFO scroll. Hover info scrollbar and press N to record its current location.")
                    print(f"Hover info scrollbar and press N to record trigger for {canonical}")
                    keyboard.wait('n')
                    sp = pyautogui.position()
                    mem['info_scroll_triggers'].append({"after_field": canonical, "anchor": [sp.x, sp.y]})
                    speak("Recorded info-scroll trigger.")
                break

            elif keyboard.is_pressed('d'):
                posf = pyautogui.position()
                name = canonical
                speak("Open the dropdown in the app, hover top-left of the visible dropdown and press O.")
                print("Open dropdown, hover top-left, press O")
                keyboard.wait('o')
                tl = pyautogui.position()
                speak("Now hover bottom-right of the visible dropdown and press P.")
                print("Hover bottom-right and press P")
                keyboard.wait('p')
                br = pyautogui.position()
                rel = [tl.x - posf.x, tl.y - posf.y, br.x - posf.x, br.y - posf.y]
                speak("If dropdown has a scrollbar hover it and press R; otherwise press F5 to skip.")
                start = time.time(); scrollbar_rel = None
                while time.time() - start < 6:
                    if keyboard.is_pressed('r'):
                        sc = pyautogui.position(); scrollbar_rel = [sc.x - posf.x, sc.y - posf.y]; speak("Recorded dropdown scrollbar."); time.sleep(0.2); break
                    if keyboard.is_pressed('f5'):
                        speak("Dropdown scrollbar skipped."); time.sleep(0.2); break
                    time.sleep(0.05)
                speak("Now hover a sample visible option and press Q.")
                print("Hover sample option and press Q")
                keyboard.wait('q')
                sample = pyautogui.position()
                sample_rel_y = sample.y - tl.y
                idx = round((posf.y - mem['anchor'][1]) / mem['spacing']) if mem['anchor'] and mem['spacing'] else None
                mem['fields'].append({
                    "name": name,
                    "type": "dropdown",
                    "pos": [posf.x, posf.y],
                    "index": idx,
                    "dropdown_region_rel": rel,
                    "dropdown_sample_rel_y": sample_rel_y,
                    "scroll_anchor_rel": scrollbar_rel
                })
                speak(f"Saved dropdown field {canonical}")
                time.sleep(0.3)
                # if this field should trigger main/info scroll, record now
                if canonical in MAIN_SCROLL_FIELDS:
                    speak(f"After {canonical} record MAIN scrollbar location now by hovering and pressing M.")
                    keyboard.wait('m'); sp = pyautogui.position()
                    mem['main_scroll_triggers'].append({"after_field": canonical, "anchor": [sp.x, sp.y]})
                    speak("Recorded main-scroll trigger.")
                if canonical in INFO_SCROLL_FIELDS:
                    speak(f"After {canonical} record INFO scrollbar location now by hovering and pressing N.")
                    keyboard.wait('n'); sp = pyautogui.position()
                    mem['info_scroll_triggers'].append({"after_field": canonical, 'anchor': [sp.x, sp.y]} )
                    speak("Recorded info-scroll trigger.")
                break

            elif keyboard.is_pressed('b'):
                name = canonical
                speak("Hover over DAY box and press 1.")
                keyboard.wait('1'); dayp = pyautogui.position()
                speak("Hover over MONTH box and press 2.")
                keyboard.wait('2'); monthp = pyautogui.position()
                speak("Hover over YEAR box and press 3.")
                keyboard.wait('3'); yearp = pyautogui.position()
                idx = round((dayp.y - mem['anchor'][1]) / mem['spacing']) if mem['anchor'] and mem['spacing'] else None
                mem['fields'].append({
                    "name": name,
                    "type": "dob",
                    "day_pos": [dayp.x, dayp.y],
                    "month_pos": [monthp.x, monthp.y],
                    "year_pos": [yearp.x, yearp.y],
                    "index": idx
                })
                speak(f"Saved DOB field {canonical}")
                time.sleep(0.3)
                if canonical in MAIN_SCROLL_FIELDS:
                    speak(f"After {canonical} record MAIN scrollbar by hovering and pressing M.")
                    keyboard.wait('m'); sp = pyautogui.position()
                    mem['main_scroll_triggers'].append({"after_field": canonical, "anchor": [sp.x, sp.y]})
                    speak("Recorded main-scroll trigger.")
                if canonical in INFO_SCROLL_FIELDS:
                    speak(f"After {canonical} record INFO scrollbar by hovering and pressing N.")
                    keyboard.wait('n'); sp = pyautogui.position()
                    mem['info_scroll_triggers'].append({"after_field": canonical, "anchor": [sp.x, sp.y]})
                    speak("Recorded info-scroll trigger.")
                break

            elif keyboard.is_pressed('k'):
                speak(f"Skipped {canonical}")
                time.sleep(0.2)
                break
            time.sleep(0.05)
                # --- NEW: Capture Upload / OK / Take Screenshot / Load Another Form flow ---
    speak("If you want me to also automate Upload, Screenshot and Load Another Form, press U now. Or press F5 to skip.")
    print("Press U to capture upload flow (Upload, OK, Take Screenshot, Load Another Form) or F5 to skip.")
    start = time.time()
    captured = False
    while time.time() - start < 12:
        if keyboard.is_pressed('u'):
            time.sleep(0.3)
            # 1) Upload Details button
            speak("Hover over the 'Upload Details' button and press 1.")
            print("Hover over 'Upload Details' and press 1")
            keyboard.wait('1')
            up = pyautogui.position()
            mem['upload_button_pos'] = [up.x, up.y]

            # 2) OK button (after upload)
            speak("Now hover over the 'OK' button that appears after upload and press 2.")
            print("Hover over 'OK' button and press 2")
            keyboard.wait('2')
            okp = pyautogui.position()
            mem['upload_ok_button_pos'] = [okp.x, okp.y]

            # 3) Region where Take Screenshot + Load Another Form appear
            speak("Now mark the region where 'Take Screenshot' and 'Load Another Form' buttons appear.")
            speak("Hover the TOP-LEFT corner of that area and press 3.")
            print("Hover TOP-LEFT of upload flow region and press 3")
            keyboard.wait('3')
            tl = pyautogui.position()

            speak("Hover the BOTTOM-RIGHT corner of the same area and press 4.")
            print("Hover BOTTOM-RIGHT of upload flow region and press 4")
            keyboard.wait('4')
            br = pyautogui.position()

            x1, y1 = min(tl.x, br.x), min(tl.y, br.y)
            x2, y2 = max(tl.x, br.x), max(tl.y, br.y)
            mem['upload_flow_region'] = [x1, y1, x2, y2]

            speak("Upload, OK and upload-flow region captured successfully.")
            captured = True
            break

        if keyboard.is_pressed('f5'):
            speak("Skipping upload and next-form automation capture.")
            captured = True
            time.sleep(0.3)
            break

        time.sleep(0.05)


    save_memory(mem)
    speak("Learning mode finished and memory saved. Press F3 to run Autofill when ready.")
def upload_learning_mode_only():
    global SPEAK_ENABLED
    SPEAK_ENABLED = True
    mem = load_memory()
    if not mem:
        speak("No existing memory found. Please run full Learning Mode once before using this.")
        print("No bot_memory.json found. Run F2 full learning first.")
        return

    speak("Starting Upload-Only Learning Mode.")
    print("Upload-Only Learning Mode: capturing Upload / OK / Take Screenshot / Load Another Form / region.")

    speak("Hover over the 'Upload Details' button and press 1.")
    keyboard.wait('1')
    up = pyautogui.position()
    mem['upload_button_pos'] = [up.x, up.y]

    speak("Now hover over the 'OK' button that appears after upload and press 2.")
    keyboard.wait('2')
    okp = pyautogui.position()
    mem['upload_ok_button_pos'] = [okp.x, okp.y]

    speak("Now hover over the 'Take Screenshot' button and press 3.")
    keyboard.wait('3')
    ts = pyautogui.position()
    mem['take_screenshot_button_pos'] = [ts.x, ts.y]

    speak("Now hover over the 'Load Another Form' button and press 4.")
    keyboard.wait('4')
    la = pyautogui.position()
    mem['load_another_form_button_pos'] = [la.x, la.y]

    speak("Internet Error OK is now automatically handled by the Enter key.")

    speak("Now mark the region where loading happens and where these buttons appear.")
    speak("Hover the TOP-LEFT corner of that area and press 6.")
    keyboard.wait('6')
    tl = pyautogui.position()

    speak("Hover the BOTTOM-RIGHT corner of the same area and press 7.")
    keyboard.wait('7')
    br = pyautogui.position()

    x1, y1 = min(tl.x, br.x), min(tl.y, br.y)
    x2, y2 = max(tl.x, br.x), max(tl.y, br.y)
    mem['upload_flow_region'] = [x1, y1, x2, y2]

    save_memory(mem)
    speak("Upload learning completed and memory saved. You can now run Autofill Mode.")
    print("Upload learning completed and memory saved.")
def capture_error_recovery_buttons():
    """
    Mini learning mode: Captures the Start MPF button for blank page recoveries.
    Internet Error OK is bypassed using the Enter key.
    """
    global SPEAK_ENABLED
    SPEAK_ENABLED = True  # Guarantee speech is ON for learning

    mem = load_memory()
    if not mem:
        speak("No existing memory found. Please run full Learning Mode once before using this.")
        return

    speak("Starting Error Recovery Capture Mode.")
    speak("Internet error is handled automatically via Enter Key.")

    speak("Hover over the 'Start MPF' button to recover from blank pages and press 6.")
    keyboard.wait('6')
    smpf = pyautogui.position()
    mem['start_mpf_button_pos'] = [smpf.x, smpf.y]

    save_memory(mem)
    speak("Recovery buttons saved successfully.")
    print(f"Saved Start MPF at: {smpf.x}, {smpf.y}")
def start_info_panel_paddle_session(use_orientation=True):
    from paddle_info_panel_ocr import PaddleInfoPanelSession
    return PaddleInfoPanelSession(use_orientation=use_orientation)

# ---------------- Autofill Mode ----------------
def snip_info_panel_from_memory(mem):
    """
    Info panel extraction (PaddleOCR ONLY).
    Everything else stays on old OCR systems.
    """
    if 'info_panel_region' in mem:
        x1, y1, x2, y2 = mem['info_panel_region']
        region = (x1, y1, x2, y2)
        print("[INFO_PANEL] Using PaddleOCR module...")

        try:
            # PaddleOCR only for info panel
            session = None
            try:
                session = start_info_panel_paddle_session(use_orientation=True)

                mapped, paddle_text = extract_info_panel_paddle(
                    region_bbox=region,
                    canonical_fields=FIELD_ORDER,
                    debug_dir=None,
                    debug_prefix="info_panel_paddle",
                    min_conf=0.10,
                    use_orientation=True,
                    session=session,   # ✅ reuse the same instance
                )

            finally:
                if session:
                    session.close()

            print("[INFO_PANEL] PaddleOCR done.")
            # ✅ NEW: log raw Paddle mapping output
            _log_mapping_debug("PADDLE_MAPPED_RAW", mapped)


            # If Paddle mapping is empty but Paddle DID read text,
            # parse Paddle text using existing parser (still Paddle OCR, not old OCR)
            if not mapped:
                if paddle_text and paddle_text.strip():
                    print("[INFO_PANEL] Paddle mapping empty, but Paddle text exists -> parsing Paddle text with old parser")

                    kv = extract_kv_from_text(paddle_text)
                    mapped = fuzzy_map_kv(kv, FIELD_ORDER)

                    try:
                        mapped = _normalize_info_panel_mapping(mapped)
                    except Exception as e:
                        print("[INFO_NORMALIZER ERROR]", e)
                        _log_mapping_debug("PADDLE_MAPPED_NORMALIZED", mapped)

                    return mapped

                # Only if Paddle produced truly nothing, then use old OCR
                print("[INFO_PANEL] Paddle produced no text at all -> HARD FAIL (no fallback).")
                
                return {}   # or: raise RuntimeError("Info panel PaddleOCR returned empty text")


            # If Paddle produced nothing, fallback to old OCR (do not abort)
            if not mapped:
                raw_text = smart_ocr_text(region)
                
                kv = extract_kv_from_text(raw_text)
                mapped = fuzzy_map_kv(kv, FIELD_ORDER)
                mapped = _normalize_info_panel_mapping(mapped)
                return mapped

            # (Optional) run your existing normalizers too (dropdown normalization etc.)
            try:
                mapped = _normalize_info_panel_mapping(mapped)
            except Exception as e:
                print("[INFO_NORMALIZER ERROR]", e)
                _log_mapping_debug("PADDLE_MAPPED_NORMALIZED", mapped)

            # save debug text snapshot (we write from paddle module already, but keep compatibility)
                

            return mapped

        except Exception as e:
            print("[PADDLE INFO OCR ERROR]", e)
        
        return {}   # or: raise


    else:
        speak("No saved info panel region. Trying interactive snip (may be blocked).")
        return interactive_info_snip_fallback()
from paddle_info_panel_ocr import PaddleInfoPanelSession, extract_info_panel_paddle


def read_info_panel_full_before_autofill(mem) -> dict:
    """
    New logic (FAST):
      1) OCR visible info at top
      2) scroll info panel until 'Rashi' disappears
      3) OCR again + merge
      4) scroll to end
      5) OCR again + merge
    Uses ONE PaddleOCR session only.

    ✅ NEW:
      - Stores RAW joined PaddleOCR text for each pass into debug_logs/
      - Also appends everything into debug_logs/info_panel_raw_history.txt
    """
    combined = {}

    if "info_panel_region" not in mem:
        return combined

    region = tuple(mem["info_panel_region"])

    # Ensure we start from top
    #scroll_info_panel_to_top(mem)
    safe_sleep(0.15)

    # Unique timestamp for this run (so files don't overwrite)
    ts = time.strftime("%Y%m%d_%H%M%S")

    # 🔥 CREATE ONE PADDLE SESSION ONLY
    session = PaddleInfoPanelSession(use_orientation=False)

    try:
        # ---------- PASS 1 ----------
        d1, raw1 = extract_info_panel_paddle(
            region_bbox=region,
            canonical_fields=FIELD_ORDER,
            min_conf=0.10,
            session=session,  # ✅ REUSE
            debug_dir=None,
            debug_prefix=f"info_panel_pass1_{ts}",
        )
        _append_info_panel_raw("PASS1_TOP", raw1)
        combined = merge_info_dict(combined, d1)

        # ---------- SCROLL UNTIL RASHI DISAPPEARS ----------
        if "info" in mem.get("scrollbars", {}):
            scroll_info_panel_until_rashi_disappears_precise(
                mem,
                check_text="Rashi",
                step_scroll=-65,   # precise
                pause_per_step=0.04
            )
            safe_sleep(0.15)

        # ---------- PASS 2 ----------
        d2, raw2 = extract_info_panel_paddle(
            region_bbox=region,
            canonical_fields=FIELD_ORDER,
            min_conf=0.10,
            session=session,  # ✅ SAME SESSION
            debug_dir=DEBUG_DIR,
            debug_prefix=f"info_panel_pass2_{ts}",
        )
        _append_info_panel_raw("PASS2_AFTER_RASHI_SCROLL", raw2)
        combined = merge_info_dict(combined, d2)

        # ---------- SCROLL TO END ----------
        if "info" in mem.get("scrollbars", {}):
            anchor = tuple(mem["scrollbars"]["info"])
            scroll_to_end(anchor, region)
            safe_sleep(0.15)

        # ---------- PASS 3 ----------
        d3, raw3 = extract_info_panel_paddle(
            region_bbox=region,
            canonical_fields=FIELD_ORDER,
            min_conf=0.10,
            session=session,  # ✅ SAME SESSION
            debug_dir=DEBUG_DIR,
            debug_prefix=f"info_panel_pass3_{ts}",
        )
        _append_info_panel_raw("PASS3_BOTTOM", raw3)
        combined = merge_info_dict(combined, d3)
        

    finally:
        # 🔻 CLOSE PADDLE ONCE
        session.close()

        # --- DEBUG: snapshot before dropdown-only normalization ---
        _log_mapping_debug("MERGED_BEFORE_DROPDOWN_NORMALIZE", combined)

        # --- SAFETY: normalize ONLY dropdown-like fields (District/Education/Caste/etc.) ---
        # (Codes like PHI/MBI/RAI/FAI are already handled in paddle_info_panel_ocr safety rules)
        try:
            combined = normalize_info_panel_targets(combined, only_dropdown_fields=True)
        except Exception as e:
            print("[INFO_NORMALIZER ERROR]", e)

        # --- DEBUG: snapshot after normalization ---
        _log_mapping_debug("MERGED_AFTER_DROPDOWN_NORMALIZE", combined)

        # Save merged result (optional debug) - NOW this will reflect normalized dropdown values
        

        return combined





def interactive_info_snip_fallback():
    speak("Interactive snip: draw rectangle in the small window if possible. Press q to cancel.")
    region = pyautogui.screenshot()
    region = cv2.cvtColor(np.array(region), cv2.COLOR_RGB2BGR)
    x_start = y_start = x_end = y_end = 0
    cropping = False
    roi = None
    

    def mouse_crop(event, x, y, flags, param):
        nonlocal x_start, y_start, x_end, y_end, cropping, roi
        if event == cv2.EVENT_LBUTTONDOWN:
            x_start, y_start, x_end, y_end = x, y, x, y
            cropping = True
        elif event == cv2.EVENT_MOUSEMOVE and cropping:
            x_end, y_end = x, y
        elif event == cv2.EVENT_LBUTTONUP:
            x_end, y_end = x, y
            cropping = False
            roi = region[y_start:y_end, x_start:x_end]
            cv2.destroyWindow("Select")

    cv2.namedWindow("Select"); cv2.setMouseCallback("Select", mouse_crop)
    while True:
        clone = region.copy()
        if cropping:
            cv2.rectangle(clone, (x_start, y_start), (x_end, y_end), (0, 255, 0), 2)
        cv2.imshow("Select", clone)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cv2.destroyAllWindows()
    if roi is None:
        speak("No snip captured.")
        return {}
    pil_roi = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
    prep, _ = preprocess_for_ocr(pil_roi, scale=2)
    raw = pytesseract.image_to_string(prep)
    
    kv = extract_kv_from_text(raw)
    mapped = fuzzy_map_kv(kv, FIELD_ORDER)
    mapped = _normalize_info_panel_mapping(mapped)
    return mapped

# ---- PADA FIX (add-only) ----------------------------------------------------
import re as _re

def _norm_pada_ord(s: str) -> str:
    """
    Normalize any 1/I st/nd/rd/th + 'pada' variants to {1,2,3,4}.
    Accepts '1st Pada', '1 st pada', 'Ist Pada', 'I st pada', etc.
    Returns '1','2','3','4' or '' if not recognized.
    """
    if not s: 
        return ""
    t = (s or "").strip().lower()
    # drop trailing punctuation
    t = t.rstrip(" .,:;")
    # common folds
    t = _re.sub(r"\s+", " ", t)
    # allow i ↔ 1 for '1st'
    if _re.search(r"^(?:1|i)\s*st\s*pada$", t): return "1"
    if _re.search(r"^first\s*pada$", t): return "1"
    if _re.search(r"^2\s*nd\s*pada$", t): return "2"
    if _re.search(r"^second\s*pada$", t): return "2"
    if _re.search(r"^3\s*rd\s*pada$", t): return "3"
    if _re.search(r"^third\s*pada$", t): return "3"
    if _re.search(r"^4\s*th\s*pada$", t): return "4"
    if _re.search(r"^fourth\s*pada$", t): return "4"
    return ""

def _desired_pada_ord(desired_value: str) -> str:
    """Map the canonical desired text to an ordinal '1'..'4'."""
    d = (desired_value or "").strip().lower()
    if "1" in d or "first" in d: return "1"
    if "2" in d or "second" in d: return "2"
    if "3" in d or "third"  in d: return "3"
    if "4" in d or "fourth" in d: return "4"
    return ""

def _resolve_dropdown_region_and_anchor_fast(field_meta, field_abs_pos):
    """Lightweight resolver (same math as your existing helper)."""
    rel = field_meta['dropdown_region_rel']
    region = (
        int(field_abs_pos[0] + rel[0]),
        int(field_abs_pos[1] + rel[1]),
        int(field_abs_pos[0] + rel[2]),
        int(field_abs_pos[1] + rel[3])
    )
    if field_meta.get('scroll_anchor_rel'):
        anchor = (
            int(field_abs_pos[0] + field_meta['scroll_anchor_rel'][0]),
            int(field_abs_pos[1] + field_meta['scroll_anchor_rel'][1])
        )
    else:
        anchor = ((region[0] + region[2]) // 2, (region[1] + region[3]) // 2)
    return region, anchor

def fill_pada_dropdown_strict(field_meta, field_abs_pos, desired_value) -> bool:
    """
    Regex-tolerant selector *only* for 'Pada' that fixes the '1st/Ist' mismatch.
    - Verifies using the OCR'd line text itself (so micro-verify passes).
    - Falls back to a safe direct click if micro-verify still fails.
    """
    desired_ord = _desired_pada_ord(desired_value)
    if not desired_ord:
        return False

    # open dropdown
    click_abs(field_abs_pos[0], field_abs_pos[1])
    safe_sleep(0.35)

    # resolve region/anchor
    region, scroll_anchor_abs = _resolve_dropdown_region_and_anchor_fast(field_meta, field_abs_pos)

    def _is_target_line(txt: str) -> bool:
        got = _norm_pada_ord(txt)
        return (got == desired_ord)

    # Try a few pages precisely; then step-scroll if needed
    for attempt in range(DROPDOWN_MAX_SCROLLS * 2):
        check_pause()
        lines = ocr_region_lines_dropdown(region, debug_name=f"pada_fix_{attempt}")
        # 1) exact tolerant match on this page
        for ln in lines:
            raw = (ln.get('text') or "").strip()
            if not raw: 
                continue
            if _is_target_line(raw.lower()):
                # micro-verify using the ACTUAL on-screen text to avoid canonical mismatch
                if verified_click_option(region, ln, raw):
                    speak(f"Selected {raw} (Pada fix)")
                    return True
                # ultra-safe fallback: do a precise single click without verify
                try:
                    abs_box = {
                        'left': region[0] + int(ln.get('left', 0)),
                        'top':  region[1] + int(ln.get('top',  0)),
                        'width':  int(ln.get('width',  1)),
                        'height': int(ln.get('height', 1)),
                    }
                    if _precise_single_click(abs_box):
                        speak(f"Selected {raw} (Pada fix fallback)")
                        return True
                except Exception:
                    pass

        # 2) if not found, step scroll down a bit and continue
        hardware_scroll_at(scroll_anchor_abs, steps=-1, pulses=2, fast=False)
        safe_sleep(0.12)

    speak(f"Pada fix: could not find {desired_value}")
    return False
# ---- END PADA FIX ------------------------------------------------------------
# ---- DIET STRICT FIX (isolated) --------------------------------------------
import re as _diet_re

# Only these are valid
_DIET_CANON = ["Veg", "Non-Veg", "Occasionally Non-Veg", "Eggetarian", "Jain", "Vegan"]

def _diet_norm(s: str) -> str:
    """
    Normalize diet strings for strict equality:
    - case-insensitive
    - collapse multiple spaces
    - normalize hyphen variants: non veg / non-veg / non – veg  -> non-veg
    - trim punctuation at ends
    """
    if not s:
        return ""
    t = (str(s)).strip()
    # remove trailing punctuation
    t = t.rstrip(" .,:;")
    # unify hyphen variants around 'non[- ]veg'
    t = _diet_re.sub(r'(?i)\bnon\s*[-–]?\s*veg\b', 'Non-Veg', t)  # force exact casing here
    # collapse spaces
    t = _diet_re.sub(r'\s+', ' ', t)
    # capitalize first letters of words except the hyphen piece we already set
    # keep exact canonical tokens if present
    # Make a lowercase baseline first (except Non-Veg we already set)
    if t != "Non-Veg":
        t = t.title()
    return t

def _diet_is_valid_canon(s: str) -> bool:
    return _diet_norm(s) in _DIET_CANON

def _resolve_dropdown_region_and_anchor_for_diet(field_meta, field_abs_pos):
    """Same math as your other resolver, kept local for isolation."""
    rel = field_meta['dropdown_region_rel']
    region = (
        int(field_abs_pos[0] + rel[0]),
        int(field_abs_pos[1] + rel[1]),
        int(field_abs_pos[0] + rel[2]),
        int(field_abs_pos[1] + rel[3])
    )
    if field_meta.get('scroll_anchor_rel'):
        anchor = (
            int(field_abs_pos[0] + field_meta['scroll_anchor_rel'][0]),
            int(field_abs_pos[1] + field_meta['scroll_anchor_rel'][1])
        )
    else:
        anchor = ((region[0] + region[2]) // 2, (region[1] + region[3]) // 2)
    return region, anchor

def fill_diet_dropdown_strict(field_meta, field_abs_pos, desired_value) -> bool:
    """
    Dedicated handler for Diet.
    Rules:
      - open dropdown
      - scan current page
      - click only the row whose normalized text == normalized desired (strict equality)
      - scroll step-by-step until found
      - micro-verify using the exact on-screen row text to avoid false positives
    """
    want = _diet_norm(desired_value)
    if not want or not _diet_is_valid_canon(want):
        speak(f"Diet value '{desired_value}' not recognized.")
        return False

    # Open the Diet dropdown
    click_abs(field_abs_pos[0], field_abs_pos[1])
    safe_sleep(0.35)

    region, scroll_anchor_abs = _resolve_dropdown_region_and_anchor_for_diet(field_meta, field_abs_pos)

    # Try a generous number of pages, strict match only
    for attempt in range(DROPDOWN_MAX_SCROLLS * 3):
        check_pause()
        lines = ocr_region_lines_dropdown(region, debug_name=f"diet_fix_{attempt}")
        for ln in lines:
            raw = (ln.get('text') or "").strip()
            if not raw:
                continue
            if _diet_norm(raw) == want:
                # For micro-verify, use the EXACT on-screen row text (raw), not the canonical target
                if verified_click_option(region, ln, raw):
                    speak(f"Diet selected: {raw}")
                    return True
                # If micro-verify fails due to OCR microbox noise, try once more:
                if verified_click_option(region, ln, raw):
                    speak(f"Diet selected (retry): {raw}")
                    return True

        # Not on this page — take a small precise scroll forward
        hardware_scroll_at(scroll_anchor_abs, steps=-1, pulses=1, fast=False)
        safe_sleep(0.06)

    speak(f"Diet selection failed for '{desired_value}'.")
    return False
# ---- END DIET STRICT FIX ----------------------------------------------------
# ---- PADA TARGET NORMALIZER (Info Panel → Canonical) ----------------------
import re
import difflib

_PADA_CANON = ["1st Pada", "2nd Pada", "3rd Pada", "4th Pada"]

def normalize_pada_target(val: str) -> str:
    """
    Take any noisy Info Panel value for 'Pada' and snap it
    to one of the 4 valid canonical options if possible.
    """
    if not val:
        return val

    s = str(val).strip()

    # 1) Already perfect
    if s in _PADA_CANON:
        return s

    # 2) Try to extract "1st/2nd/3rd/4th Pada" from inside junk
    m = re.search(r"\b(1st|2nd|3rd|4th)\s+Pada\b", s, flags=re.IGNORECASE)
    if m:
        ord_raw = m.group(1).lower()
        mapping = {
            "1st": "1st Pada",
            "2nd": "2nd Pada",
            "3rd": "3rd Pada",
            "4th": "4th Pada",
        }
        return mapping.get(ord_raw, s)

    # 3) As a fallback, fuzzy-match the whole string to the 4 options
    best = difflib.get_close_matches(s, _PADA_CANON, n=1, cutoff=0.5)
    if best:
        return best[0]

    # 4) If we really cannot understand it, return original (logs will show it)
    return s
# ---- END PADA TARGET NORMALIZER -------------------------------------------
# ---- Helper: form signature + wait for info panel ----


def _build_form_signature(extracted: dict):
    """Create a compact signature for a form to detect when the same form repeats."""
    if not extracted:
        return None
    for key in ("MBI Code", "App No", "Full Name"):
        if extracted.get(key):
            return str(extracted.get(key))
    try:
        return json.dumps(extracted, sort_keys=True)
    except Exception:
        return str(extracted)


def quick_info_panel_signature_old(mem):
    """
    Fast/cheap form-change check using OLD OCR only (no Paddle).
    Reads only top small area of info panel.
    """
    if "info_panel_region" not in mem:
        return None

    x1, y1, x2, y2 = mem["info_panel_region"]
    y2_small = min(y2, y1 + 170)  # only top portion
    region = (x1, y1, x2, y2_small)

    raw = smart_ocr_text(region) or ""
    raw = raw.replace("\n", " ").strip()

    # Prefer stable IDs if visible
    m = re.search(r"(MBI\s*Code\s*[:\-]?\s*[A-Z]{3}\d{10})", raw, re.I)
    if m:
        return m.group(1).strip()

    m = re.search(r"(App\s*No\s*[:\-]?\s*\d+)", raw, re.I)
    if m:
        return m.group(1).strip()

    return raw[:60] if raw else None

def _grace_wait_for_new_form(mem, last_signature, timeout_seconds=7*60, poll_interval=1.0, stable_hits=2):
    start_mpf_pos = mem.get("start_mpf_button_pos")  # NEW
    
    print("[RECOVERY] Pressing Enter to clear potential Internet Error before grace wait...")
    pyautogui.press('enter')
    safe_sleep(1.5)

    la_pos = mem.get("load_another_form_button_pos")
    flow_region = mem.get("upload_flow_region")
    if flow_region:
        print("[RECOVERY] Scanning for Load Another Form just in case...")
        if wait_for_button_and_click("Load Another Form", tuple(flow_region), timeout=3.0, poll_interval=0.7, click_pos=la_pos):
            print("[RECOVERY] Clicked Load Another Form again during form wait.")
            safe_sleep(2.0)

    remaining = float(timeout_seconds)
    last_seen = None
    hits = 0
    
    blank_page_timer = 40.0  # 40-second countdown for the blank page/internet error check

    while remaining > 0:
        check_pause()
        
        # BLANK PAGE / INTERNET ERROR RECOVERY LOOP
        blank_page_timer -= poll_interval
        if blank_page_timer <= 0:
            if start_mpf_pos:
                print("[RECOVERY] 40s passed with no new form. Pressing Enter to clear Internet Error, then clicking Start MPF...")
                # 1. Press Enter to clear any invisible or visible Internet Error popup
                pyautogui.press('enter')
                safe_sleep(1.0)
                
                # 2. Click Start MPF to reload the form
                click_abs(start_mpf_pos[0], start_mpf_pos[1])
                safe_sleep(2.0)
                
                # 3. Reset the 40s timer to continuously loop this process until the 7 mins are up
                blank_page_timer = 40.0  
            else:
                print("[RECOVERY] 40s passed, but Start MPF position not saved. Resetting timer.")
                blank_page_timer = 40.0

        sig = quick_info_panel_signature_old(mem)

        if sig and (last_signature is None or sig != last_signature):
            if sig == last_seen:
                hits += 1
            else:
                last_seen = sig
                hits = 1

            if hits >= stable_hits:
                return True, sig
        else:
            last_seen = None
            hits = 0

        step = poll_interval if remaining > poll_interval else remaining
        safe_sleep(step)
        remaining -= step

    return False, last_signature

def _wait_for_info_panel(mem, last_signature, form_index,
                         max_wait_first=5.0, max_wait_new=45.0, poll_interval=1.0):
    remaining = float(max_wait_first if form_index == 0 else max_wait_new)

    while remaining > 0:
        check_pause()
        sig = quick_info_panel_signature_old(mem)
        if sig:
            if form_index == 0:
                return True, sig
            if sig != last_signature:
                return True, sig

        step = poll_interval if remaining > poll_interval else remaining
        safe_sleep(step)
        remaining -= step

    return False, last_signature


def _norm_v(v):
    return re.sub(r"\s+", " ", (v or "").strip().lower())

def merge_info_dict(base: dict, incoming: dict) -> dict:
    """
    Merge without duplicates. Never overwrite a good value with junk.
    If both exist:
      - keep longer value if one is substring of the other
      - else keep base and log conflict
    """
    if not incoming:
        return base
    for k, v in incoming.items():
        if not v:
            continue
        if k not in base or not base.get(k):
            base[k] = v
            continue

        a = base.get(k, "")
        if _norm_v(a) == _norm_v(v):
            continue

        # prefer longer if one contains the other
        if _norm_v(a) in _norm_v(v):        
            base[k] = v
        elif _norm_v(v) in _norm_v(a):
            pass
        
            
    return base

def autofill_mode():
    """Autofill one or more forms, then run the new Upload → Screenshot → Next-form loop."""
    global SPEAK_ENABLED

    mem = load_memory()
    if not mem:
        # Briefly allow speech so the user knows it failed immediately
        SPEAK_ENABLED = True
        speak("Memory not found. Run Learning Mode (F2) first.")
        return

    # 🔇 MUTE TTS for the ENTIRE duration of Autofill Mode
    SPEAK_ENABLED = False

    form_index = 0
    last_signature = None

    while True:
        check_pause()

        # wait for info panel to actually show data / new form
        ok, signature = _wait_for_info_panel(mem, last_signature, form_index)
        if not ok:
            print("[INFO] No new forms detected. Waiting 7 minutes, then terminating.")
            _telegram_notify_no_forms("No new forms detected (info panel did not change)")

            resumed, _ = _grace_wait_for_new_form(mem, last_signature, timeout_seconds=7*60)
            if resumed:
                print("[INFO] New form detected. Cancelled termination. Resuming autofill.")
                _telegram_notify_recovery("New form data detected during grace wait. Termination cancelled.")
                continue

            # Restore speech before exiting
            SPEAK_ENABLED = True
            return

        # Now do FULL 3-pass Paddle extraction ONCE
        extracted = read_info_panel_full_before_autofill(mem)
        if not extracted:
            if form_index == 0:
                print("[ERROR] Could not extract data from information panel. Aborting autofill.")
            else:
                print("[INFO] No more forms detected in information panel. Waiting 7 minutes, then terminating.")
                _telegram_notify_no_forms("No more forms detected in info panel (grace wait started)")

                resumed, _ = _grace_wait_for_new_form(mem, last_signature, timeout_seconds=7*60)
                if resumed:
                    print("[INFO] New form detected. Cancelled termination. Resuming autofill.")
                    continue

                # Restore speech before exiting
                SPEAK_ENABLED = True
                return


        if last_signature is not None and signature == last_signature:
            print("[INFO] Same form data detected again after loading. Assuming no new forms are available.")
            print("[INFO] Waiting 7 minutes, then terminating.")
            _telegram_notify_no_forms("Same form detected again (grace wait started)")

            resumed, _ = _grace_wait_for_new_form(mem, last_signature, timeout_seconds=7*60)
            if resumed:
                print("[INFO] New form detected. Cancelled termination. Resuming autofill.")
                continue

            # Restore speech before exiting
            SPEAK_ENABLED = True
            return

        last_signature = signature
        form_index += 1

        CODE_STRICT_FIELDS = {
            "MBI Code", "RAI Code", "PHI Code", "FAI Code", "ECI Code",
        }

        def find_value_for(name):
            if name in extracted and extracted[name]:
                return extracted[name]
            if name in CODE_STRICT_FIELDS or name.strip().lower().endswith("code"):
                return None
            aliases = {
                "sub cast": "Sub Cast",
                "subcast": "Sub Cast",
            }
            alt = aliases.get(name)
            if alt and extracted.get(alt):
                return extracted[alt]
            m = difflib.get_close_matches(name, extracted.keys(), n=1, cutoff=0.65)
            return extracted[m[0]] if m else None

        print(f"\n=== Autofill Mode Activated — Form {form_index} ===")

        cumulative_scroll_est = 0
        failed_fields = []  

        for field in mem.get('fields', []):
            fname = field.get('name')
            ftype = field.get('type')

            global SKIP_ENABLED
            SKIP_ENABLED = True
            try:
                check_pause()

                val = find_value_for(fname)
                if val is None:
                    failed_fields.append(fname)
                    continue

                if field.get('pos'):
                    abs_pos = tuple(field['pos'])
                elif field.get('index') is not None and mem.get('anchor') and mem.get('spacing'):
                    anchor = mem['anchor']
                    spacing = mem['spacing']
                    abs_pos = (anchor[0], int(anchor[1] + field['index'] * spacing - cumulative_scroll_est))
                else:
                    failed_fields.append(fname)
                    continue

                screen_w, screen_h = pyautogui.size()
                attempts = 0
                main_anchor = mem.get('scrollbars', {}).get('main', None)
                while abs_pos[1] > screen_h - 140 and attempts < 12:
                    check_pause()
                    if main_anchor:
                        scroll_at(tuple(main_anchor), -5)
                    else:
                        scroll_at((screen_w // 2, screen_h // 2), -5)
                    abs_pos = (abs_pos[0], abs_pos[1] - 60)
                    cumulative_scroll_est += 60
                    attempts += 1

                try:
                    if ftype == 'typing':
                        click_and_type_abs(abs_pos[0], abs_pos[1], val)

                    elif ftype == 'dropdown':
                        lname = fname.strip().lower()

                        ok = fill_dropdown_by_memory(field, abs_pos, val)

                        if not ok:
                            if lname == "pada":
                                ok = fill_pada_dropdown_strict(field, abs_pos, val)
                            elif lname == "diet":
                                ok = fill_diet_dropdown_strict(field, abs_pos, val)
                            elif lname == "annual income":
                                ok = fill_annual_income_dropdown_strict(field, abs_pos, val)

                        if ok:
                            bump_field_value(fname, val)
                        else:
                            failed_fields.append(fname)

                    elif ftype == 'dob':
                        if not fill_dob_by_memory(field, val):
                            failed_fields.append(fname)
                    else:
                        click_and_type_abs(abs_pos[0], abs_pos[1], val)

                except Exception:
                    failed_fields.append(fname)
                    continue

            except SkipFieldException:
                print(f"[SKIP] User skipped field: {fname}")
                safe_sleep(0.1)
                continue

            finally:
                SKIP_ENABLED = False

            if fname == "Religion":
                if "input_panel_region" in mem and "main" in mem.get("scrollbars", {}):
                    region = tuple(mem["input_panel_region"])
                    anchor = tuple(mem["scrollbars"]["main"])

                    scrolled = scroll_until_disappears(anchor, region, "Religion", next_field="Cast")
                    if scrolled:
                        safe_sleep(1.0) 

            elif fname == "Father Name":
                if "input_panel_region" in mem and "main" in mem.get("scrollbars", {}):
                    region = tuple(mem["input_panel_region"])
                    anchor = tuple(mem["scrollbars"]["main"])
                    scroll_to_end(anchor, region)

            safe_sleep(0.05)

        # Removed the 'SPEAK_ENABLED = True' that was unmuting here
        if failed_fields:
           print(f"[WARNING] Autofill completed with issues for this form. Could not fill: {', '.join(failed_fields)}")

        if not run_upload_and_next_form(mem):
            SPEAK_ENABLED = True
            return

        # After upload + Load Another Form, loop back and try to read a fresh form.



# ---------------- Main loop ----------------
# Start background pause listener thread
listener_thread = threading.Thread(target=pause_listener, daemon=True)
listener_thread.start()
# NEW: start skip listener thread (F5)
skip_thread = threading.Thread(target=skip_listener, daemon=True)
skip_thread.start()
if __name__ == "__main__":
    print("[INIT] Preloading PaddleOCR (info panel models)...")
    try:
        ok = warmup_info_panel_ocr(use_orientation=False)
        print("[INIT] PaddleOCR preload:", "OK" if ok else "FAILED (PaddleOCR None)")
    except Exception as e:
        print("[INIT] PaddleOCR preload failed:", e)

    # UPDATED VOICE AND PRINT PROMPTS
    speak("Bot ready. Press F2 to start Learning Mode. Press F3 for Autofill. Press F4 for Upload Learning. Press F6 for Internet Error Capture.")
    print("F2 -> Learning Mode, F3 -> Autofill Mode, F4 -> Upload-Only Learning, F6 -> Internet Error Only.")

    try:
        while True:
            if keyboard.is_pressed('F2'):
                time.sleep(0.2)
                learning_mode()
                time.sleep(0.5)
            elif keyboard.is_pressed('F3'):
                time.sleep(0.2)
                autofill_mode()
                time.sleep(0.5)
            elif keyboard.is_pressed('F4'):
                time.sleep(0.2)
                upload_learning_mode_only()
                time.sleep(0.5)
            # NEW BLOCK FOR F6
            elif keyboard.is_pressed('F6'):
                time.sleep(0.2)
                capture_error_recovery_buttons()
                time.sleep(0.5)
                
            time.sleep(0.12)
    except KeyboardInterrupt:
        print("Exiting.")
speak("Text to speech initialized.")
system_speak("System voice working correctly.")
