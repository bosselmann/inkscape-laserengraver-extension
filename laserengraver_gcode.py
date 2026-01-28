#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copyright (C) 2026 Max Bosselmann
#
# See the LICENSE file for full license text.

"""
G-code generation utilities for Laserengraver
"""


class GCodeGenerator:
    """Generates G-code from geometric data"""
    
    def __init__(self, options):
        self.options = options
        self.current_x = None
        self.current_y = None
        self.laser_on = False
    
    def format_coordinate(self, value, decimals=4):
        """Format a coordinate value"""
        formatted = f"{value:.{decimals}f}".rstrip('0').rstrip('.')
        return formatted if formatted else "0"
    
    def move_to(self, x, y, rapid=True):
        """
        Generate G-code to move to position
        
        Args:
            x, y: Target coordinates
            rapid: If True, use G0 (rapid), else G1 (linear)
        
        Returns:
            G-code string
        """
        code = "G0" if rapid else "G1"
        
        parts = [code]
        
        # Only include coordinates that changed
        if self.current_x is None or abs(x - self.current_x) > 1e-6:
            parts.append(f"X{self.format_coordinate(x)}")
            self.current_x = x
        
        if self.current_y is None or abs(y - self.current_y) > 1e-6:
            parts.append(f"Y{self.format_coordinate(y)}")
            self.current_y = y
        
        return " ".join(parts)
    
    def line_to(self, x, y, feed=None):
        """
        Generate G-code for linear move
        
        Args:
            x, y: Target coordinates
            feed: Feed rate (optional)
        
        Returns:
            G-code string
        """
        code = self.move_to(x, y, rapid=False)
        
        if feed is not None:
            code += f" F{self.format_coordinate(feed, 1)}"
        
        return code
    
    def arc_to(self, x, y, i, j, clockwise=False, feed=None):
        """
        Generate G-code for arc move
        
        Args:
            x, y: Target coordinates
            i, j: Offset to arc center from current position
            clockwise: Direction of arc
            feed: Feed rate (optional)
        
        Returns:
            G-code string
        """
        code = "G02" if clockwise else "G03"
        
        parts = [code]
        
        # Target position
        if self.current_x is None or abs(x - self.current_x) > 1e-6:
            parts.append(f"X{self.format_coordinate(x)}")
            self.current_x = x
        
        if self.current_y is None or abs(y - self.current_y) > 1e-6:
            parts.append(f"Y{self.format_coordinate(y)}")
            self.current_y = y
        
        # Arc center offset
        parts.append(f"I{self.format_coordinate(i)}")
        parts.append(f"J{self.format_coordinate(j)}")
        
        # Feed rate
        if feed is not None:
            parts.append(f"F{self.format_coordinate(feed, 1)}")
        
        return " ".join(parts)
    
    def laser_on(self, power=None):
        """
        Generate G-code to turn laser on
        
        Args:
            power: Laser power (0-100), optional
        
        Returns:
            G-code string
        """
        if power is not None:
            # M3 S[power] for spindle/laser with power control
            return f"M03 S{int(power)}"
        else:
            # M3 for simple on/off
            return "M03"
    
    def laser_off(self):
        """Generate G-code to turn laser off"""
        return "M05"
    
    def dwell(self, seconds):
        """
        Generate G-code for dwell (pause)
        
        Args:
            seconds: Dwell time in seconds
        
        Returns:
            G-code string
        """
        return f"G4 P{self.format_coordinate(seconds, 2)}"
    
    def comment(self, text):
        """
        Generate G-code comment
        
        Args:
            text: Comment text
        
        Returns:
            G-code string
        """
        # Use semicolon for comments (most common)
        return f"; {text}"
    
    def set_feed_rate(self, feed):
        """
        Generate G-code to set feed rate
        
        Args:
            feed: Feed rate
        
        Returns:
            G-code string
        """
        return f"F{self.format_coordinate(feed, 1)}"
    
    def set_units_mm(self):
        """Generate G-code to set units to millimeters"""
        return "G21"
    
    def set_units_inches(self):
        """Generate G-code to set units to inches"""
        return "G20"
    
    def set_absolute_mode(self):
        """Generate G-code to set absolute positioning"""
        return "G90"
    
    def set_relative_mode(self):
        """Generate G-code to set relative positioning"""
        return "G91"
    
    def home(self, axes="XY"):
        """
        Generate G-code to home axes
        
        Args:
            axes: String of axes to home (e.g., "XY", "Z")
        
        Returns:
            G-code string
        """
        return f"G28 {' '.join(axes)}"
    
    def program_end(self):
        """Generate G-code for program end"""
        return "M02"
    
    def program_stop(self):
        """Generate G-code for program stop (optional stop)"""
        return "M00"


class GCodeFormatter:
    """Formats and optimizes G-code output"""
    
    def __init__(self):
        self.lines = []
    
    def add_line(self, line):
        """Add a line of G-code"""
        if line:
            self.lines.append(line)
    
    def add_comment(self, comment):
        """Add a comment line"""
        self.lines.append(f"; {comment}")
    
    def add_blank_line(self):
        """Add a blank line for readability"""
        self.lines.append("")
    
    def optimize(self):
        """
        Optimize G-code by removing redundant commands
        Returns optimized line list
        """
        optimized = []
        last_command = None
        
        for line in self.lines:
            # Skip empty lines at start
            if not optimized and not line.strip():
                continue
            
            # Skip duplicate comments
            if line.startswith(';'):
                if line != last_command:
                    optimized.append(line)
                last_command = line
                continue
            
            # Remove redundant mode changes
            if line in ['G90', 'G91', 'G21', 'G20']:
                if line != last_command:
                    optimized.append(line)
                last_command = line
                continue
            
            optimized.append(line)
            last_command = line
        
        return optimized
    
    def to_string(self, optimize=True):
        """
        Convert to G-code string
        
        Args:
            optimize: Whether to optimize before output
        
        Returns:
            G-code string
        """
        lines = self.optimize() if optimize else self.lines
        return "\n".join(lines)
    
    def save(self, filename, optimize=True):
        """
        Save G-code to file
        
        Args:
            filename: Output filename
            optimize: Whether to optimize before saving
        """
        with open(filename, 'w') as f:
            f.write(self.to_string(optimize=optimize))
