# MPF Autofill Automation – README

## 🚀 Overview
The MPF Autofill Automation Project is a fully automated system designed to read member details from the left-side Info Panel of the MPF (7.3) software and accurately autofill the right-side form fields — including text fields, dropdowns, DOB, scrollable lists, and code fields like MBI/RAI/ECI.

It uses advanced OCR, multi-pass reasoning, fuzzy matching, predictive dropdown selection, and hardware-level scrolling.

## 🧩 Project Structure
```
MPF_Autofill_Project/
├── MPF_BOT_V7_3.py
├── smart_text_reader.py
├── smart_text_reader_twin.py
├── dropdown_reasoner.py
├── dropdown_data.py
├── cast_data.py
├── subcast_data.py
├── education_data.py
├── education_normalizer_guard.py
├── heavy_dropdown_guard.py
├── reverse_precise_tracker.py
├── info_normalizer.py
├── reasoning_core.py
├── reasoning_meta.py
├── reasoning_profile.json
├── prediction_layer.py
├── prediction_memory.py
├── prediction_memory.json
├── bot_memory.json
└── README.md
```

## 📌 Key Features
- Learning Mode (F2)
- Autofill Mode (F3)
- Skip Field (F5)
- Pause/Resume (F9)
- Multi-pass OCR
- Dropdown reasoning + prediction
- Reverse precise tracking
- Heavy dropdown manager
- Info-panel normalization
- Code-field repair (ECI, MBI, RAI, PHI)
- Stable Annual Income resolver
- Micro-verification clicks
- Multi-form upload flow support

## 📞 Support
If you need improvements, debugging, UI design, or new modules, just ask!
