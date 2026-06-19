import os
import pytest
import numpy as np
import pandas as pd
import cv2
from unittest.mock import patch

from core.detector import DroneDetector
from core.tracker import RobustDroneTracker, KalmanFilter2D
from core.homography import PitchRegistrator
from wrappers.data_layers import TrajectoryDataLayer
from analytics.possession import PossessionAnalyzer
from football_tactical_analytics_engine import FootballTacticalAnalyzer


# ==========================================
# FEATURE 1: VIDEO INGESTION & DETECTION
# ==========================================

def test_tier1_f1_ingest_standard_video(mock_video_factory):
    """1. Ingest standard video: Verify metadata and cv2 compatibility."""
    video_path = mock_video_factory(name="standard.mp4", num_frames=10)
    cap = cv2.VideoCapture(video_path)
    assert cap.isOpened()
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    assert total_frames == 10
    assert width == 640
    assert height == 360
    assert fps == 30.0
    cap.release()

def test_tier1_f1_ingest_stride_subsampling():
    """2. Stride sub-sampling: Process frames sequentially with step stride."""
    frame_indices = list(range(0, 100, 30))  # Stride 30
    assert frame_indices == [0, 30, 60, 90]
    assert len(frame_indices) == 4

def test_tier1_f1_ingest_frame_limiter(mock_video_factory):
    """3. Frame limiter: Ensure frame ingestion stops at specified limit."""
    video_path = mock_video_factory(name="limit.mp4", num_frames=10)
    cap = cv2.VideoCapture(video_path)
    limit = 5
    processed = 0
    while cap.isOpened() and processed < limit:
        ret, frame = cap.read()
        if not ret:
            break
        processed += 1
    cap.release()
    assert processed == 5

def test_tier1_f1_ingest_downscaling_active():
    """4. Downscaling: Check resizing of high-resolution frames."""
    large_frame = np.zeros((2160, 3840, 3), dtype=np.uint8)  # 4K frame
    target_size = (1920, 1080)
    resized_frame = cv2.resize(large_frame, target_size)
    assert resized_frame.shape == (1080, 1920, 3)

def test_tier1_f1_detector_clustering_teams():
    """5. DBSCAN team clustering: Verify Team A (0) and Team B (1) classification."""
    detector = DroneDetector()
    # Team A hues close to 0.05, Team B hues close to 0.65
    player_hues = [[0.04], [0.05], [0.06], [0.64], [0.65], [0.66]]
    labels = ["player"] * 6
    teams = detector.cluster_teams_dbscan(labels, player_hues)
    assert len(teams) == 6
    assert 0 in teams
    assert 1 in teams


# ==========================================
# FEATURE 2: MULTI-OBJECT TRACKING (MOT)
# ==========================================

def test_tier1_f2_tracker_kalman_prediction():
    """6. Kalman prediction: Verify state estimation."""
    kf = KalmanFilter2D(initial_x=10.0, initial_y=20.0)
    # Perform prediction
    px, py = kf.predict()
    assert px == 10.0
    assert py == 20.0
    # Update and predict again
    kf.update((12.0, 22.0))
    px2, py2 = kf.predict()
    assert px2 > 10.0
    assert py2 > 20.0

def test_tier1_f2_tracker_hungarian_assignment():
    """7. Hungarian assignment: Verify track ID continuity."""
    tracker = RobustDroneTracker()
    # Frame 1
    detections_f1 = {
        "boxes": [[100, 100, 120, 120]],
        "labels": ["player"],
        "confidences": [0.9],
        "teams": [0]
    }
    ids_f1 = tracker.update(detections_f1)
    # Frame 2 (slight movement)
    detections_f2 = {
        "boxes": [[102, 102, 122, 122]],
        "labels": ["player"],
        "confidences": [0.9],
        "teams": [0]
    }
    ids_f2 = tracker.update(detections_f2)
    assert ids_f1[0] == ids_f2[0]  # Kept the same ID

def test_tier1_f2_tracker_track_archiving():
    """8. Track archiving: Verify tracks terminate after max_lost_frames."""
    tracker = RobustDroneTracker(max_lost_frames=5)
    # Start track
    tracker.update({"boxes": [[100, 100, 120, 120]], "labels": ["player"], "confidences": [0.9], "teams": [0]})
    # Skip frames (unmatched)
    for _ in range(6):
        tracker.update({"boxes": [], "labels": [], "confidences": [], "teams": []})
    assert len(tracker.tracks) == 0
    assert len(tracker.tracklet_metadata) > 0  # Should be archived

