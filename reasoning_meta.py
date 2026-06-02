# reasoning_meta.py
"""
Offline meta-reasoner for dropdown reasoning.

Reads debug_logs/reasoning_*.txt and builds a per-field profile:
    - min_score_ok:  conservative lower bound from successful selections
    - ambiguity_margin: small fixed margin (can be tweaked later)

Run manually after some test runs:
    python reasoning_meta.py

It will write reasoning_profile.json.
"""

import os
import re
import json
from collections import defaultdict

DEBUG_DIR = "debug_logs"
OUT_FILE = "reasoning_profile.json"

# Regexes matching your log format from dropdown_reasoner._log_reasoning
FIELD_RE = re.compile(r"^Field:\s*(.+)$")
STATUS_RE = re.compile(r"^Status:\s*(.+)$")
CONF_RE = re.compile(r"^Confidence:\s*([0-9.]+)")

def parse_logs():
    stats = defaultdict(lambda: {
        "ok_confidences": [],
        "no_match": 0,
        "ambiguous": 0,
        "total": 0,
    })

    if not os.path.isdir(DEBUG_DIR):
        print(f"No {DEBUG_DIR}/ directory found.")
        return stats

    for fname in os.listdir(DEBUG_DIR):
        if not fname.startswith("reasoning_") or not fname.endswith(".txt"):
            continue
        path = os.path.join(DEBUG_DIR, fname)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            current_field = None
            current_status = None
            current_conf = None

            for line in f:
                line = line.rstrip("\n")
                m_field = FIELD_RE.match(line)
                if m_field:
                    current_field = m_field.group(1).strip()
                    current_status = None
                    current_conf = None
                    continue

                m_status = STATUS_RE.match(line)
                if m_status:
                    current_status = m_status.group(1).strip().lower()
                    continue

                m_conf = CONF_RE.match(line)
                if m_conf:
                    try:
                        current_conf = float(m_conf.group(1))
                    except ValueError:
                        current_conf = None
                    # when we see confidence, we consider this snapshot complete
                    if current_field:
                        key = current_field.strip().lower()
                        s = stats[key]
                        s["total"] += 1
                        if current_status == "ok" and current_conf is not None:
                            s["ok_confidences"].append(current_conf)
                        elif current_status == "no_match":
                            s["no_match"] += 1
                        elif current_status == "ambiguous":
                            s["ambiguous"] += 1
                    continue

    return stats


def build_profile(stats):
    profile = {}
    for field_key, s in stats.items():
        ok_confs = s["ok_confidences"]
        if not ok_confs:
            continue

        # Simple heuristic:
        # - min_score_ok: slightly below the min observed confidence
        # - ambiguity_margin: small, fixed default (safe)
        min_conf = min(ok_confs)
        avg_conf = sum(ok_confs) / len(ok_confs)

        # Be conservative: don't go below 0.45 even if logs say so
        suggested_min = max(0.45, min_conf - 0.03)

        profile[field_key] = {
            "min_score_ok": round(suggested_min, 3),
            "ambiguity_margin": 0.04,   # you can hand-tune this later per field if needed
            "summary": {
                "avg_conf_ok": round(avg_conf, 3),
                "min_conf_ok": round(min_conf, 3),
                "no_match": s["no_match"],
                "ambiguous": s["ambiguous"],
                "total": s["total"],
            }
        }
    return profile


def main():
    stats = parse_logs()
    profile = build_profile(stats)

    if not profile:
        print("No data extracted from reasoning logs.")
        return

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

    print(f"Wrote {OUT_FILE} with per-field tuning:")
    for k, v in profile.items():
        print(f"  {k}: min_score_ok={v['min_score_ok']}, ambiguity_margin={v['ambiguity_margin']}")


if __name__ == "__main__":
    main()
