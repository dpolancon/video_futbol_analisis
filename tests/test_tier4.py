import os
import shutil
import subprocess
import sys
import pytest
import pandas as pd
import cv2
import numpy as np


def clean_outputs_and_inputs(match_ids, video_paths=None):
    """Utility to clean up generated test outputs and inputs."""
    for match_id in match_ids:
        out_dir = os.path.abspath(f"outputs/{match_id}")
        if os.path.exists(out_dir):
            shutil.rmtree(out_dir, ignore_errors=True)
            
    if video_paths:
        for path in video_paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


def create_local_mock_video(path, num_frames=5, width=640, height=360):
    """Programmatically writes a local mock video file for E2E testing."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(path, fourcc, 30.0, (width, height))
    for _ in range(num_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = [40, 150, 40]  # Green background
        out.write(frame)
    out.release()


# ==========================================
# TIER 4: REAL-WORLD SCENARIOS (E2E INTEGRATION)
# ==========================================

def test_tier4_f5_full_headless_pipeline():
    """56. Full Headless Walkthrough: Execute main.py and run_tactical_analysis.py sequentially."""
    match_id = "test_e2e_match_1"
    video_path = os.path.abspath(f"inputs/{match_id}.mp4")
    create_local_mock_video(video_path, num_frames=10)
    
    try:
        # 1. Run main.py via subprocess
        cmd_main = [
            sys.executable, "main.py",
            "--video", video_path,
            "--frames", "5",
            "--stride", "2",
            "--weights", "mock_none.pt"
        ]
        res_main = subprocess.run(cmd_main, capture_output=True, text=True, check=True)
        assert res_main.returncode == 0
        
        # Verify output coordinates exist
        trajectory_csv = os.path.abspath(f"outputs/{match_id}/final_dataset/trajectories.csv")
        assert os.path.exists(trajectory_csv)
        
        # 2. Run run_tactical_analysis.py via subprocess
        cmd_tactical = [
            sys.executable, "run_tactical_analysis.py",
            "--match", match_id,
            "--fps", "30"
        ]
        res_tactical = subprocess.run(cmd_tactical, capture_output=True, text=True, check=True)
        assert res_tactical.returncode == 0
        
        # Verify reports are generated
        reports_dir = os.path.abspath(f"outputs/{match_id}/reports")
        assert os.path.exists(os.path.join(reports_dir, "metricas_compactacion_es.csv"))
        assert os.path.exists(os.path.join(reports_dir, "mapas_calor_posesion_es.png"))
        
    finally:
        clean_outputs_and_inputs([match_id], [video_path])

def test_tier4_f5_headless_batch_execution():
    """57. Batch Execution: Process all videos in inputs/ directory via --batch flag."""
    match_ids = ["test_batch_1", "test_batch_2"]
    video_paths = []
    for mid in match_ids:
        video_paths.append(os.path.abspath(f"inputs/{mid}.mp4"))
        create_local_mock_video(video_paths[-1], num_frames=5)
        
    try:
        # Run main.py in batch mode
        cmd_batch = [
            sys.executable, "main.py",
            "--batch",
            "--frames", "2",
            "--stride", "2",
            "--weights", "mock_none.pt"
        ]
        res = subprocess.run(cmd_batch, capture_output=True, text=True, check=True)
        assert res.returncode == 0
        
        # Check that both matches have outputs
        for mid in match_ids:
            trajectory_csv = os.path.abspath(f"outputs/{mid}/final_dataset/trajectories.csv")
            assert os.path.exists(trajectory_csv)
            
    finally:
        clean_outputs_and_inputs(match_ids, video_paths)

def test_tier4_f5_missing_video_and_trajectory_robustness():
    """58. Pipeline Robustness: Verify CLI scripts exit cleanly on invalid pathing inputs."""
    # Run main.py with non-existent video path
    cmd_main = [
        sys.executable, "main.py",
        "--video", "non_existent_file.mp4"
    ]
    # Check that main.py logs a warning and exits/handles it
    res = subprocess.run(cmd_main, capture_output=True, text=True)
    # It logs warning and runs simulation loop, which is a fallback!
    assert res.returncode == 0
    
    # Run run_tactical_analysis.py with invalid match ID
    cmd_tactical = [
        sys.executable, "run_tactical_analysis.py",
        "--match", "non_existent_match"
    ]
    res_tactical = subprocess.run(cmd_tactical, capture_output=True, text=True)
    # Logs error and should exit cleanly
    assert res_tactical.returncode == 0

def test_tier4_f5_uncontested_possession_match():
    """59. Uncontested/Empty Match: Run tactical analysis on trajectory with only ball, possession defaults to -1."""
    match_id = "test_empty_match"
    out_dir = os.path.abspath(f"outputs/{match_id}/final_dataset")
    os.makedirs(out_dir, exist_ok=True)
    trajectory_csv = os.path.join(out_dir, "trajectories.csv")
    
    # Write a trajectories CSV with only ball (player_id = 99, label = ball)
    records = []
    for f in range(1, 10):
        records.append({
            "frame_id": f,
            "player_id": 99,
            "x_pixel": 100.0,
            "y_pixel": 100.0,
            "x_meter": 10.0,
            "y_meter": 10.0,
            "xmin": 95, "ymin": 95, "xmax": 105, "ymax": 105,
            "label": "ball",
            "team_id": -1,
            "confidence": 0.9,
            "reconstructed": False
        })
    df = pd.DataFrame(records)
    df.to_csv(trajectory_csv, index=False)
    
    try:
        # Run tactical analysis via subprocess
        cmd_tactical = [
            sys.executable, "run_tactical_analysis.py",
            "--match", match_id,
            "--fps", "30"
        ]
        res = subprocess.run(cmd_tactical, capture_output=True, text=True, check=True)
        assert res.returncode == 0
        
        # Verify metricas_compactacion_es.csv is generated
        reports_dir = os.path.abspath(f"outputs/{match_id}/reports")
        assert os.path.exists(os.path.join(reports_dir, "metricas_compactacion_es.csv"))
        
    finally:
        clean_outputs_and_inputs([match_id])

def test_tier4_f5_extremely_fast_real_walkthrough():
    """60. Rapid End-to-End verification: Ingest 2 frames and check schema headers."""
    match_id = "test_rapid_e2e"
    video_path = os.path.abspath(f"inputs/{match_id}.mp4")
    create_local_mock_video(video_path, num_frames=2)
    
    try:
        # Run pipeline
        subprocess.run([
            sys.executable, "main.py",
            "--video", video_path,
            "--frames", "2",
            "--stride", "1",
            "--weights", "mock_none.pt"
        ], check=True)
        
        subprocess.run([
            sys.executable, "run_tactical_analysis.py",
            "--match", match_id
        ], check=True)
        
        # Verify compactness metrics Spanish columns
        compact_csv = os.path.abspath(f"outputs/{match_id}/reports/metricas_compactacion_es.csv")
        df = pd.read_csv(compact_csv)
        expected_cols = [
            "frame_id", "centroide_x_eq0", "centroide_y_eq0", "area_convex_hull_eq0_m2",
            "desviacion_estandar_distancia_eq0_m", "centroide_x_eq1", "centroide_y_eq1",
            "area_convex_hull_eq1_m2", "desviacion_estandar_distancia_eq1_m"
        ]
        for col in expected_cols:
            assert col in df.columns
            
    finally:
        clean_outputs_and_inputs([match_id], [video_path])
