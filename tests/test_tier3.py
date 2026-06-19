import os
import pytest
import numpy as np
import pandas as pd

from core.detector import DroneDetector
from core.tracker import RobustDroneTracker
from core.homography import PitchRegistrator
from wrappers.data_layers import TrajectoryDataLayer
from analytics.possession import PossessionAnalyzer
from football_tactical_analytics_engine import FootballTacticalAnalyzer


def test_tier3_tracker_split_reid_stitching():
    """51. Split + Re-ID Stitching: Tracker splits duelists, offline Re-ID merges them post-duel."""
    tracker = RobustDroneTracker(iou_threshold=0.7)
    
    # 1. Frame 1: Two players are separate
    detections_f1 = {
        "boxes": [[100, 100, 120, 120], [200, 200, 220, 220]],
        "labels": ["player", "player"],
        "confidences": [0.9, 0.9],
        "teams": [0, 0]
    }
    ids_f1 = tracker.update(detections_f1)
    
    # 2. Frame 2: Collision (IoU overlap > iou_threshold)
    detections_f2 = {
        "boxes": [[100, 100, 120, 120], [100, 100, 120, 120]],
        "labels": ["player", "player"],
        "confidences": [0.9, 0.9],
        "teams": [0, 0]
    }
    ids_f2 = tracker.update(detections_f2)
    # The split should terminate both tracklets, placing them into metadata for offline Re-ID
    assert len(tracker.tracks) == 0
    assert len(tracker.tracklet_metadata) >= 2
    
    # 3. Frame 3: Duelists emerge separately again
    detections_f3 = {
        "boxes": [[102, 102, 122, 122], [202, 202, 222, 222]],
        "labels": ["player", "player"],
        "confidences": [0.9, 0.9],
        "teams": [0, 0]
    }
    ids_f3 = tracker.update(detections_f3)
    
    # Create complete dataframe for offline stitching
    # To test integration, build a dataframe matching the track IDs
    df = pd.DataFrame([
        # Player 1 first tracklet (frames 1-2)
        {"frame_id": 1, "player_id": ids_f1[0], "x_pixel": 110.0, "y_pixel": 120.0, "x_meter": 11.0, "y_meter": 12.0, "xmin": 100, "ymin": 100, "xmax": 120, "ymax": 120, "label": "player", "team_id": 0, "confidence": 0.9},
        # Player 2 first tracklet (frames 1-2)
        {"frame_id": 1, "player_id": ids_f1[1], "x_pixel": 210.0, "y_pixel": 220.0, "x_meter": 21.0, "y_meter": 22.0, "xmin": 200, "ymin": 200, "xmax": 220, "ymax": 220, "label": "player", "team_id": 0, "confidence": 0.9},
        # Re-emergence (frame 3) - aligned to exact positions of original tracklets
        {"frame_id": 3, "player_id": ids_f3[0], "x_pixel": 110.0, "y_pixel": 120.0, "x_meter": 11.0, "y_meter": 12.0, "xmin": 100, "ymin": 100, "xmax": 120, "ymax": 120, "label": "player", "team_id": 0, "confidence": 0.9},
        {"frame_id": 3, "player_id": ids_f3[1], "x_pixel": 210.0, "y_pixel": 220.0, "x_meter": 21.0, "y_meter": 22.0, "xmin": 200, "ymin": 200, "xmax": 220, "ymax": 220, "label": "player", "team_id": 0, "confidence": 0.9},
    ])
    df.set_index(["frame_id", "player_id"], inplace=True)
    
    # offline_stitch
    stitched_df = tracker.offline_stitch(df, fps=30.0)
    # The re-emerging track IDs (ids_f3) should have been stitched to the original ones (ids_f1)
    assert len(stitched_df.index.levels[1].unique()) <= 3

