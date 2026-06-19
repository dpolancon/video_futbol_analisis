import os
import shutil
import pytest
import cv2
import numpy as np
import pandas as pd

@pytest.fixture
def temp_dir(tmp_path):
    """Fixture to provide a clean temporary directory for test file operations."""
    return str(tmp_path)

@pytest.fixture
def mock_video_factory(tmp_path):
    """Fixture to programmatically generate tiny mock video files for testing."""
    def _create_video(name="mock_match.mp4", num_frames=10, width=640, height=360, color=(40, 150, 40)):
        video_path = os.path.join(tmp_path, name)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(video_path, fourcc, 30.0, (width, height))
        for _ in range(num_frames):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            frame[:, :] = color  # Green pitch color by default
            # Draw center circle to mimic pitch
            cv2.circle(frame, (width // 2, height // 2), 50, (255, 255, 255), 2)
            out.write(frame)
        out.release()
        return video_path
    return _create_video

@pytest.fixture
def mock_trajectory_csv_factory():
    """Fixture to write mock trajectory CSV files with realistic soccer positions."""
    def _create_csv(filepath, num_frames=10, has_ball=True, num_players=10):
        records = []
        for f in range(1, num_frames + 1):
            # Players: Team 0
            for p_id in range(num_players // 2):
                records.append({
                    "frame_id": f,
                    "player_id": p_id,
                    "x_pixel": float(100 + p_id * 30 + f * 2),
                    "y_pixel": float(150 + p_id * 20 + (p_id % 2) * 20),
                    "x_meter": float(10 + p_id * 5 + f * 0.1),
                    "y_meter": float(15 + p_id * 4 + (p_id % 2) * 5),
                    "xmin": float(90 + p_id * 30 + f * 2),
                    "ymin": float(130 + p_id * 20 + (p_id % 2) * 20),
                    "xmax": float(110 + p_id * 30 + f * 2),
                    "ymax": float(170 + p_id * 20 + (p_id % 2) * 20),
                    "label": "player",
                    "team_id": 0,
                    "confidence": 0.90,
                    "reconstructed": False
                })
            # Players: Team 1
            for p_id in range(num_players // 2, num_players):
                records.append({
                    "frame_id": f,
                    "player_id": p_id,
                    "x_pixel": float(400 + (p_id - 5) * 30 - f * 2),
                    "y_pixel": float(200 + (p_id - 5) * 20 + (p_id % 2) * 20),
                    "x_meter": float(60 + (p_id - 5) * 5 - f * 0.1),
                    "y_meter": float(25 + (p_id - 5) * 4 + (p_id % 2) * 5),
                    "xmin": float(390 + (p_id - 5) * 30 - f * 2),
                    "ymin": float(180 + (p_id - 5) * 20 + (p_id % 2) * 20),
                    "xmax": float(410 + (p_id - 5) * 30 - f * 2),
                    "ymax": float(220 + (p_id - 5) * 20 + (p_id % 2) * 20),
                    "label": "player",
                    "team_id": 1,
                    "confidence": 0.92,
                    "reconstructed": False
                })
            # Ball
            if has_ball:
                records.append({
                    "frame_id": f,
                    "player_id": 99,
                    "x_pixel": float(250 + f * 5),
                    "y_pixel": float(180 + f * 3),
                    "x_meter": float(35 + f * 0.2),
                    "y_meter": float(20 + f * 0.15),
                    "xmin": float(245 + f * 5),
                    "ymin": float(175 + f * 3),
                    "xmax": float(255 + f * 5),
                    "ymax": float(185 + f * 3),
                    "label": "ball",
                    "team_id": -1,
                    "confidence": 0.88,
                    "reconstructed": False
                })
        
        df = pd.DataFrame(records)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        df.to_csv(filepath, index=False)
        return filepath
    return _create_csv
