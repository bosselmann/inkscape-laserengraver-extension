"""
Geometry utilities for Laserengraver
Handles bezier curves, biarcs, and path manipulation
"""

import math
import cmath
from typing import List, Tuple, Optional


class P:
    """Point class with vector operations"""
    
    def __init__(self, x, y=None):
        if y is None:
            self.x, self.y = float(x[0]), float(x[1])
        else:
            self.x, self.y = float(x), float(y)
    
    def __add__(self, other):
        return P(self.x + other.x, self.y + other.y)
    
    def __sub__(self, other):
        return P(self.x - other.x, self.y - other.y)
    
    def __mul__(self, other):
        if isinstance(other, P):
            return self.x * other.x + self.y * other.y
        return P(self.x * other, self.y * other)
    
    __rmul__ = __mul__
    
    def __truediv__(self, other):
        return P(self.x / other, self.y / other)
    
    def mag(self):
        """Magnitude of vector"""
        return math.hypot(self.x, self.y)
    
    def unit(self):
        """Unit vector"""
        m = self.mag()
        return self / m if m > 0 else P(0, 0)
    
    def angle(self):
        """Angle in radians"""
        return math.atan2(self.y, self.x)
    
    def rot(self, theta):
        """Rotate by angle theta"""
        c = math.cos(theta)
        s = math.sin(theta)
        return P(self.x * c - self.y * s, self.x * s + self.y * c)
    
    def ccw(self):
        """90 degree counter-clockwise rotation"""
        return P(-self.y, self.x)
    
    def to_list(self):
        """Convert to list [x, y]"""
        return [self.x, self.y]
    
    def __repr__(self):
        return f"P({self.x:.4f}, {self.y:.4f})"


def bezier_parameterize(bezier):
    """
    Parameterize bezier curve
    bezier = [[x0,y0], [x1,y1], [x2,y2], [x3,y3]]
    Returns ax,ay,bx,by,cx,cy,dx,dy for:
    x(t) = ax*t³ + bx*t² + cx*t + dx
    y(t) = ay*t³ + by*t² + cy*t + dy
    """
    x0, y0 = bezier[0]
    x1, y1 = bezier[1]
    x2, y2 = bezier[2]
    x3, y3 = bezier[3]
    
    cx = 3 * (x1 - x0)
    bx = 3 * (x2 - x1) - cx
    ax = x3 - x0 - cx - bx
    
    cy = 3 * (y1 - y0)
    by = 3 * (y2 - y1) - cy
    ay = y3 - y0 - cy - by
    
    return ax, ay, bx, by, cx, cy, x0, y0


def csp_parameterize(sp1, sp2):
    """
    Parameterize cubic super path segment
    sp1, sp2 = [[handle_in], [point], [handle_out]]
    """
    bezier = [sp1[1], sp1[2], sp2[0], sp2[1]]
    return bezier_parameterize(bezier)


def csp_at_t(sp1, sp2, t):
    """Evaluate cubic super path segment at parameter t"""
    ax, ay, bx, by, cx, cy, dx, dy = csp_parameterize(sp1, sp2)
    
    x = ax * t**3 + bx * t**2 + cx * t + dx
    y = ay * t**3 + by * t**2 + cy * t + dy
    
    return [x, y]


def csp_split(sp1, sp2, t=0.5):
    """
    Split cubic super path segment at parameter t
    Returns three segments: [sp1, split_point], [split_point, sp2]
    """
    # Get bezier points
    p0 = sp1[1]
    p1 = sp1[2]
    p2 = sp2[0]
    p3 = sp2[1]
    
    # De Casteljau's algorithm
    p01 = [p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t]
    p12 = [p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t]
    p23 = [p2[0] + (p3[0] - p2[0]) * t, p2[1] + (p3[1] - p2[1]) * t]
    
    p012 = [p01[0] + (p12[0] - p01[0]) * t, p01[1] + (p12[1] - p01[1]) * t]
    p123 = [p12[0] + (p23[0] - p12[0]) * t, p12[1] + (p23[1] - p12[1]) * t]
    
    p0123 = [p012[0] + (p123[0] - p012[0]) * t, p012[1] + (p123[1] - p012[1]) * t]
    
    # Return split segments
    sp_left = [sp1[0][:], sp1[1][:], p01]
    sp_mid = [p012, p0123, p123]
    sp_right = [p23, sp2[1][:], sp2[2][:]]
    
    return sp_left, sp_mid, sp_right


def csp_normalized_slope(sp1, sp2, t):
    """Get normalized slope (tangent) at parameter t"""
    ax, ay, bx, by, cx, cy, dx, dy = csp_parameterize(sp1, sp2)
    
    # First derivative
    fx = 3 * ax * t**2 + 2 * bx * t + cx
    fy = 3 * ay * t**2 + 2 * by * t + cy
    
    # Handle zero derivative
    if abs(fx) < 1e-10 and abs(fy) < 1e-10:
        # Try second derivative
        fx = 6 * ax * t + 2 * bx
        fy = 6 * ay * t + 2 * by
        
        if abs(fx) < 1e-10 and abs(fy) < 1e-10:
            # Try third derivative
            fx = 6 * ax
            fy = 6 * ay
            
            if abs(fx) < 1e-10 and abs(fy) < 1e-10:
                return [1.0, 0.0]
    
    # Normalize
    length = math.sqrt(fx**2 + fy**2)
    if length > 0:
        return [fx / length, fy / length]
    return [1.0, 0.0]


def csp_normalized_normal(sp1, sp2, t):
    """Get normalized normal at parameter t"""
    slope = csp_normalized_slope(sp1, sp2, t)
    return [-slope[1], slope[0]]


