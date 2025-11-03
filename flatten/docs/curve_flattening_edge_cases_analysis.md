# Curve Flattening Algorithm Edge Cases Analysis

## Algorithm Overview

The current flattening algorithm:
1. Computes negative CUSUM: `cusum[i] = min(0, cusum[i-1] + (diff - k))` where `diff = y[i] - y[i-1]`
2. Applies smoothing with window size 5 before CUSUM computation
3. Finds minimum CUSUM value and its index
4. If CUSUM min ≤ threshold (e.g., -80), flattens all readings before min index to the value at min index
5. Includes sanity check: compares reading at CUSUM min with average of first 2-5 cycles

## Mathematical Analysis of Edge Cases

### 1. False Positives (Curves Incorrectly Flattened)

#### 1.1 V-Shaped Recovery Pattern
**Problem**: Sharp decline followed by equally sharp recovery
```
Pattern: [100, 95, 85, 70, 50, 70, 85, 95, 100, ...]
CUSUM accumulation: Builds up negative value during decline
CUSUM min index: At the valley (index 4, value=50)
Issue: Would flatten indices 0-3 to value 50, destroying valid initial data
```

**Mathematical Explanation**: 
- CUSUM accumulates: -5, -15, -30, -50 at valley
- Recovery doesn't reset CUSUM immediately due to min(0, ...) operation
- Sanity check may pass if avg(first 2) = 97.5 > 50

#### 1.2 Oscillating Pattern with Drift
**Problem**: Natural oscillation with slight downward drift
```
Pattern: [100, 98, 101, 97, 102, 96, 103, 95, 104, 94, ...]
With k=0: Small negative CUSUM accumulation over time
Issue: May flatten natural oscillations if drift accumulates past threshold
```

**Mathematical Explanation**:
- Each cycle contributes small negative CUSUM
- Over many cycles: CUSUM = Σ(negative_diffs) can exceed threshold
- Smoothing (window=5) may not eliminate oscillations completely

#### 1.3 Step Function with Noise
**Problem**: Single step down with noisy plateau
```
Pattern: [100±2, 100±2, 100±2, 75±2, 75±2, 75±2, ...]
CUSUM at step: Large negative jump (~-25)
Issue: Would flatten valid initial plateau to lower level
```

**Mathematical Explanation**:
- Step creates immediate CUSUM drop: cusum[step] ≈ -25
- Noise on plateau keeps CUSUM near this minimum
- Algorithm can't distinguish intentional step from slope

### 2. False Negatives (Curves Missed That Should Be Flattened)

#### 2.1 Gradual Decay with Late Acceleration
**Problem**: Slow initial decline that accelerates later
```
Pattern: [100, 99.5, 99, 98.5, 98, 97, 95, 92, 88, 83, ...]
Early CUSUM: Small accumulation (-0.5, -1, -1.5, ...)
Issue: May not reach threshold despite significant total decline
```

**Mathematical Explanation**:
- With k > 0: Early small decrements absorbed by k parameter
- CUSUM = Σ(diff - k), if diff ≈ k initially, no accumulation
- Late acceleration may be insufficient to reach threshold

#### 2.2 Sawtooth Decline
**Problem**: Decline with periodic small recoveries
```
Pattern: [100, 95, 96, 90, 91, 85, 86, 80, 81, ...]
CUSUM behavior: Partially resets at each recovery
Issue: May not accumulate enough to trigger flattening
```

**Mathematical Explanation**:
- Recovery steps create positive diffs
- CUSUM formula: min(0, cusum + diff), positive diffs push toward 0
- Net accumulation reduced: CUSUM_net ≈ Σ(declines) - partial_recovery_effect

#### 2.3 Multiple Plateau Pattern
**Problem**: Series of plateaus at decreasing levels
```
Pattern: [100, 100, 100, 90, 90, 90, 80, 80, 80, ...]
CUSUM: Jumps at transitions, stable on plateaus
Issue: Min index might be at wrong plateau transition
```

### 3. Sanity Check Edge Cases

#### 3.1 Early Spike Problem
**Scenario**: High initial values followed by normal decline
```
Pattern: [120, 115, 100, 95, 90, 85, 80, ...]
avg(first 2) = 117.5
Reading at min = 80
Sanity check: PASSES (80 < 117.5)
Issue: Flattening may be inappropriate despite passing check
```

#### 3.2 Index Boundary Issue
**Current Logic**:
```python
if min_index < 5:
    avg_first = np.mean(original_readings[:2])
else:
    avg_first = np.mean(original_readings[:5])
```
**Problem**: Discontinuity at index 5
- min_index = 4: compares with avg of first 2
- min_index = 5: compares with avg of first 5
- Can cause inconsistent decisions for similar patterns

#### 3.3 Insufficient Context
**Problem**: Using only first 2-5 readings ignores overall pattern
```
Pattern: [100, 98, 102, 97, 103, 50, 45, 40, ...]
avg(first 5) ≈ 100
Reading at min = 40
Sanity check: PASSES
Issue: Doesn't detect that decline starts after noisy beginning
```