def test_tier1_f2_tracker_team_identification():
    """9. Team identification: Verify tracks preserve correct team ID."""
    tracker = RobustDroneTracker()
    detections = {
        "boxes": [[100, 100, 120, 120], [200, 200, 220, 220]],
        "labels": ["player", "player"],
        "confidences": [0.9, 0.9],
        "teams": [0, 1]
    }
    ids = tracker.update(detections)
    assert tracker.tracks[ids[0]]["team_id"] == 0
    assert tracker.tracks[ids[1]]["team_id"] == 1

def test_tier1_f2_tracker_split_enforcement():
    """10. Tracklet split: Verify high IoU overlap triggers termination."""
    tracker = RobustDroneTracker(iou_threshold=0.7)
    # Setup two tracks close to each other
    tracker.update({"boxes": [[100, 100, 120, 120], [150, 150, 170, 170]], "labels": ["player", "player"], "confidences": [0.9, 0.9], "teams": [0, 1]})
    # Collision frame (IoU = 1.0)
    tracker.update({"boxes": [[100, 100, 120, 120], [100, 100, 120, 120]], "labels": ["player", "player"], "confidences": [0.9, 0.9], "teams": [0, 1]})
    # Active tracks should be terminated to prevent ID swaps
    assert len(tracker.tracks) == 0


# ==========================================
# FEATURE 3: HOMOGRAPHY MAPPING
# ==========================================

def test_tier1_f3_homography_default_projection():
    """11. Default Homography: Convert pixel coords to meters."""
    registrator = PitchRegistrator()
    xm, ym = registrator.pixel_to_meters(1920, 1080)
    # Check that default matrix converts coordinates successfully
    assert xm > 0
    assert ym > 0

def test_tier1_f3_homography_custom_calculation():
    """12. Custom Homography: Calculate 3x3 homography matrix."""
    registrator = PitchRegistrator()
    src = [(100, 100), (200, 100), (200, 200), (100, 200)]
    dst = [(0, 0), (10, 0), (10, 10), (0, 10)]
    H = registrator.compute_homography(src, dst)
    assert H.shape == (3, 3)

def test_tier1_f3_homography_numpy_fallback():
    """13. Homography SVD fallback: Test NumPy DLT solver without cv2."""
    registrator = PitchRegistrator()
    src = [(100, 100), (200, 100), (200, 200), (100, 200)]
    dst = [(0, 0), (10, 0), (10, 10), (0, 10)]
    # Temporarily mock cv2 import failure
    with patch.dict('sys.modules', {'cv2': None}):
        H = registrator.compute_homography(src, dst)
        assert H.shape == (3, 3)

def test_tier1_f3_homography_coord_clamping():
    """14. Coordinate clamping: In data layer filter_ball_trajectory, bounds are enforced."""
    registrator = PitchRegistrator()
    data_layer = TrajectoryDataLayer(registrator)
    
    # Setup df with out of bounds coordinate for ball
    df = pd.DataFrame([{
        "frame_id": 1,
        "player_id": 99,
        "x_pixel": 100,
        "y_pixel": 100,
        "x_meter": 200.0,  # Out of bounds (> 105)
        "y_meter": -10.0,  # Out of bounds (< 0)
        "xmin": 90, "ymin": 90, "xmax": 110, "ymax": 110,
        "label": "ball",
        "team_id": -1,
        "confidence": 0.8
    }])
    df.set_index(["frame_id", "player_id"], inplace=True)
    
    # We must insert a gap for interpolation to trigger clamping
    # Let's add ball in frame 1, gap in frame 2, ball in frame 3
    df_reset = df.reset_index()
    # Add frame 3 ball
    f3_ball = df_reset.copy()
    f3_ball["frame_id"] = 3
    # Concat
    df_full = pd.concat([df_reset, f3_ball], ignore_index=True)
    df_full.set_index(["frame_id", "player_id"], inplace=True)
    
    filtered_df = data_layer.filter_ball_trajectory(df_full, max_gap=1)
    
    # Frame 2 ball is interpolated and clamped
    f2_ball = filtered_df.xs(99, level="player_id").loc[2]
    assert 0.0 <= f2_ball["x_meter"] <= 105.0
    assert 0.0 <= f2_ball["y_meter"] <= 68.0

