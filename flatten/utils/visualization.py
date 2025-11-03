"""
Visualization utility functions for SVG/HTML generation
"""
import random
import numpy as np

def create_flattened_readings(original_readings, cusum_values, cusum_min, threshold=-80, 
                             sanity_check=False, sanity_lob=False, target_reading=None, 
                             min_index=None, avg_first=None, lob_gradient=None):
    """Create flattened readings for curves with significant downward trends
    
    This is the consolidated version handling all sanity check types.
    """
    from .algorithms import find_cusum_minimum_index, calculate_lob_gradient
    
    # Only flatten if CUSUM min <= threshold
    if cusum_min > threshold:
        return None
    
    # Find the index where CUSUM reaches minimum (end of downward slope)
    if min_index is None:
        min_index = find_cusum_minimum_index(cusum_values)
    
    # Skip if minimum occurs too early (nothing to flatten)
    if min_index <= 1:
        return None
    
    # Get the target reading value (at the minimum CUSUM point)
    if target_reading is None:
        target_reading = original_readings[min_index]
    
    # Sanity check: ensure the CUSUM min point actually represents a decrease
    if sanity_check:
        if avg_first is None:
            # Check if min_index is in first five cycles
            if min_index < 5:
                # For first five cycles, compare with average of first two
                avg_first = np.mean(original_readings[:2])
            else:
                # Otherwise, compare with average of first five cycles
                avg_first = np.mean(original_readings[:5])
        
        # Skip if the reading at cusum min is not lower than the early average
        if target_reading >= avg_first:
            return None  # Sanity check failed, don't flatten
    
    if sanity_lob:
        if lob_gradient is None:
            # Line of Best Fit sanity check: check gradient from first to CUSUM min
            # Use readings from index 0 to min_index (inclusive)
            x_values = np.arange(min_index + 1)
            y_values = original_readings[:min_index + 1]
            
            # Calculate line of best fit
            lob_gradient, _, _ = calculate_lob_gradient(x_values, y_values)
        
        # Check if gradient is negative (downward trend)
        if lob_gradient >= 0:
            return None  # LOB sanity check failed, don't flatten
    
    # Determine appropriate noise scale based on data
    reading_std = np.std(original_readings)
    noise_scale = reading_std * 0.001  # Very small noise, 0.1% of standard deviation
    
    # Create flattened readings
    flattened = original_readings.copy()
    
    # Flatten all readings before the minimum point
    for i in range(min_index):
        # Add small random noise to prevent identical values
        noise = random.uniform(-noise_scale, noise_scale)
        flattened[i] = target_reading + noise
    
    return flattened

def scale_to_svg_coords(values, margin, plot_size, value_min=None, value_max=None):
    """Convert data values to SVG coordinates"""
    if value_min is None:
        value_min = min(values)
    if value_max is None:
        value_max = max(values)
    
    value_range = value_max - value_min if value_max != value_min else 1
    
    svg_coords = []
    for value in values:
        svg_coord = margin + plot_size - (plot_size * (value - value_min) / value_range)
        svg_coords.append(svg_coord)
    
    return svg_coords

def generate_svg_path(x_values, y_values):
    """Generate SVG path string from x,y coordinates"""
    path_parts = []
    for i, (x, y) in enumerate(zip(x_values, y_values)):
        command = 'M' if i == 0 else 'L'
        path_parts.append(f"{command} {x:.1f} {y:.1f}")
    return " ".join(path_parts)