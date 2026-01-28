# Laserengraver - Inkscape Extension for G-code Export

This project is a custom **Inkscape extension** for generating **G-code** from SVG paths, primarily intended for **laser engraving and CNC workflows**.

It is based on the original *Laserengraver / Gcodetools* concept, but modernized and extended to work reliably with **Inkscape 1.4+**, LinuxCNC, and similar controllers.

---

<img width="589" height="789" alt="Image" src="https://github.com/user-attachments/assets/8eebd935-91ab-4f52-951c-826c2d719156" />

---

## Features

- Export SVG paths directly to **G-code (mm or inch)**
- Correct **Y-axis handling** (SVG top-left → CNC bottom-left)
- Supports **orientation points** (compatible with Gcodetools logic)
- Two curve modes:
  - **Polyline mode (G1 only)** – smooth preview & robust execution
  - **Biarc mode (G02/G03)** – smaller G-code where supported
- Handles **subpaths** correctly (including fill / hatch lines)
- Optional **preview output** inside Inkscape
- Designed for **LinuxCNC**, but controller-agnostic

---

## Installation

1. Copy all files into your Inkscape extensions directory  
   (e.g. `~/.config/inkscape/extensions/`)

2. Files included:
   - `laserengraver.py`
   - `laserengraver.inx`
   - `laserengraver_geometry.py`
   - `laserengraver_orientation.py`
   - `laserengraver_gcode.py`
   - `Readme.md`

3. Restart Inkscape

The extension will appear under:

Extensions -> Laserengraver 

---

## Workflow Overview

1. Create or import SVG geometry in Inkscape
2. Transform your Text or Graphic into a path 
3. (Optional) Use **Gcodetools** to create areafills
4. Select paths you wich to transform to gcode (or leave unselected to process all)
5. Run **Laserengraver**
6. Load the generated `.nc`, `.ngc` or `.gcode` file into your CNC / laser controller

---

## Settings

- **Curve mode**
  - `polyline` (recommended): all curves converted to G1 segments
  - `biarc`: uses G02/G03 arcs where possible
- **Polyline resolution**: segments per Bezier curve
- **Units**: mm (G21) or inch (G20)
- **Laser speed**: feed rate during engraving

---

## Notes

- This extension focuses on **geometry correctness and predictability**
- It intentionally avoids machine-specific G-code
- Z-axis handling is omitted by design (laser use-case)

---

## About the Code

This project was developed by a non-programmer with a strong practical CNC background.  
Large parts of the code were written with the assistance of **AI tools**, refined and tested in real-world engraving workflows.

The goal is **usability and clarity**, not academic perfection.

---

## License

MIT License – see the `LICENSE` file for details.

---

## Motivation

This project grew out of practical needs in a small woodworking and manufacturing workshop that values **open-source software**, transparency, and long-term maintainability.

If it helps others: even better.

---

## Credits & Acknowledgements

This project builds upon ideas and code originally developed in the
Inkscape Gcodetools / Laserengraver ecosystem.

Original contributors include:

- **Nick Drobchenko** (2009) – Laserengraver / Gcodetools foundation
- **hugomatic** (2007) – gcode.py concepts
- **Aaron Spike** (2005–2007) – cubicsuperpath and Bezier utilities

The current version was heavily rewritten, modularized and adapted
for modern Inkscape versions (1.4+), LinuxCNC, and predictable CNC
workflows.