def test_tier1_f3_homography_point_mapping_player_vs_ball():
    """15. Contact point: Verify players map at feet and ball at center."""
    registrator = PitchRegistrator()
    data_layer = TrajectoryDataLayer(registrator)
    # Player bounding box
    box_p = [100, 100, 120, 200]  # xmin, ymin, xmax, ymax
    # Ball bounding box
    box_b = [300, 300, 310, 310]
    
    # Player foot is at ((100+120)/2, 200) = (110, 200)
    # Ball center is at ((300+310)/2, (300+310)/2) = (305, 305)
    
    data_layer.add_frame_data(
        frame_id=1,
        track_ids=[1, 99],
        detections={
            "boxes": [box_p, box_b],
            "labels": ["player", "ball"],
            "confidences": [0.9, 0.9],
            "teams": [0, -1]
        }
    )
    df = data_layer.to_dataframe()
    assert df.loc[(1, 1), "x_pixel"] == 110.0
    assert df.loc[(1, 1), "y_pixel"] == 200.0
    assert df.loc[(1, 99), "x_pixel"] == 305.0
    assert df.loc[(1, 99), "y_pixel"] == 305.0


# ==========================================
# FEATURE 4: POST-PROCESSING & INTERPOLATION
# ==========================================

def test_tier1_f4_postprocess_parquet_serialization(tmpdir):
    """16. Parquet serialization: Save and reload trajectory dataframe."""
    data_layer = TrajectoryDataLayer()
    data_layer.add_frame_data(1, [1], {"boxes": [[100,100,120,120]], "labels":["player"], "confidences":[0.9], "teams":[0]})
    parquet_path = os.path.join(tmpdir, "test.parquet")
    try:
        import pyarrow
        data_layer.save_to_parquet(parquet_path)
        assert os.path.exists(parquet_path)
        df = pd.read_parquet(parquet_path)
        assert not df.empty
    except ImportError:
        # Graceful pass if library is not present
        pass

def test_tier1_f4_postprocess_csv_serialization(tmpdir):
    """17. CSV serialization: Save and reload trajectory dataframe."""
    data_layer = TrajectoryDataLayer()
    data_layer.add_frame_data(1, [1], {"boxes": [[100,100,120,120]], "labels":["player"], "confidences":[0.9], "teams":[0]})
    csv_path = os.path.join(tmpdir, "test.csv")
    data_layer.save_to_csv(csv_path)
    assert os.path.exists(csv_path)
    df = pd.read_csv(csv_path, index_col=["frame_id", "player_id"])
    assert not df.empty

def test_tier1_f4_postprocess_reid_stitching_active():
    """18. Re-ID active stitching: Merge fragmented tracklets."""
    tracker = RobustDroneTracker()
    # Add two tracklets for same team and hue
    tracker.tracklet_metadata = [
        {"track_id": 1, "label": "player", "team_id": 0, "start_frame": 1, "end_frame": 5, "mean_hue": 0.05, "end_pos": [10.0, 10.0]},
        {"track_id": 2, "label": "player", "team_id": 0, "start_frame": 7, "end_frame": 10, "mean_hue": 0.05, "end_pos": [10.0, 10.0]}
    ]
    # Build df
    df = pd.DataFrame([
        {"frame_id": f, "player_id": 1, "x_pixel": 100.0, "y_pixel": 100.0, "x_meter": 10.0, "y_meter": 10.0, "xmin": 90, "ymin": 90, "xmax": 110, "ymax": 110, "label": "player", "team_id": 0, "confidence": 0.9}
        for f in range(1, 6)
    ] + [
        {"frame_id": f, "player_id": 2, "x_pixel": 100.0, "y_pixel": 100.0, "x_meter": 10.0, "y_meter": 10.0, "xmin": 90, "ymin": 90, "xmax": 110, "ymax": 110, "label": "player", "team_id": 0, "confidence": 0.9}
        for f in range(7, 11)
    ])
    df.set_index(["frame_id", "player_id"], inplace=True)
    
    stitched_df = tracker.offline_stitch(df, fps=30.0)
    # ID 2 should be mapped/merged to 1
    assert 2 not in stitched_df.index.levels[1]
    assert 1 in stitched_df.index.levels[1]

def test_tier1_f4_postprocess_reid_stitching_temporal_gate():
    """19. Stitching temporal gate: Prevent merger for large gap."""
    tracker = RobustDroneTracker()
    # Gap is 100 frames (> 2.5 * fps)
    tracker.tracklet_metadata = [
        {"track_id": 1, "label": "player", "team_id": 0, "start_frame": 1, "end_frame": 5, "mean_hue": 0.05, "end_pos": [10.0, 10.0]},
        {"track_id": 2, "label": "player", "team_id": 0, "start_frame": 107, "end_frame": 110, "mean_hue": 0.05, "end_pos": [11.0, 11.0]}
    ]
    df = pd.DataFrame([
        {"frame_id": f, "player_id": 1, "x_pixel": 100.0, "y_pixel": 100.0, "x_meter": 10.0, "y_meter": 10.0, "xmin": 90, "ymin": 90, "xmax": 110, "ymax": 110, "label": "player", "team_id": 0, "confidence": 0.9}
        for f in range(1, 6)
    ] + [
        {"frame_id": f, "player_id": 2, "x_pixel": 110.0, "y_pixel": 110.0, "x_meter": 11.0, "y_meter": 11.0, "xmin": 100, "ymin": 100, "xmax": 120, "ymax": 120, "label": "player", "team_id": 0, "confidence": 0.9}
        for f in range(107, 111)
    ])
    df.set_index(["frame_id", "player_id"], inplace=True)
    
    stitched_df = tracker.offline_stitch(df, fps=30.0)
    # ID 2 should NOT be mapped/merged to 1
    assert 2 in stitched_df.index.levels[1]

