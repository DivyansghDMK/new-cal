"""
ecg/holter/holter_auto_arrhythmia_detect.py
===========================================
Auto-detection module for arrhythmias in Holter full disclosure view.

This module provides functionality to automatically detect arrhythmias from
ECG waveforms using the arrhythmia_detector module and add them as structured
events for waveform coloring.
"""

import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Callable, Optional


def detect_arrhythmias(
    reader,
    progress_callback: Optional[Callable[[int], None]] = None
) -> List[Dict[str, Any]]:
    """
    Auto-detect arrhythmias from the waveform using arrhythmia_detector.py.
    
    Args:
        reader: ECGHFileReader instance with read_range method
        progress_callback: Optional callback function(int) for progress updates (0-100)
    
    Returns:
        List of detected arrhythmia segments with:
            - start_sec: Start time in seconds
            - end_sec: End time in seconds
            - label: Short label code (V, AF, S, P, X)
            - color: Color hex code for waveform coloring
            - detected_rhythm: Full arrhythmia name
    """
    from ecg.arrhythmia_detector import analyze_ecg
    
    detected_segments = []
    
    # Get sampling rate and duration from reader
    fs = getattr(reader, 'fs', 500)
    if fs is None or fs <= 0:
        fs = 500
    
    total_duration = getattr(reader, 'duration_sec', 0)
    if total_duration <= 0:
        print("[Auto Arrhythmia Detect] Invalid duration")
        return []
    
    # Get lead names from reader
    lead_names = getattr(reader, 'lead_names', [])
    if not lead_names:
        lead_names = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
    
    # Process in 10-second windows with 5-second overlap
    window_size = 10.0  # seconds
    overlap = 5.0  # seconds
    step_size = window_size - overlap
    
    # Process each window
    current_time = 0.0
    window_count = 0
    
    while current_time < total_duration:
        window_end = min(current_time + window_size, total_duration)
        
        try:
            # Read window data from reader
            data_array = reader.read_range(current_time, window_end)
            
            if data_array is not None and data_array.shape[1] > 0:
                # Convert to leads dictionary for analyze_ecg
                window_leads = {}
                for i, lead_name in enumerate(lead_names):
                    if i < data_array.shape[0]:
                        window_leads[lead_name] = data_array[i, :]
                
                if window_leads:
                    # Run arrhythmia detection
                    results = analyze_ecg(window_leads, fs=fs)
                    
                    # Get detected arrhythmias
                    arrhythmias = results.get('arrhythmias', [])
                    primary_rhythm = results.get('primary_rhythm', '')
                    
                    if arrhythmias or primary_rhythm:
                        # Map detected arrhythmias to segment labels
                        label_map = {
                            'Asystole': ('X', '#0000FF'),
                            'Ventricular Fibrillation': ('V', '#FF3333'),
                            'Ventricular Tachycardia': ('V', '#FF3333'),
                            'Atrial Fibrillation': ('AF', '#FF00FF'),
                            'Atrial Flutter': ('AF', '#FF00FF'),
                            'Sinus Bradycardia': ('S', '#00FFFF'),
                            'Sinus Tachycardia': ('S', '#00FFFF'),
                            'Normal Sinus Rhythm': ('N', '#00FF00'),
                            'Bradycardia (non-sinus)': ('S', '#00FFFF'),
                            'Tachycardia (non-sinus)': ('S', '#00FFFF'),
                            '1st-degree AV block': ('P', '#FF00FF'),
                            '2nd-degree AV block (Mobitz I / Wenckebach)': ('P', '#FF00FF'),
                            '3rd-degree AV block': ('P', '#FF00FF'),
                            'Right bundle branch block (RBBB)': ('P', '#FF00FF'),
                            'Left bundle branch block (LBBB)': ('P', '#FF00FF'),
                            'Premature ventricular contraction (PVC)': ('V', '#FF3333'),
                            'Premature atrial contraction (PAC)': ('S', '#00FFFF'),
                            'ST elevation': ('X', '#FFFF00'),
                            'ST depression': ('X', '#FFFF00'),
                        }
                        
                        # Use primary rhythm or first arrhythmia
                        detected_label = primary_rhythm if primary_rhythm else (arrhythmias[0] if arrhythmias else '')
                        
                        # Map to segment label
                        label_code, color = label_map.get(detected_label, ('X', '#0000FF'))
                        
                        # Only add if not Normal Sinus Rhythm (to avoid clutter)
                        if detected_label != 'Normal Sinus Rhythm' and detected_label != 'Rhythm Undetermined':
                            # Compute real-world timestamp strings
                            start_time_str = ''
                            end_time_str = ''
                            try:
                                if hasattr(reader, 'start_time') and reader.start_time is not None:
                                    start_real = datetime.fromtimestamp(reader.start_time + current_time)
                                    end_real = datetime.fromtimestamp(reader.start_time + window_end)
                                    start_time_str = start_real.strftime('%H:%M:%S')
                                    end_time_str = end_real.strftime('%H:%M:%S')
                                else:
                                    h = int(current_time // 3600)
                                    m = int((current_time % 3600) // 60)
                                    s = int(current_time % 60)
                                    start_time_str = f"{h:02d}:{m:02d}:{s:02d}"
                                    
                                    h = int(window_end // 3600)
                                    m = int((window_end % 3600) // 60)
                                    s = int(window_end % 60)
                                    end_time_str = f"{h:02d}:{m:02d}:{s:02d}"
                            except Exception as e:
                                print(f"[Auto Arrhythmia Detect] Error formatting time: {e}")
                            
                            detected_segments.append({
                                'start_sec': current_time,
                                'end_sec': window_end,
                                'label': label_code,
                                'color': color,
                                'start_time_str': start_time_str,
                                'end_time_str': end_time_str,
                                'detected_rhythm': detected_label
                            })
                            
                            print(f"[Auto Arrhythmia Detect] Detected: {detected_label} at {current_time:.1f}s - {window_end:.1f}s")
        
        except Exception as e:
            print(f"[Auto Arrhythmia Detect] Error analyzing window {current_time:.1f}s: {e}")
        
        current_time += step_size
        window_count += 1
        
        # Update progress periodically
        if window_count % 10 == 0 and progress_callback:
            progress = int((current_time / total_duration) * 100)
            progress_callback(progress)
    
    # Merge overlapping segments with same label
    if detected_segments:
        detected_segments.sort(key=lambda x: x['start_sec'])
        merged_segments = []
        
        for seg in detected_segments:
            if not merged_segments:
                merged_segments.append(seg)
            else:
                last = merged_segments[-1]
                # Check if overlapping and same label
                if (seg['start_sec'] <= last['end_sec'] + 2.0 and 
                    seg['label'] == last['label']):
                    # Merge segments
                    last['end_sec'] = max(last['end_sec'], seg['end_sec'])
                    last['end_time_str'] = seg['end_time_str']
                else:
                    merged_segments.append(seg)
        
        detected_segments = merged_segments
    
    return detected_segments


def convert_to_structured_events(detected_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert detected segments to structured_events format for waveform coloring.
    
    Args:
        detected_segments: List of detected arrhythmia segments from detect_arrhythmias()
    
    Returns:
        List of structured events with timestamp, type, label, end_timestamp, color
    """
    structured_events = []
    
    for seg in detected_segments:
        structured_events.append({
            'timestamp': seg['start_sec'],
            'type': seg['detected_rhythm'],
            'label': seg['detected_rhythm'],
            'end_timestamp': seg['end_sec'],
            'color': seg['color']
        })
    
    # Sort by timestamp
    structured_events.sort(key=lambda x: float(x.get('timestamp', 0.0) or 0.0))
    
    return structured_events
