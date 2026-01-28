#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Max Bosselmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# --------------------------------------------------------------------
# This project is based on and inspired by earlier work from:
#
# - Nick Drobchenko (2009) – Gcodetools / Laserengraver
# - hugomatic (2007) – gcode.py
# - Aaron Spike (2005–2007) – cubicsuperpath, bezier utilities, nodes
#
# Parts of the original architecture were rewritten and adapted
# for Inkscape 1.4+, modern Python, and LinuxCNC workflows.
# --------------------------------------------------------------------
"""
Laserengraver Extension for Inkscape 1.4+
Modernized version with modular structure

Based on original Laserengraver v0.01
Migrated to Inkscape 1.x API

Key points in this version:
- Coordinates are exported in **mm**
- SVG Y-axis is flipped using the **viewBox height** so that (0,0) is bottom-left in G-code space
- Curves can be exported either as biarcs (G02/G03) or as G1 polylines
- **FIX:** Now correctly processes Gcodetools-Fill paths (subpaths in groups)
"""

import time
import re
from pathlib import Path

import inkex
from inkex import Style, PathElement, Group, TextElement, Transform
from inkex.paths import CubicSuperPath

from laserengraver_geometry import csp_at_t, biarc_approximation
from laserengraver_gcode import GCodeGenerator
from laserengraver_orientation import OrientationManager


__version__ = "1.0.9"