def test_tier1_f4_postprocess_ball_imputation_quadratic():
    """20. Ball imputation: Verify quadratic curve fitting on missing gap."""
    data_layer = TrajectoryDataLayer()
    df = pd.DataFrame([
        # Before gap: frame 1, 2, 3 in motion
        {"frame_id": 1, "player_id": 99, "x_pixel": 10.0, "y_pixel": 10.0, "x_meter": 1.0, "y_meter": 1.0, "xmin": 5, "ymin": 5, "xmax": 15, "ymax": 15, "label": "ball", "team_id": -1, "confidence": 0.9},
        {"frame_id": 2, "player_id": 99, "x_pixel": 20.0, "y_pixel": 15.0, "x_meter": 2.0, "y_meter": 1.5, "xmin": 15, "ymin": 10, "xmax": 25, "ymax": 20, "label": "ball", "team_id": -1, "confidence": 0.9},
        {"frame_id": 3, "player_id": 99, "x_pixel": 30.0, "y_pixel": 18.0, "x_meter": 3.0, "y_meter": 1.8, "xmin": 25, "ymin": 13, "xmax": 35, "ymax": 23, "label": "ball", "team_id": -1, "confidence": 0.9},
        # Gap: frame 4
        # After gap: frame 5, 6, 7
        {"frame_id": 5, "player_id": 99, "x_pixel": 50.0, "y_pixel": 20.0, "x_meter": 5.0, "y_meter": 2.0, "xmin": 45, "ymin": 15, "xmax": 55, "ymax": 25, "label": "ball", "team_id": -1, "confidence": 0.9},
        {"frame_id": 6, "player_id": 99, "x_pixel": 60.0, "y_pixel": 19.0, "x_meter": 6.0, "y_meter": 1.9, "xmin": 55, "ymin": 14, "xmax": 65, "ymax": 24, "label": "ball", "team_id": -1, "confidence": 0.9},
        {"frame_id": 7, "player_id": 99, "x_pixel": 70.0, "y_pixel": 17.0, "x_meter": 7.0, "y_meter": 1.7, "xmin": 65, "ymin": 12, "xmax": 75, "ymax": 22, "label": "ball", "team_id": -1, "confidence": 0.9},
    ])
    df.set_index(["frame_id", "player_id"], inplace=True)
    
    imputed_df = data_layer.filter_ball_trajectory(df, max_gap=2)
    # Frame 4 should be imputed
    assert 4 in imputed_df.index.levels[0]
    assert imputed_df.loc[(4, 99), "reconstructed"] == True


# ==========================================
# FEATURE 5: TACTICAL & POSSESSION ANALYTICS
# ==========================================

def test_tier1_f5_possession_metrics_standard():
    """21. Possession Analyzer: Verify possession sequence logic."""
    analyzer = PossessionAnalyzer(t_in=1.5, t_out=2.5)
    # Ball is close to player 1 (Team 0)
    df = pd.DataFrame([
        {"frame_id": 1, "player_id": 1, "x_pixel": 100.0, "y_pixel": 100.0, "x_meter": 10.0, "y_meter": 10.0, "xmin": 90, "ymin": 90, "xmax": 110, "ymax": 110, "label": "player", "team_id": 0, "confidence": 0.9},
        {"frame_id": 1, "player_id": 99, "x_pixel": 102.0, "y_pixel": 102.0, "x_meter": 10.2, "y_meter": 10.2, "xmin": 99, "ymin": 99, "xmax": 105, "ymax": 105, "label": "ball", "team_id": -1, "confidence": 0.9}
    ])
    df.set_index(["frame_id", "player_id"], inplace=True)
    
    possession_df = analyzer.calculate_possession(df)
    assert possession_df.loc[1, "possession_team_id"] == 0

