"""
Algorithm utility functions for CUSUM and curve processing
"""
import numpy as np
from scipy import stats

def compute_negative_cusum(y_vals, k=0.0):
    """Compute negative CUSUM with adjustable k parameter - matches original algorithm"""
    cusum = [0]
    for i in range(1, len(y_vals)):
        diff = y_vals[i] - y_vals[i - 1]
        s = min(0, cusum[-1] + (diff - k))
        cusum.append(s)
    return np.array(cusum)

def smooth_curve(y_vals, window_size=5):
    """Apply smoothing to curve data"""
    if len(y_vals) < window_size:
        return y_vals
    
    smoothed = []
    half_window = window_size // 2
    
    for i in range(len(y_vals)):
        start = max(0, i - half_window)
        end = min(len(y_vals), i + half_window + 1)
        smoothed.append(sum(y_vals[start:end]) / (end - start))
    
    return smoothed

def find_cusum_minimum_index(cusum_values):
    """Find the index where CUSUM reaches its minimum value"""
    min_val = min(cusum_values)
    return cusum_values.index(min_val)

def calculate_lob_gradient(x_values, y_values):
    """Calculate Line of Best Fit gradient using linear regression"""
    slope, intercept, r_value, p_value, std_err = stats.linregress(x_values, y_values)
    return slope, intercept, r_value

def apply_corrected_cusum_algorithm(readings, k=0.0):
    """Apply the corrected CUSUM algorithm with adjustable k parameter"""
    margin = 50
    plot_width = 800 - 2 * margin
    plot_height = 400 - 2 * margin
    
    min_reading = min(readings)
    max_reading = max(readings)
    reading_range = max_reading - min_reading if max_reading != min_reading else 1
    
    # Convert to SVG coordinates (same as original algorithm)
    svg_y_vals = []
    for reading in readings:
        svg_y = margin + plot_height - (plot_height * (reading - min_reading) / reading_range)
        svg_y_vals.append(svg_y)
    
    svg_y_vals = np.array(svg_y_vals)
    
    # Apply simple inversion
    y_inv = np.max(svg_y_vals) - svg_y_vals
    
    # Smooth the inverted data
    y_smooth = smooth_curve(y_inv)
    
    # Apply CUSUM with custom k parameter
    cusum = compute_negative_cusum(y_smooth, k=k)
    
    return cusum, min(cusum)