class LaserEngraver(inkex.EffectExtension):
    """Main extension class for laser engraving G-code generation"""

    def add_arguments(self, pars):
        # File settings
        pars.add_argument("-d", "--directory", type=str, default="c:\\output\\", help="Directory for G-code file")
        pars.add_argument("-f", "--filename", type=str, default="output.nc", help="Output filename")
        pars.add_argument("--add-numeric-suffix-to-filename", type=inkex.Boolean, default=True,
                          help="Add numeric suffix to filename")

        # Laser settings
        pars.add_argument("--engraving-laser-speed", type=int, default=30, help="Speed of laser during engraving")

        # Units
        pars.add_argument("--unit", type=str, default="G21 (All units in mm)", help="Units (G21=mm, G20=inches)")

        # Curve mode
        # polyline  -> use only G1 segments (recommended for smooth preview in LinuxCNC)
        # biarc     -> use G02/G03 where possible
        pars.add_argument("--curve-mode", type=str, default="polyline", help="polyline|biarc")

        # Polyline quality (only used when curve-mode=polyline)
        pars.add_argument("--polyline-segments", type=int, default=24, help="Segments per cubic Bezier")

        # Debug options
        pars.add_argument("--suppress-all-messages", type=inkex.Boolean, default=True,
                          help="Suppress all messages during generation")
        pars.add_argument("--create-log", type=inkex.Boolean, default=False, help="Create log file")
        pars.add_argument("--log-filename", type=str, default="", help="Log filename")
        pars.add_argument("--engraving-draw-calculation-paths", type=inkex.Boolean, default=False,
                          help="Draw calculation paths for debugging")

        # Biarc settings
        pars.add_argument("--biarc-max-split-depth", type=int, default=4, help="Maximum depth for biarc splitting")

        # Tab selection
        pars.add_argument("--active-tab", type=str, default="laser", help="Active tab")

    def __init__(self):
        super().__init__()

        self.orientation_mgr = None
        self.gcode_gen = None

        self.selected_paths = {}
        self.all_paths = {}
        self.layers = []

        self.header = "G90\n"
        self.footer = "G0 X0.0000 Y0.0000\nM05\nM02\n"

        self.tool = {
            "name": "Laser Engraver",
            "id": "Laser_001",
            "diameter": 0.0,
            "penetration_feed": 30,
            "feed": 30,
            "gcode_before_path": "M03",  # Laser ON
            "gcode_after_path": "M05",   # Laser OFF
        }

    def effect(self):
        self._setup_logging()

        if self.options.active_tab not in ["laser", "orientation"]:
            raise inkex.AbortExtension("Please select either 'Laser' or 'Orientation' tab")

        self.orientation_mgr = OrientationManager(self.svg)
        self.gcode_gen = GCodeGenerator(self.options)

        self.tool["penetration_feed"] = self.options.engraving_laser_speed
        self.tool["feed"] = self.options.engraving_laser_speed

        if self.options.active_tab == "orientation":
            self._handle_orientation()
        else:
            self._handle_laser()

    def _handle_orientation(self):
        current_layer = self.svg.get_current_layer()
        if self.orientation_mgr.has_orientation_points(current_layer):
            raise inkex.AbortExtension("Current layer already has orientation points!")
        self.orientation_mgr.create_orientation_points(current_layer, self.options.unit)
        self._log("Orientation points created successfully")

    def _handle_laser(self):
        self._collect_paths()

        # Ensure there are orientation points (needed for consistent scaling/rotation, even if identity)
        found_points = self.orientation_mgr.find_orientation_points()
        if found_points:
            self._log(f"Found orientation points in {len(self.orientation_mgr.orientation_points)} layer(s)")
        else:
            self._log("No orientation points found, creating defaults...")
            current_layer = self.svg.get_current_layer()
            self.orientation_mgr.create_orientation_points(current_layer, self.options.unit)
            # Nochmal suchen nach dem Erstellen
            self.orientation_mgr.find_orientation_points()

        # Wenn etwas ausgewählt ist: nur Auswahl, sonst alles
        paths_to_process = self.selected_paths if self.selected_paths else self.all_paths
        
        if not paths_to_process:
            raise inkex.AbortExtension("No paths to process!")

        total_paths = sum(len(p) for p in paths_to_process.values())
        self._log(f"Processing {total_paths} paths")
        
        gcode = self._generate_gcode(paths_to_process)
        self._export_gcode(gcode)

        if self.options.engraving_draw_calculation_paths:
            self._draw_preview(paths_to_process)

    def _collect_paths(self):
        """
        Sammelt Pfade basierend auf Auswahl:
        - Wenn etwas ausgewählt ist: Nur diese Pfade + Pfade in ausgewählten Gruppen
        - Wenn nichts ausgewählt ist: Alle Pfade im Dokument
        WICHTIG: Filtert nur Orientierungspunkte heraus
        """
        self.layers = list(self.svg.xpath('//svg:g[@inkscape:groupmode="layer"]'))
        if not self.layers:
            self.layers = [self.svg]

        # Sammle ausgewählte Elemente (Pfade UND Gruppen)
        selected_elements = list(self.svg.selection)
        
        if selected_elements:
            self._log(f"Processing selection of {len(selected_elements)} elements")
            
            # Durchsuche ausgewählte Elemente
            for elem in selected_elements:
                layer = self._get_layer(elem)
                
                # Wenn es ein Pfad ist, direkt hinzufügen
                if isinstance(elem, PathElement):
                    if self._is_valid_path(elem):
                        self.selected_paths.setdefault(layer, []).append(elem)
                        self._log(f"  Selected path: {elem.get('id', 'unknown')}")
                
                # Wenn es eine Gruppe ist, alle Pfade darin finden (rekursiv!)
                elif isinstance(elem, Group):
                    group_id = elem.get('id', 'unknown')
                    self._log(f"  Selected group: {group_id}")
                    
                    # Finde alle Pfade in dieser Gruppe (rekursiv)
                    paths_in_group = elem.xpath('.//svg:path', namespaces=inkex.NSS)
                    for path in paths_in_group:
                        if self._is_valid_path(path):
                            self.selected_paths.setdefault(layer, []).append(path)
                            self._log(f"    -> Path in group: {path.get('id', 'unknown')}")
        
        else:
            # Keine Auswahl: Sammle alle Pfade
            self._log("No selection, processing all paths in document")
            for layer in self.layers:
                all_path_elements = layer.xpath('.//svg:path', namespaces=inkex.NSS)
                
                for path in all_path_elements:
                    if self._is_valid_path(path):
                        self.all_paths.setdefault(layer, []).append(path)

        # Statistik
        total_selected = sum(len(p) for p in self.selected_paths.values())
        total_all = sum(len(p) for p in self.all_paths.values())
        
        self._log(f"Found {total_selected} selected paths")
        self._log(f"Found {total_all} total paths")
        
        # Detaillierte Statistik pro Layer
        if self.selected_paths:
            for layer, paths in self.selected_paths.items():
                layer_name = layer.get(inkex.addNS('label', 'inkscape'), 'Unnamed')
                gcodetools_count = sum(1 for p in paths if p.get('gcodetools', ''))
                self._log(f"  Layer '{layer_name}': {len(paths)} paths ({gcodetools_count} Gcodetools)")

    def _is_valid_path(self, path):
        """
        Prüft ob ein Pfad verarbeitet werden soll
        Returns: True wenn der Pfad exportiert werden soll
        """
        # Filtere Orientierungspunkte heraus
        gcodetools_attr = path.get('gcodetools', '')
        if gcodetools_attr and 'orientation' in gcodetools_attr.lower():
            return False
        
        # Überspringe Pfade ohne 'd' Attribut
        if not path.get('d'):
            return False
        
        return True

    def _get_layer(self, element):
        while element is not None:
            if element.get(inkex.addNS('groupmode', 'inkscape')) == 'layer':
                return element
            element = element.getparent()
        return self.svg

    def _generate_gcode(self, paths_dict):
        gcode_lines = []

        gcode_lines.append(self.header.rstrip("\n"))
        if "G21" in self.options.unit:
            gcode_lines.append("G21  ; Units in mm")
        elif "G20" in self.options.unit:
            gcode_lines.append("G20  ; Units in inches")

        gcode_lines.append("(DEBUG: laserengraver.py v1.0.8 - Open arrows on every subpath - 2026-01-27)")

        for layer, paths in paths_dict.items():
            layer_name = layer.get(inkex.addNS('label', 'inkscape'), 'Unnamed')
            self._log(f"Processing layer: {layer_name}")
            layer_transform = self.orientation_mgr.get_transform_for_layer(layer)

            for path in paths:
                path_id = path.get('id', 'unknown')
                path_d = path.get('d')
                if not path_d:
                    self._log(f"  Skipping path {path_id}: no 'd' attribute")
                    continue

                self._log(f"  Processing path: {path_id}")

                csp = CubicSuperPath(path_d)

                # Apply element transform into document coordinates
                csp = csp.transform(path.composed_transform())

                # Apply orientation transform (scale/rotate/translate into gcode space)
                if layer_transform:
                    csp = csp.transform(layer_transform)

                gcode_lines.append(self._path_to_gcode(csp))

        gcode_lines.append(self.footer.rstrip("\n"))
        return "\n".join(gcode_lines) + "\n"

    def _path_to_gcode(self, csp):
        gcode = []

        # px per mm in current document units
        px_per_mm = float(self.svg.unittouu('1mm'))

        # viewBox is [min_x, min_y, width, height] in px
        viewbox = self.svg.get_viewbox()
        page_height_px = float(viewbox[3])

        curve_mode = (self.options.curve_mode or "polyline").strip().lower()
        poly_segments = max(2, int(self.options.polyline_segments))

        for subpath in csp:
            if len(subpath) < 2:
                continue

            # Move to start (subpath[0][1] is the node point)
            start = subpath[0][1]
            x0 = start[0] / px_per_mm
            y0 = (page_height_px - start[1]) / px_per_mm

            gcode.append(f"G0 X{x0:.4f} Y{y0:.4f}")
            gcode.append(self.tool["gcode_before_path"])

            for i in range(1, len(subpath)):
                sp1 = subpath[i - 1]
                sp2 = subpath[i]

                if curve_mode == "biarc":
                    biarcs = biarc_approximation(sp1, sp2, max_depth=self.options.biarc_max_split_depth)
                    for arc in biarcs:
                        if arc['type'] == 'line':
                            end = arc['end']
                            x = end[0] / px_per_mm
                            y = (page_height_px - end[1]) / px_per_mm
                            gcode.append(f"G1 X{x:.4f} Y{y:.4f} F{self.tool['feed']}")
                        else:
                            end = arc['end']
                            center = arc['center']
                            start_arc = arc['start']

                            x = end[0] / px_per_mm
                            y = (page_height_px - end[1]) / px_per_mm

                            i_off = (center[0] - start_arc[0]) / px_per_mm
                            # J needs inverted because we flipped Y via (page_height - y)
                            j_off = -((center[1] - start_arc[1]) / px_per_mm)

                            direction = "G02" if arc['angle'] < 0 else "G03"
                            gcode.append(f"{direction} X{x:.4f} Y{y:.4f} I{i_off:.4f} J{j_off:.4f}")
                else:
                    # polyline: sample the cubic segment at t in [0..1]
                    # skip t=0 because we're already at start
                    for s in range(1, poly_segments + 1):
                        t = s / poly_segments
                        p = csp_at_t(sp1, sp2, t)
                        x = p[0] / px_per_mm
                        y = (page_height_px - p[1]) / px_per_mm
                        gcode.append(f"G1 X{x:.4f} Y{y:.4f} F{self.tool['feed']}")
            gcode.append(self.tool["gcode_after_path"])

        return "\n".join(gcode)

    def _export_gcode(self, gcode):
        directory = Path(self.options.directory)
        if not directory.exists():
            raise inkex.AbortExtension(f"Directory does not exist: {directory}")

        filename = self.options.filename
        if self.options.add_numeric_suffix_to_filename:
            filename = self._add_numeric_suffix(directory, filename)

        output_path = directory / filename
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(gcode)

        self._log(f"G-code written to: {output_path}")

    def _add_numeric_suffix(self, directory, filename):
        path = Path(filename)
        stem = path.stem
        suffix = path.suffix

        max_num = 0
        pattern = re.compile(rf"^{re.escape(stem)}_(\d+){re.escape(suffix)}$")
        for file in directory.iterdir():
            m = pattern.match(file.name)
            if m:
                max_num = max(max_num, int(m.group(1)))

        return f"{stem}_{max_num + 1:04d}{suffix}"

    def _draw_preview(self, paths_dict):
        """
        Zeichnet eine Preview der exportierten Pfade mit Richtungspfeilen
        Die Preview wird 100mm über dem Original platziert
        Pfeile werden an JEDEM Subpath gezeichnet (inkl. Fülllinien)
        """
        # Erstelle oder finde defs Element
        defs = self.svg.defs
        if defs is None:
            defs = self.svg.getElement('//svg:defs')
        if defs is None:
            defs = inkex.Defs()
            self.svg.append(defs)
        
        # Erstelle Pfeil-Marker wenn noch nicht vorhanden
        marker_id = 'LaserPreviewArrow'
        
        # Prüfe ob Marker bereits existiert
        marker_exists = False
        for elem in defs:
            if elem.get('id') == marker_id:
                marker_exists = True
                break
        
        if not marker_exists:
            marker = inkex.Marker()
            marker.set('id', marker_id)
            marker.set('orient', 'auto')
            marker.set('refX', '5')  # Pfeilspitze bei x=5
            marker.set('refY', '5')  # Zentriert bei y=5
            marker.set('style', 'overflow:visible')
            marker.set('markerWidth', '6')
            marker.set('markerHeight', '6')
            marker.set('viewBox', '0 0 10 10')
            
            # Geöffneter Pfeil (wie >) - zwei Linien im V-Form
            arrow_path = inkex.PathElement()
            arrow_path.set('d', 'M 2,2 L 8,5 L 2,8')  # V-Form nach rechts
            arrow_path.style = {
                'fill': 'none',           # Kein Füllen!
                'stroke': '#E0BC00',      # Türkis/Cyan Farbe
                'stroke-width': '1',      # Dicke Linie
                'stroke-linecap': 'round',
                'stroke-linejoin': 'round'
            }
            marker.append(arrow_path)
            defs.append(marker)
        
        # Erstelle Preview-Gruppe
        preview_group = Group()
        preview_group.set('id', 'laserengraver_gcode_preview')
        preview_group.label = 'G-Code Preview'
        
        current_layer = self.svg.get_current_layer()
        current_layer.append(preview_group)
        
        # Berechne Offset: 100mm nach oben
        px_per_mm = float(self.svg.unittouu('1mm'))
        offset_y = -100 * px_per_mm  # 100mm nach oben (negativ in SVG-Koordinaten)
        
        # Erstelle Beschriftungs-Text
        text_elem = TextElement()
        text_elem.set('x', str(10 * px_per_mm))
        text_elem.set('y', str(offset_y - 10 * px_per_mm))
        text_elem.style = {
            'font-size': '8px',
            'font-family': 'sans-serif',
            'fill': '#7DF9FF',  # Gleiche Farbe wie Pfeile
            'font-weight': 'bold'
        }
        text_elem.text = 'G-Code Preview (Laser Path with Direction Arrows)'
        preview_group.append(text_elem)
        
        viewbox = self.svg.get_viewbox()
        page_height_px = float(viewbox[3])
        
        for layer, paths in paths_dict.items():
            layer_transform = self.orientation_mgr.get_transform_for_layer(layer)
            
            for path in paths:
                path_d = path.get('d')
                if not path_d:
                    continue
                
                # Parse und transformiere Pfad
                csp = CubicSuperPath(path_d)
                csp = csp.transform(path.composed_transform())
                
                if layer_transform:
                    csp = csp.transform(layer_transform)
                
                # WICHTIG: Für jeden Subpath einen separaten Preview-Pfad erstellen!
                # Das stellt sicher, dass jede Fülllinie ihren eigenen Pfeil bekommt
                for subpath in csp:
                    if len(subpath) < 2:
                        continue
                    
                    # Erstelle neuen CSP mit nur diesem Subpath
                    # subpath ist bereits eine Liste von Punkten, also brauchen wir nur [subpath]
                    single_subpath_csp = CubicSuperPath([subpath])
                    
                    # Verschiebe Preview nach oben
                    preview_csp = single_subpath_csp.transform(Transform(translate=(0, offset_y)))
                    
                    # Erstelle Preview-Pfad mit Pfeil am Ende
                    preview_path = PathElement()
                    preview_path.set('d', str(preview_csp))
                    preview_path.style = Style({
                        'stroke': '#7DF9FF',       # Türkis/Cyan
                        'stroke-width': str(0.5),  # Dünnere Linie
                        'fill': 'none',
                        'opacity': '0.9',
                        'marker-end': f'url(#{marker_id})'  # Pfeil am Ende!
                    })
                    preview_group.append(preview_path)

    def _setup_logging(self):
        if self.options.create_log and self.options.log_filename:
            log_path = Path(self.options.log_filename)
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write("Laserengraver Log\n")
                f.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Version: {__version__}\n")
                f.write("-" * 50 + "\n\n")

    def _log(self, message):
        if self.options.create_log and self.options.log_filename:
            try:
                with open(self.options.log_filename, 'a', encoding='utf-8') as f:
                    f.write(f"[{time.strftime('%H:%M:%S')}] {message}\n")
            except Exception:
                pass
        if not self.options.suppress_all_messages:
            print(message)


if __name__ == '__main__':
    LaserEngraver().run()
