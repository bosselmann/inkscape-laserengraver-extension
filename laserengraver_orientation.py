"""
Orientation point management for Laserengraver
Handles coordinate transformation between Inkscape and G-code space
"""

import inkex
from inkex import Transform, PathElement, TextElement, Group
from lxml import etree


class OrientationManager:
    """Manages orientation points and coordinate transformations"""
    
    def __init__(self, svg):
        self.svg = svg
        self.orientation_points = {}
        self.transforms = {}
    
    def find_orientation_points(self):
        """
        Find all orientation point groups in the document
        Returns True if found, False otherwise
        """
        # Clear previous results
        self.orientation_points.clear()
        
        # Search for Gcodetools orientation groups with proper namespace
        groups = self.svg.xpath('//svg:g[@gcodetools="Gcodetools orientation group"]', namespaces=inkex.NSS)
        
        if not groups:
            # Fallback: search for any group with "orientation" in gcodetools attribute
            all_groups = self.svg.xpath('//svg:g[@gcodetools]', namespaces=inkex.NSS)
            groups = [g for g in all_groups if 'orientation' in g.get('gcodetools', '').lower()]
        
        for group in groups:
            layer = self._get_layer(group)
            points = self._parse_orientation_group(group)
            
            if points:
                if layer not in self.orientation_points:
                    self.orientation_points[layer] = []
                self.orientation_points[layer].append(points)
        
        return len(self.orientation_points) > 0
    
    def has_orientation_points(self, layer):
        """Check if a layer has orientation points"""
        self.find_orientation_points()
        return layer in self.orientation_points
    
    def create_orientation_points(self, layer, unit="G21 (All units in mm)"):
        """
        Create orientation points on the specified layer
        
        Args:
            layer: SVG layer element
            unit: "G21 (All units in mm)" for mm or "G20 (All units in inches)" for inches
        """
        # Create orientation group
        orient_group = Group()
        orient_group.set('gcodetools', 'Gcodetools orientation group')
        orient_group.label = 'Orientation Points'
        layer.append(orient_group)
        
        # Get document dimensions
        doc_width = self.svg.viewport_width
        doc_height = self.svg.viewport_height
        
        # Define orientation points based on unit
        if "G21" in unit:  # mm
            # 100mm spacing
            points = [
                [0, 0, 0],
                [100, 0, 0]
            ]
            scale = self.svg.unittouu('1mm')
        else:  # G20 - inches
            # 5 inch spacing
            points = [
                [0, 0, 0],
                [5, 0, 0]
            ]
            scale = self.svg.unittouu('1in')
        
        # Create point groups
        for i, point in enumerate(points):
            self._create_orientation_point(
                orient_group,
                point,
                scale,
                doc_height
            )
    
    def _create_orientation_point(self, parent_group, point, scale, doc_height):
        """Create a single orientation point marker"""
        # Calculate position
        x_pos = point[0] * scale
        y_pos = doc_height - (point[1] * scale)  # Flip Y
        
        # Create point group
        point_group = Group()
        point_group.set('gcodetools', 'Gcodetools orientation point (2 points)')
        parent_group.append(point_group)
        
        # Create arrow marker
        arrow_path = PathElement()
        arrow_path.set('gcodetools', 'Gcodetools orientation point arrow')
        arrow_path.style = {
            'stroke': 'none',
            'fill': '#000000'
        }
        
        # Arrow shape (pointing down-right)
        arrow_d = (
            f"m {x_pos},{y_pos} "
            "2.9375,-6.34375 "
            "0.8125,1.90625 "
            "6.84375,-6.84375 "
            "0.6875,0.6875 "
            "-6.84375,6.84375 "
            "1.90625,0.8125 z"
        )
        arrow_path.set('d', arrow_d)
        point_group.append(arrow_path)
        
        # Create text label
        text = TextElement()
        text.set('gcodetools', 'Gcodetools orientation point text')
        text.set('x', str(x_pos + 10))
        text.set('y', str(y_pos - 10))
        text.style = {
            'font-size': '10px',
            'font-family': 'sans-serif',
            'fill': '#000000'
        }
        text.set(inkex.addNS('space', 'xml'), 'preserve')
        text.text = f"({point[0]}; {point[1]}; {point[2]})"
        point_group.append(text)
    
    def _parse_orientation_group(self, group):
        """
        Parse an orientation group to extract point coordinates
        Returns list of [[svg_x, svg_y], [gcode_x, gcode_y, gcode_z]]
        """
        points = []
        
        # Find point subgroups with proper namespace
        point_groups = group.xpath(
            './/svg:g[@gcodetools="Gcodetools orientation point (2 points)" or '
            '@gcodetools="Gcodetools orientation point (3 points)"]',
            namespaces=inkex.NSS
        )
        
        for pg in point_groups:
            point = self._parse_point_group(pg)
            if point:
                points.append(point)
        
        # Validate: need 2 or 3 points
        if len(points) in [2, 3]:
            return points
        return None
    
    def _parse_point_group(self, group):
        """
        Determine orientation point position robustly.
        SVG position is the center of the orientation group.
        G-code position is parsed from the orientation text '(x; y; z)'.
        """

        # --- SVG position (document coordinates) ---
        bbox = group.bounding_box()
        if bbox is None:
            return None

        cx = (bbox.left + bbox.right) / 2.0
        cy = (bbox.top + bbox.bottom) / 2.0

        transform = group.composed_transform()
        svg_x, svg_y = transform.apply_to_point((cx, cy))

        svg_pos = [svg_x, svg_y]

        # --- G-code target from text ---
        text_el = group.xpath(
            './/svg:text[@gcodetools="Gcodetools orientation point text"]',
            namespaces=inkex.NSS
        )
        if not text_el:
            return None

        txt = text_el[0].text
        if not txt:
            return None

        try:
            # Expected format: "(x; y; z)"
            nums = txt.strip("()").split(";")
            gcode_pos = [float(nums[0]), float(nums[1]), float(nums[2])]
        except Exception:
            return None

        return (svg_pos, gcode_pos)


    
    def get_transform_for_layer(self, layer):
        """
        Get transformation matrix for a layer
        Returns Transform object or None
        """
        if layer in self.transforms:
            return self.transforms[layer]
        
        # Find orientation points for this layer or parent layers
        points = None
        current = layer
        
        while current is not None:
            if current in self.orientation_points:
                points = self.orientation_points[current][0]
                break
            current = self._get_parent_layer(current)
        
        if not points or len(points) < 2:
            return None
        
        # Calculate transformation matrix
        # This maps from SVG coordinates to G-code coordinates
        
        # Get two points
        svg1, gcode1 = points[0]
        svg2, gcode2 = points[1]
        
        # Calculate scale and rotation
        svg_dx = svg2[0] - svg1[0]
        svg_dy = svg2[1] - svg1[1]
        gcode_dx = gcode2[0] - gcode1[0]
        gcode_dy = gcode2[1] - gcode1[1]
        
        svg_length = (svg_dx**2 + svg_dy**2)**0.5
        gcode_length = (gcode_dx**2 + gcode_dy**2)**0.5
        
        if svg_length < 1e-6:
            return None
        
        scale = gcode_length / svg_length
        
        # Calculate rotation
        import math
        svg_angle = math.atan2(svg_dy, svg_dx)
        gcode_angle = math.atan2(gcode_dy, gcode_dx)
        rotation = gcode_angle - svg_angle
        
        # Create transform: translate to origin, scale, rotate, translate back
        transform = Transform()
        transform.add_translate(-svg1[0], -svg1[1])
        transform.add_scale(scale, scale)  # Do not Flip Y axis
        transform.add_rotate(math.degrees(rotation))
        transform.add_translate(gcode1[0], gcode1[1])
        
        self.transforms[layer] = transform
        return transform
    
    def _get_layer(self, element):
        """Get the layer containing an element"""
        while element is not None:
            if element.get(inkex.addNS('groupmode', 'inkscape')) == 'layer':
                return element
            element = element.getparent()
        return self.svg
    
    def _get_parent_layer(self, layer):
        """Get the parent layer of a layer"""
        parent = layer.getparent()
        while parent is not None:
            if parent.get(inkex.addNS('groupmode', 'inkscape')) == 'layer':
                return parent
            parent = parent.getparent()
        return None