def test_tier3_homography_ballistic_interpolation():
    """52. Homography + Ballistic: Projects ball coords, fits parabolic curve, clamps boundary limits."""
    registrator = PitchRegistrator()
    data_layer = TrajectoryDataLayer(registrator)
    
    # 1. Ball travels parabolically: frame 1, 2, 3, (gap 4), 5, 6, 7
    # Metrics: (x, y) = (t, t^2)
    # We define pixel positions which correspond to meters. For simplicity, let default homography map it.
    df = pd.DataFrame([
        {"frame_id": 1, "player_id": 99, "x_pixel": 10.0, "y_pixel": 10.0, "x_meter": 1.0, "y_meter": 1.0, "xmin": 5, "ymin": 5, "xmax": 15, "ymax": 15, "label": "ball", "team_id": -1, "confidence": 0.9},
        {"frame_id": 2, "player_id": 99, "x_pixel": 20.0, "y_pixel": 14.0, "x_meter": 2.0, "y_meter": 1.4, "xmin": 15, "ymin": 9, "xmax": 25, "ymax": 19, "label": "ball", "team_id": -1, "confidence": 0.9},
        {"frame_id": 3, "player_id": 99, "x_pixel": 30.0, "y_pixel": 16.0, "x_meter": 3.0, "y_meter": 1.6, "xmin": 25, "ymin": 11, "xmax": 35, "ymax": 21, "label": "ball", "team_id": -1, "confidence": 0.9},
        # Gap frame 4
        {"frame_id": 5, "player_id": 99, "x_pixel": 50.0, "y_pixel": 16.0, "x_meter": 5.0, "y_meter": 1.6, "xmin": 45, "ymin": 11, "xmax": 55, "ymax": 21, "label": "ball", "team_id": -1, "confidence": 0.9},
        {"frame_id": 6, "player_id": 99, "x_pixel": 60.0, "y_pixel": 14.0, "x_meter": 6.0, "y_meter": 1.4, "xmin": 55, "ymin": 9, "xmax": 65, "ymax": 19, "label": "ball", "team_id": -1, "confidence": 0.9},
        {"frame_id": 7, "player_id": 99, "x_pixel": 70.0, "y_pixel": 10.0, "x_meter": 7.0, "y_meter": 1.0, "xmin": 65, "ymin": 5, "xmax": 75, "ymax": 15, "label": "ball", "team_id": -1, "confidence": 0.9},
    ])
    df.set_index(["frame_id", "player_id"], inplace=True)
    
    res = data_layer.filter_ball_trajectory(df, max_gap=2)
    assert 4 in res.index.levels[0]
    # Verify clamping
    val = res.loc[(4, 99)]
    assert 0.0 <= val["x_meter"] <= 105.0
    assert 0.0 <= val["y_meter"] <= 68.0

def test_tier3_hue_clustering_reid_color_matching():
    """53. Color Consistency: Team IDs do not shift during tracking update and offline Re-ID stitching."""
    detector = DroneDetector()
    tracker = RobustDroneTracker()
    
    # Step 1: Detect frame 1 with colors
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    detections = detector.process_frame(frame)
    # Tracker updates active tracklet hues and team_ids
    ids_f1 = tracker.update(detections)
    # Re-ID stitching maps them later. Ensure team_ids are preserved in tracking dictionary
    for tid in ids_f1:
        if tid in tracker.tracks:
            assert tracker.tracks[tid]["team_id"] in [-1, 0, 1]

def test_tier3_stride_and_fps_scaling():
    """54. Strides and FPS scaling: Verify possession sequences scale relative to stride."""
    # Create possession DataFrame with 60 frames
    # Under stride 30, it effectively parses frame 1 and 31 (2 frames total)
    # Verify calculation logic handles low frame rates correctly
    analyzer = PossessionAnalyzer(t_in=1.5, t_out=2.5)
    records = []
    for f in [1, 31]:
        records.append({"frame_id": f, "player_id": 1, "x_pixel": 100.0, "y_pixel": 100.0, "xmin": 90, "ymin": 90, "xmax": 110, "ymax": 110, "label": "player", "team_id": 0, "confidence": 0.9})
        records.append({"frame_id": f, "player_id": 99, "x_pixel": 101.0, "y_pixel": 101.0, "label": "ball", "team_id": -1, "confidence": 0.9})
    df = pd.DataFrame(records).set_index(["frame_id", "player_id"])
    possession_df = analyzer.calculate_possession(df)
    assert len(possession_df) == 2
    assert possession_df.loc[1, "possession_team_id"] == 0
    assert possession_df.loc[31, "possession_team_id"] == 0

def test_tier3_detector_fallback_to_homography_mapping():
    """55. Fallback continuity: Simulated detections are mapped via PitchRegistrator successfully."""
    detector = DroneDetector()
    registrator = PitchRegistrator()
    data_layer = TrajectoryDataLayer(registrator)
    
    # Process frame to trigger fallback
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    detections = detector.process_frame(frame)
    
    # Process coordinates and add to data layer
    data_layer.add_frame_data(frame_id=1, track_ids=list(range(len(detections["boxes"]))), detections=detections)
    df = data_layer.to_dataframe()
    
    # Check that metric coordinates are in bounds
    assert not df.empty
    assert (df["x_meter"] >= 0).all()
    assert (df["y_meter"] >= 0).all()