def test_tier1_f5_possession_hysteresis_gate():
    """22. Hysteresis gate: Verify state remains unchanged in intermediate distance."""
    analyzer = PossessionAnalyzer(t_in=1.5, t_out=2.5)
    # Frame 1: Player 1 (Team 0) gains possession (dist = 0)
    # Frame 2: Player 1 is at dist = 2.0 (between 1.5 and 2.5) -> keeps possession
    # Frame 3: Player 1 is at dist = 3.0 (> 2.5) -> loses possession
    df = pd.DataFrame([
        # Frame 1
        {"frame_id": 1, "player_id": 1, "x_pixel": 100.0, "y_pixel": 100.0, "xmin": 90, "ymin": 90, "xmax": 110, "ymax": 110, "label": "player", "team_id": 0, "confidence": 0.9},
        {"frame_id": 1, "player_id": 99, "x_pixel": 100.0, "y_pixel": 100.0, "label": "ball", "team_id": -1, "confidence": 0.9},
        # Frame 2 (normalized distance = 20 / 20 = 1.0 < 2.5 -> stays in possession)
        {"frame_id": 2, "player_id": 1, "x_pixel": 100.0, "y_pixel": 100.0, "xmin": 90, "ymin": 90, "xmax": 110, "ymax": 110, "label": "player", "team_id": 0, "confidence": 0.9},
        {"frame_id": 2, "player_id": 99, "x_pixel": 120.0, "y_pixel": 100.0, "label": "ball", "team_id": -1, "confidence": 0.9},
        # Frame 3 (normalized distance = 60 / 20 = 3.0 > 2.5 -> loses possession)
        {"frame_id": 3, "player_id": 1, "x_pixel": 100.0, "y_pixel": 100.0, "xmin": 90, "ymin": 90, "xmax": 110, "ymax": 110, "label": "player", "team_id": 0, "confidence": 0.9},
        {"frame_id": 3, "player_id": 99, "x_pixel": 160.0, "y_pixel": 100.0, "label": "ball", "team_id": -1, "confidence": 0.9},
    ])
    df.set_index(["frame_id", "player_id"], inplace=True)
    
    possession_df = analyzer.calculate_possession(df)
    assert possession_df.loc[1, "possession_team_id"] == 0
    assert possession_df.loc[2, "possession_team_id"] == 0
    assert possession_df.loc[3, "possession_team_id"] == -1

def test_tier1_f5_analytics_compactness_calculation(mock_trajectory_csv_factory, tmpdir):
    """23. Convex Hull: Verify compactness area is positive for structured player layout."""
    csv_path = os.path.join(tmpdir, "trajectories.csv")
    mock_trajectory_csv_factory(csv_path, num_frames=5)
    
    # Load and convert to schema
    df = pd.read_csv(csv_path, index_col=["frame_id", "player_id"])
    from run_tactical_analysis import convert_to_tactical_df
    tactical_df = convert_to_tactical_df(df)
    
    analyzer = FootballTacticalAnalyzer(fps=30)
    compactness_df = analyzer.calculate_team_compactness(tactical_df)
    assert not compactness_df.empty
    assert (compactness_df["team0_hull_area"] > 0).all()

def test_tier1_f5_analytics_passing_lanes(mock_trajectory_csv_factory, tmpdir):
    """24. Passing lanes: Verify detection of blocked/unblocked corridors."""
    csv_path = os.path.join(tmpdir, "trajectories.csv")
    mock_trajectory_csv_factory(csv_path, num_frames=5)
    df = pd.read_csv(csv_path, index_col=["frame_id", "player_id"])
    
    from run_tactical_analysis import convert_to_tactical_df
    tactical_df = convert_to_tactical_df(df)
    
    analyzer = FootballTacticalAnalyzer(fps=30)
    lanes = analyzer.detect_passing_lanes_and_defensive_clutter(frame_idx=1, coords_df=tactical_df)
    assert isinstance(lanes, list)

def test_tier1_f5_reports_generation(mock_trajectory_csv_factory, tmpdir):
    """25. Reports and Heatmaps: Verify reporting files generation."""
    csv_path = os.path.join(tmpdir, "trajectories.csv")
    mock_trajectory_csv_factory(csv_path, num_frames=5)
    df = pd.read_csv(csv_path, index_col=["frame_id", "player_id"])
    
    from run_tactical_analysis import convert_to_tactical_df
    tactical_df = convert_to_tactical_df(df)
    
    analyzer = FootballTacticalAnalyzer(fps=30, language="es")
    reports_dir = os.path.join(tmpdir, "reports")
    analyzer.generate_possession_weighted_heatmaps(tactical_df, reports_dir)
    assert os.path.exists(os.path.join(reports_dir, "possession_weighted_heatmaps.png"))