### 4. Minimum Index Selection Issues

#### 4.1 Multiple Minima
**Problem**: CUSUM may have multiple points with same minimum value
```
Pattern: Decline → plateau → further decline
CUSUM: [-50, -80, -80, -80, -85, -85, -85]
Current: Uses first occurrence (index 1)
Issue: Should potentially use last occurrence for better representation
```

#### 4.2 Late Minimum Problem
**Problem**: Minimum occurs near end of series
```
Pattern: [100, 95, 90, ..., 20, 15, 10]
Min at index 41 (near end)
Issue: Flattens almost entire series, losing all variation
```

#### 4.3 Premature Minimum
**Problem**: Local minimum before global trend
```
Pattern: [100, 85, 90, 95, 80, 75, 70, ...]
First significant dip creates CUSUM min
Issue: Misses overall declining trend after recovery
```

### 5. Mathematical and Algorithmic Concerns

#### 5.1 Smoothing Window Effects
**Issue**: Window size 5 creates phase lag and boundary effects
```python
# Current smoothing implementation
for i in range(len(y_vals)):
    start = max(0, i - half_window)
    end = min(len(y_vals), i + half_window + 1)
```
**Problems**:
- Asymmetric at boundaries (less smoothing at start/end)
- 2-sample delay in detecting changes
- Can merge distinct features

#### 5.2 K Parameter Sensitivity
**Mathematical Analysis**:
- k=0: Pure accumulation of all negative changes
- k>0: Filters out small decrements
- Optimal k depends on noise level: k_opt ≈ σ_noise/√2

**Issue**: Fixed k across all signals ignores varying noise characteristics

#### 5.3 Threshold Selection
**Current**: Fixed threshold (e.g., -80)
**Problems**:
- Doesn't account for signal magnitude
- Doesn't consider series length
- Should be: threshold ∝ -σ_signal × √n × factor

#### 5.4 Noise Addition for Flattening
**Current Implementation**:
```python
noise_scale = reading_std * 0.001  # 0.1% of std
noise = random.uniform(-noise_scale, noise_scale)
```
**Issues**:
- If original std is very small, noise becomes negligible
- If original std is large, may introduce unrealistic variation
- Uniform distribution unlike typical measurement noise (should be Gaussian)

## Recommendations for Improvement

### 1. Enhanced Detection Logic
```python
def improved_detection(readings, cusum_values):
    # Multiple criteria approach
    criteria = {
        'cusum_threshold': min(cusum_values) <= threshold,
        'total_decline': readings[-1] < readings[0] * 0.8,  # 20% decline
        'consistent_trend': check_trend_consistency(readings),
        'sufficient_data': find_cusum_minimum_index(cusum_values) > len(readings) * 0.1
    }
    return sum(criteria.values()) >= 3  # Require multiple criteria
```

### 2. Adaptive Parameters
```python
def adaptive_parameters(readings):
    noise_estimate = estimate_noise_level(readings)
    signal_range = max(readings) - min(readings)
    
    k_adaptive = noise_estimate * 0.5  # Filter noise-level changes
    threshold_adaptive = -3 * signal_range * np.sqrt(len(readings)) / 10
    
    return k_adaptive, threshold_adaptive
```

### 3. Improved Sanity Check
```python
def enhanced_sanity_check(readings, min_index):
    # Use robust statistics
    initial_median = np.median(readings[:min(10, len(readings)//4)])
    min_value = readings[min_index]
    
    # Check multiple conditions
    checks = [
        min_value < initial_median * 0.9,  # 10% decline
        min_index > 3,  # Not too early
        min_index < len(readings) * 0.8,  # Not too late
        check_monotonic_region(readings, min_index)  # Verify actual decline
    ]
    
    return all(checks)
```

### 4. Alternative Flattening Strategy
```python
def smart_flattening(readings, cusum_values, min_index):
    # Find start of significant decline
    decline_start = find_decline_start(cusum_values, min_index)
    
    # Use weighted average for target value
    window = readings[max(0, min_index-2):min(len(readings), min_index+3)]
    target = np.median(window)
    
    # Flatten only the declining portion
    flattened = readings.copy()
    for i in range(decline_start, min_index):
        flattened[i] = target + appropriate_noise()
    
    return flattened
```

## Conclusion

The current algorithm has several vulnerabilities:

1. **Over-sensitive** to cumulative effects in oscillating patterns
2. **Under-sensitive** to gradual declines with variable rates
3. **Simplistic** sanity check that can be fooled by early spikes or noise
4. **Rigid** threshold that doesn't adapt to signal characteristics
5. **Naive** flattening that destroys all variation before minimum

These issues can lead to both false positives (flattening valid data) and false negatives (missing true declines). A more robust approach would use multiple detection criteria, adaptive parameters, and selective flattening based on identified decline regions rather than wholesale replacement of early data.