import unittest
from unittest.mock import patch, MagicMock
import numpy as np
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ecg.qrs_detection import measure_qrs_duration_paper

class TestQRSPaper(unittest.TestCase):
    def test_median_beat_unavailable(self):
        # Test case: median beat unavailable (empty or too short)
        # 1. Empty beat
        res = measure_qrs_duration_paper(np.array([]), np.array([]), 500.0, 0.0)
        self.assertIsNone(res)
        
        # 2. Too short beat (length < 30)
        res = measure_qrs_duration_paper(np.zeros(20), np.zeros(20), 500.0, 0.0)
        self.assertIsNone(res)

    @patch('ecg.qrs_detection.find_reference_peak')
    @patch('ecg.qrs_detection.find_significant_peaks')
    @patch('ecg.qrs_detection.remove_peak_outliers_by_spacing')
    @patch('ecg.qrs_detection.delineate_channel_borders')
    @patch('ecg.qrs_detection.delineate_global_borders')
    @patch('ecg.qrs_detection._adaptive_amplitude_qrs_width')
    def test_paper_delineation_success(self, mock_amp, mock_glob, mock_chan, mock_spacing, mock_sig, mock_ref):
        # Test case: paper delineation success
        mock_ref.return_value = 150
        mock_sig.return_value = [150]
        mock_spacing.return_value = [150]
        # delineate_channel_borders returns (onset, offset)
        mock_chan.return_value = (130, 170)
        # delineate_global_borders returns (onset, offset)
        mock_glob.return_value = (130, 170)
        # amp override returns 0 (no override)
        mock_amp.return_value = (0.0, None, None)
        
        # Call function: fs=500.0. QRS = (170-130)/500 * 1000 = 80ms
        res = measure_qrs_duration_paper(np.ones(300), np.arange(300), 500.0, 0.0)
        self.assertEqual(res, 80)

    @patch('ecg.qrs_detection.find_reference_peak')
    @patch('ecg.qrs_detection.find_significant_peaks')
    @patch('ecg.qrs_detection.remove_peak_outliers_by_spacing')
    @patch('ecg.qrs_detection.delineate_channel_borders')
    @patch('ecg.qrs_detection.delineate_global_borders')
    def test_paper_delineation_failure(self, mock_glob, mock_chan, mock_spacing, mock_sig, mock_ref):
        # Test case: paper delineation failure (e.g., global borders are None)
        mock_ref.return_value = 150
        mock_sig.return_value = [150]
        mock_spacing.return_value = [150]
        mock_chan.return_value = (None, None)
        mock_glob.return_value = (None, None)
        
        res = measure_qrs_duration_paper(np.ones(300), np.arange(300), 500.0, 0.0)
        self.assertIsNone(res)

    @patch('ecg.qrs_detection.find_reference_peak')
    @patch('ecg.qrs_detection.find_significant_peaks')
    @patch('ecg.qrs_detection.remove_peak_outliers_by_spacing')
    @patch('ecg.qrs_detection.delineate_channel_borders')
    @patch('ecg.qrs_detection.delineate_global_borders')
    @patch('ecg.qrs_detection._adaptive_amplitude_qrs_width')
    def test_amplitude_override_success(self, mock_amp, mock_glob, mock_chan, mock_spacing, mock_sig, mock_ref):
        # Test case: amplitude override success
        # Paper method finds QRS = 80ms. Amplitude override finds 120ms (plausible & wider).
        mock_ref.return_value = 150
        mock_sig.return_value = [150]
        mock_spacing.return_value = [150]
        mock_chan.return_value = (130, 170) # 80ms
        mock_glob.return_value = (130, 170)
        # amp override returns 120.0ms, onset, offset
        mock_amp.return_value = (120.0, 120, 180)
        
        res = measure_qrs_duration_paper(np.ones(300), np.arange(300), 500.0, 0.0)
        self.assertEqual(res, 120)

    @patch('ecg.qrs_detection.find_reference_peak')
    @patch('ecg.qrs_detection.find_significant_peaks')
    @patch('ecg.qrs_detection.remove_peak_outliers_by_spacing')
    @patch('ecg.qrs_detection.delineate_channel_borders')
    @patch('ecg.qrs_detection.delineate_global_borders')
    @patch('ecg.qrs_detection._adaptive_amplitude_qrs_width')
    def test_amplitude_override_rejection(self, mock_amp, mock_glob, mock_chan, mock_spacing, mock_sig, mock_ref):
        # Test case: amplitude override rejection
        # Scenario A: Amplitude override is > 160ms (implausible)
        mock_ref.return_value = 150
        mock_sig.return_value = [150]
        mock_spacing.return_value = [150]
        mock_chan.return_value = (130, 170) # 80ms
        mock_glob.return_value = (130, 170)
        mock_amp.return_value = (180.0, 105, 195)
        
        res = measure_qrs_duration_paper(np.ones(300), np.arange(300), 500.0, 0.0)
        # Should stay 80ms, not override to 180ms
        self.assertEqual(res, 80)

        # Scenario B: Amplitude override is narrower than paper method and paper method did not fail
        mock_amp.return_value = (70.0, 132, 167)
        res = measure_qrs_duration_paper(np.ones(300), np.arange(300), 500.0, 0.0)
        # Should stay 80ms, not override to 70ms
        self.assertEqual(res, 80)

if __name__ == '__main__':
    unittest.main()
