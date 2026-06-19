import os
import sys
import cv2
import numpy as np
import subprocess

def create_local_mock_video(path, num_frames=5, width=640, height=360):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(path, fourcc, 30.0, (width, height))
    for _ in range(num_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = [40, 150, 40]
        out.write(frame)
    out.release()

def test_batch():
    match_ids = ["test_batch_1", "test_batch_2"]
    video_paths = []
    for mid in match_ids:
        path = os.path.abspath(f"inputs/{mid}.mp4")
        video_paths.append(path)
        create_local_mock_video(path, num_frames=5)
        print(f"Created video: {path}, exists={os.path.exists(path)}")

    cmd_batch = [
        sys.executable, "main.py",
        "--batch",
        "--frames", "2",
        "--stride", "2",
        "--weights", "mock_none.pt"
    ]
    res = subprocess.run(cmd_batch, capture_output=True, text=True)
    print("EXIT CODE:", res.returncode)
    print("STDOUT:\n", res.stdout)
    print("STDERR:\n", res.stderr)

    for mid in match_ids:
        trajectory_csv = os.path.abspath(f"outputs/{mid}/final_dataset/trajectories.csv")
        print(f"File {trajectory_csv} exists: {os.path.exists(trajectory_csv)}")

if __name__ == "__main__":
    test_batch()