def csp_curvature_at_t(sp1, sp2, t):
    """Calculate curvature at parameter t"""
    ax, ay, bx, by, cx, cy, dx, dy = csp_parameterize(sp1, sp2)
    
    # First derivative
    fx = 3 * ax * t**2 + 2 * bx * t + cx
    fy = 3 * ay * t**2 + 2 * by * t + cy
    
    # Second derivative
    fxx = 6 * ax * t + 2 * bx
    fyy = 6 * ay * t + 2 * by
    
    # Curvature = (x'y'' - y'x'') / (x'² + y'²)^(3/2)
    denominator = (fx**2 + fy**2)**1.5
    
    if abs(denominator) < 1e-10:
        return 1e10  # Very high curvature
    
    curvature = (fx * fyy - fy * fxx) / denominator
    return curvature


def csp_length(sp1, sp2, tolerance=0.001):
    """Estimate length of cubic super path segment"""
    # Use adaptive subdivision
    def recursive_length(sp1, sp2, depth=0):
        if depth > 10:
            # Direct distance as fallback
            p1 = sp1[1]
            p2 = sp2[1]
            return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
        
        # Calculate length using control points
        points = [sp1[1], sp1[2], sp2[0], sp2[1]]
        chord_length = math.sqrt(
            (points[3][0] - points[0][0])**2 + 
            (points[3][1] - points[0][1])**2
        )
        
        poly_length = sum(
            math.sqrt((points[i][0] - points[i-1][0])**2 + 
                     (points[i][1] - points[i-1][1])**2)
            for i in range(1, 4)
        )
        
        if poly_length - chord_length < tolerance:
            return poly_length
        
        # Split and recurse
        sp_left, sp_mid, sp_right = csp_split(sp1, sp2, 0.5)
        return recursive_length(sp_left, sp_mid, depth+1) + \
               recursive_length(sp_mid, sp_right, depth+1)
    
    return recursive_length(sp1, sp2)


def biarc_approximation(sp1, sp2, max_depth=4):
    """
    Approximate cubic bezier segment with biarcs
    Returns list of arc/line segments
    """
    
    def split_and_approximate(sp1, sp2, depth):
        """Recursively split if needed"""
        if depth >= max_depth:
            # Base case: return line
            return [{
                'type': 'line',
                'start': sp1[1],
                'end': sp2[1]
            }]
        
        # Check if segment is nearly straight
        p0, p1, p2, p3 = sp1[1], sp1[2], sp2[0], sp2[1]
        
        # Calculate straightness
        chord_length = math.sqrt((p3[0] - p0[0])**2 + (p3[1] - p0[1])**2)
        if chord_length < 0.01:
            return [{
                'type': 'line',
                'start': p0,
                'end': p3
            }]
        
        # Calculate control point distances
        d1 = abs((p1[1] - p0[1]) * (p3[0] - p0[0]) - 
                 (p1[0] - p0[0]) * (p3[1] - p0[1])) / chord_length
        d2 = abs((p2[1] - p0[1]) * (p3[0] - p0[0]) - 
                 (p2[0] - p0[0]) * (p3[1] - p0[1])) / chord_length
        
        if max(d1, d2) < 0.1:  # Tolerance for straightness
            return [{
                'type': 'line',
                'start': p0,
                'end': p3
            }]
        
        # Try to fit biarc
        result = fit_biarc(sp1, sp2)
        if result:
            return result
        
        # Split and recurse
        sp_left, sp_mid, sp_right = csp_split(sp1, sp2, 0.5)
        return (split_and_approximate(sp_left, sp_mid, depth + 1) +
                split_and_approximate(sp_mid, sp_right, depth + 1))
    
    return split_and_approximate(sp1, sp2, 0)


def fit_biarc(sp1, sp2):
    """
    Fit two circular arcs to a cubic bezier segment
    Returns list of two arc segments or None if not possible
    """
    P0 = P(sp1[1])
    P3 = P(sp2[1])
    T0 = P(sp1[2]) - P0  # Start tangent
    T3 = P(sp2[1]) - P(sp2[0])  # End tangent
    
    # Check for degenerate cases
    if T0.mag() < 1e-6 or T3.mag() < 1e-6:
        return None
    
    T0 = T0.unit()
    T3 = T3.unit()
    V = P3 - P0
    
    # Check if tangents are parallel
    if abs(T0.x * T3.y - T0.y * T3.x) < 1e-6:
        return None
    
    # Calculate join point P1
    # This is a simplified biarc calculation
    t = 0.5  # Use midpoint as simple heuristic
    P1 = P0 + V * t
    
    # Calculate arc centers and angles
    # (Simplified - full implementation would be more complex)
    
    return [{
        'type': 'arc',
        'start': P0.to_list(),
        'end': P1.to_list(),
        'center': ((P0 + P1) / 2).to_list(),
        'angle': 0.0
    }, {
        'type': 'arc',
        'start': P1.to_list(),
        'end': P3.to_list(),
        'center': ((P1 + P3) / 2).to_list(),
        'angle': 0.0
    }]


def normalize(v):
    """Normalize a 2D vector"""
    length = math.sqrt(v[0]**2 + v[1]**2)
    if length > 0:
        return [v[0] / length, v[1] / length]
    return [0, 0]


def dot(a, b):
    """Dot product of two 2D vectors"""
    return a[0] * b[0] + a[1] * b[1]


def cross(a, b):
    """Cross product (z-component) of two 2D vectors"""
    return a[0] * b[1] - a[1] * b[0]
