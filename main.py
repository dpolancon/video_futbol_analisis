"""
Automated Soccer Tracking and Drone Analytics Pipeline - Orchestration Entrypoint
main.py

This script coordinates the soccer video tracking pipeline, loading components 
sequentially and orchestrating the data flow from raw video to downstream analytical insights.
"""

import os
import argparse
import logging
import numpy as np
import pandas as pd

# Pipeline imports
from core.detector import DroneDetector
from core.tracker import DroneTracker
from core.homography import PitchRegistrator
from wrappers.data_layers import TrajectoryDataLayer
import analytics

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("pipeline_orchestrator")

def parse_arguments() -> argparse.Namespace:
    """
    Parses command-line arguments.

    Returns:
        argparse.Namespace: Object containing argument values.
    """
    parser = argparse.ArgumentParser(
        description="Automated Offline Soccer Tracking and Drone Analytics Data Pipeline"
    )
    parser.add_argument(
        "--video", "-v",
        type=str,
        required=True,
        help="Path to the input raw mp4 video asset (e.g., inputs/match_01.mp4)"
    )
    parser.add_argument(
        "--frames", "-f",
        type=int,
        default=30,
        help="Number of simulated/processed frames to run. Default is 30."
    )
    parser.add_argument(
        "--iou-threshold",
        type=float,
        default=0.7,
        help="Tracker overlapping bounding box IoU threshold. Default is 0.7."
    )
    return parser.parse_args()

def setup_pipeline_directories(match_id: str) -> Dict[str, str]:
    """
    Creates structural output directories for intermediate pipeline deliverables.

    Args:
        match_id (str): Derived ID of the match from the video file name.

    Returns:
        Dict[str, str]: Dictionary mapping directory keys to their absolute path strings.
    """
    base_output_dir = os.path.abspath(f"outputs/{match_id}")
    
    subdirs = {
        "base": base_output_dir,
        "raw_detections": os.path.join(base_output_dir, "raw_detections"),
        "tracklets": os.path.join(base_output_dir, "tracklets"),
        "calibration": os.path.join(base_output_dir, "calibration"),
        "final_dataset": os.path.join(base_output_dir, "final_dataset"),
        "reports": os.path.join(base_output_dir, "reports")
    }
    
    for name, path in subdirs.items():
        os.makedirs(path, exist_ok=True)
        logger.info(f"Directory verified/created: {path}")
        
    return subdirs

def main() -> None:
    """
    Main pipeline execution flow.
    """
    args = parse_arguments()
    
    # 1. Parse video and derive match ID
    video_path = args.video
    video_filename = os.path.basename(video_path)
    match_id = os.path.splitext(video_filename)[0]
    
    logger.info("=" * 60)
    logger.info(f"Starting Soccer Tracking Pipeline for Match: {match_id}")
    logger.info(f"Target Video Path: {video_path}")
    logger.info("=" * 60)
    
    # 2. Setup output directories
    output_dirs = setup_pipeline_directories(match_id)
    
    # 3. Initialize components
    logger.info("Initializing core pipeline modules...")
    detector = DroneDetector()
    tracker = DroneTracker(iou_threshold=args.iou_threshold)
    registrator = PitchRegistrator()
    data_layer = TrajectoryDataLayer(registrator=registrator)
    
    # Define a simulated homography calibration matrix (e.g. from manual anchors)
    # This matrix would normally be saved in the calibration subdirectory
    calibration_matrix = registrator.default_homography
    calibration_file = os.path.join(output_dirs["calibration"], "homography_matrix.npy")
    np.save(calibration_file, calibration_matrix)
    logger.info(f"Saved homography calibration parameters to {calibration_file}")

    # 4. Processing Loop (Simulating offline video decoding frame-by-frame)
    logger.info(f"Processing {args.frames} video frames...")
    
    # Simulate a typical 1080p frame
    height, width = 1080, 1920
    dummy_frame = np.zeros((height, width, 3), dtype=np.uint8)
    
    for frame_id in range(1, args.frames + 1):
        # In a real deployment, we would decode using:
        # ret, frame = video_capture.read()
        
        # A: Run Drone Detection
        detections = detector.process_frame(dummy_frame)
        
        # B: Run multi-object tracker with collision metrics splits
        track_ids = tracker.update(detections)
        
        # C: Feed current outputs into the SportsLabKit data layer
        data_layer.add_frame_data(
            frame_id=frame_id, 
            track_ids=track_ids, 
            detections=detections, 
            homography_matrix=calibration_matrix
        )
        
        # Occasionally log progress
        if frame_id % 10 == 0 or frame_id == args.frames:
            logger.info(f"Frame {frame_id}/{args.frames} completed.")

    # 5. Build final structured trajectory DataFrame
    logger.info("Serializing processed trajectory records...")
    
    csv_out_path = os.path.join(output_dirs["final_dataset"], "trajectories.csv")
    parquet_out_path = os.path.join(output_dirs["final_dataset"], "trajectories.parquet")
    
    data_layer.save_to_csv(csv_out_path)
    data_layer.save_to_parquet(parquet_out_path)
    
    trajectory_df = data_layer.to_dataframe()
    logger.info(f"Structured trajectory dataset generated: {trajectory_df.shape[0]} total tracklet points.")
    
    # 6. Execute Downstream Analytics Skill (Decoupled execution)
    logger.info("Triggering decoupled analytics phase...")
    try:
        # Load the registered 'possession' skill dynamically
        PossessionClass = analytics.get_skill("possession")
        possession_analyzer = PossessionClass(t_in=1.5, t_out=2.5)
        
        logger.info("Calculating time-series possession metrics...")
        possession_summary_df = possession_analyzer.calculate_possession(trajectory_df)
        
        # Save analysis reports
        report_path = os.path.join(output_dirs["reports"], "possession_summary.csv")
        possession_summary_df.to_csv(report_path)
        logger.info(f"Possession summary report written to: {report_path}")
        
        # Compute and output possession percentages for printout
        team_possessions = possession_summary_df["possession_team_id"].value_counts(normalize=True) * 100
        logger.info("=" * 60)
        logger.info("PIPELINE EXECUTION SUMMARY & STATISTICS:")
        logger.info("=" * 60)
        for team, pct in team_possessions.items():
            team_label = "Uncontested/Ball-Out" if team == -1 else f"Team {int(team)}"
            logger.info(f" -> Possession {team_label}: {pct:.2f}%")
        logger.info("=" * 60)
        
    except KeyError as e:
        logger.error(f"Downstream skill processing failed: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error in downstream analytics skill execution: {e}")

    logger.info("Pipeline run successfully completed.")

if __name__ == "__main__":
    main()
