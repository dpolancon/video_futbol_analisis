"""
Automated Soccer Tracking and Drone Analytics Pipeline - Data Abstraction Layer
wrappers/data_layers.py

This module contains data abstraction layers inspired by SportsLabKit patterns,
converting raw CV trackers outputs into highly structured, serialized Pandas DataFrames.
"""

import os
import logging
from typing import Dict, List, Tuple, Union, Any
import pandas as pd
import numpy as np
from core.homography import PitchRegistrator

# Configure logging
logger = logging.getLogger(__name__)

class TrajectoryDataLayer:
    """
    TrajectoryDataLayer manages tracking data serialization and packaging.
    
    It accepts raw multi-object tracking dictionary representations per frame, projects 
    the pixel locations onto the physical pitch coordinates in meters, and aggregates 
    them into a Pandas DataFrame utilizing a MultiIndex: (frame_id, player_id).
    
    This structured indexing allows seamless filtering, feature engineering, and offline
    downstream analytics (e.g., possession analysis, speed calculations) to be conducted.
    """
    
    def __init__(self, registrator: PitchRegistrator = None):
        """
        Initializes the TrajectoryDataLayer.

        Args:
            registrator (PitchRegistrator, optional): Registrator instance used to convert
                                                      pixels to meters. If None, instantiates a default.
        """
        self.registrator = registrator if registrator is not None else PitchRegistrator()
        # Internal store for frame-by-frame data
        self.records: List[Dict[str, Any]] = []
        logger.info("TrajectoryDataLayer initialized.")

    def add_frame_data(
        self, 
        frame_id: int, 
        track_ids: List[int], 
        detections: Dict[str, Union[List[List[float]], List[str], List[float], List[int]]],
        homography_matrix: np.ndarray = None
    ) -> None:
        """
        Ingests tracking data from a single frame, processes coordinates, and stores them.

        Args:
            frame_id (int): Incremental frame ID.
            track_ids (List[int]): Track IDs returned by the tracker corresponding to detections.
            detections (dict): Dict containing 'boxes', 'labels', 'confidences', and 'teams'.
            homography_matrix (np.ndarray, optional): 3x3 projection matrix.
        """
        boxes = detections["boxes"]
        labels = detections["labels"]
        confidences = detections["confidences"]
        teams = detections["teams"]
        
        for idx, (track_id, box, label, confidence, team) in enumerate(zip(track_ids, boxes, labels, confidences, teams)):
            # 1. Determine local position representing the coordinate point.
            # For players, the foot-contact point is most accurate for homography: bottom-middle of the box.
            # For the ball, the center point is more representative.
            xmin, ymin, xmax, ymax = box
            if label == "ball":
                x_pixel = (xmin + xmax) / 2.0
                y_pixel = (ymin + ymax) / 2.0
            else:
                x_pixel = (xmin + xmax) / 2.0
                y_pixel = float(ymax)  # Foot level contact with pitch
                
            # 2. Map coordinates from image space to pitch meters
            x_meter, y_meter = self.registrator.pixel_to_meters(x_pixel, y_pixel, homography_matrix)
            
            # Store structured record
            self.records.append({
                "frame_id": frame_id,
                "player_id": track_id,
                "x_pixel": x_pixel,
                "y_pixel": y_pixel,
                "x_meter": x_meter,
                "y_meter": y_meter,
                "xmin": xmin,
                "ymin": ymin,
                "xmax": xmax,
                "ymax": ymax,
                "label": label,
                "team_id": team,
                "confidence": confidence
            })
            
        logger.debug(f"Ingested {len(boxes)} records for frame {frame_id} into DataLayer.")

    def to_dataframe(self) -> pd.DataFrame:
        """
        Converts the stored records into a MultiIndexed Pandas DataFrame.

        Returns:
            pd.DataFrame: A DataFrame with:
                          - Index: MultiIndex containing levels ('frame_id', 'player_id')
                          - Columns: ['x_pixel', 'y_pixel', 'x_meter', 'y_meter', 
                                      'xmin', 'ymin', 'xmax', 'ymax', 'label', 'team_id', 'confidence']
        """
        if not self.records:
            # Return empty DataFrame with the specified structure if no records exist
            index = pd.MultiIndex.from_tuples([], names=["frame_id", "player_id"])
            cols = [
                "x_pixel", "y_pixel", "x_meter", "y_meter", 
                "xmin", "ymin", "xmax", "ymax", "label", "team_id", "confidence"
            ]
            return pd.DataFrame(index=index, columns=cols)
            
        # Create plain DataFrame
        df = pd.DataFrame(self.records)
        
        # Set MultiIndex structure
        df.set_index(["frame_id", "player_id"], inplace=True)
        df.sort_index(inplace=True)
        
        return df

    def save_to_parquet(self, filepath: str) -> None:
        """
        Serializes the tracking dataset to a binary Parquet file.
        If pyarrow/fastparquet is not available, logs a warning and skips.

        Args:
            filepath (str): Absolute file path to output target.
        """
        df = self.to_dataframe()
        
        # Ensure parent directories exist
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        try:
            # Parquet natively supports MultiIndexed DataFrames in modern pandas versions
            df.to_parquet(filepath, index=True)
            logger.info(f"Trajectory dataset successfully saved as Parquet: {filepath}")
        except ImportError as e:
            logger.warning(
                f"Skipping Parquet serialization: pyarrow or fastparquet is not installed. "
                f"Details: {e}"
            )


    def save_to_csv(self, filepath: str) -> None:
        """
        Serializes the tracking dataset to a comma-separated values (CSV) file.

        Args:
            filepath (str): Absolute file path to output target.
        """
        df = self.to_dataframe()
        
        # Ensure parent directories exist
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        df.to_csv(filepath, index=True)
        logger.info(f"Trajectory dataset successfully saved as CSV: {filepath}")

    def filter_ball_trajectory(self, trajectory_df: pd.DataFrame, max_gap: int = 30) -> pd.DataFrame:
        """
        Post-processing filter to interpolate ball coordinate gaps using sliding-window 
        parabolic (quadratic) curve fitting.

        Args:
            trajectory_df (pd.DataFrame): Coordinates DataFrame indexed by (frame_id, player_id).
            max_gap (int): Maximum consecutive frames missing to attempt interpolation. Default is 30.

        Returns:
            pd.DataFrame: Cleaned and back-filled trajectories DataFrame.
        """
        if trajectory_df.empty:
            return trajectory_df

        df_flat = trajectory_df.reset_index()
        
        # Ensure 'reconstructed' column exists
        if "reconstructed" not in df_flat.columns:
            df_flat["reconstructed"] = False
            
        # Get all ball detections
        ball_df = df_flat[df_flat["label"] == "ball"].sort_values("frame_id")
        
        if ball_df.empty:
            logger.info("No ball detections found in trajectories. Skipping ball trajectory interpolation.")
            trajectory_df["reconstructed"] = False
            return trajectory_df
            
        # Get min and max frames in the dataset
        min_frame = int(df_flat["frame_id"].min())
        max_frame = int(df_flat["frame_id"].max())
        
        # Get the track ID used for the ball
        ball_track_id = int(ball_df.iloc[0]["player_id"])
        
        # Create a dict of known ball positions: frame_id -> row_dict
        known_ball = {int(row["frame_id"]): row.to_dict() for _, row in ball_df.iterrows()}
        
        imputed_rows = []
        
        # Find gaps and interpolate
        # We loop from min_frame to max_frame
        frame_idx = min_frame
        
        while frame_idx <= max_frame:
            if frame_idx in known_ball:
                frame_idx += 1
                continue
                
            # We found the start of a gap!
            gap_start = frame_idx
            while frame_idx <= max_frame and frame_idx not in known_ball:
                frame_idx += 1
            gap_end = frame_idx - 1
            
            gap_len = gap_end - gap_start + 1
            
            # Interpolate only if gap length is within threshold and bounded on both sides
            if gap_len <= max_gap and (gap_start - 1) in known_ball and (gap_end + 1) in known_ball:
                logger.info(f"Interpolating ball trajectory gap from frame {gap_start} to {gap_end} (length={gap_len} frames)")
                
                # Gather context windows on both sides of the gap (up to 7 frames before and after)
                left_window = [gap_start - k for k in range(1, 8) if (gap_start - k) in known_ball]
                right_window = [gap_end + k for k in range(1, 8) if (gap_end + k) in known_ball]
                
                context_frames = sorted(left_window + right_window)
                
                if len(context_frames) >= 3:
                    # Fit a quadratic/parabolic curve (degree 2) for ballistic motion
                    t_fit = np.array(context_frames, dtype=np.float32)
                    x_fit = np.array([known_ball[f]["x_meter"] for f in context_frames], dtype=np.float32)
                    y_fit = np.array([known_ball[f]["y_meter"] for f in context_frames], dtype=np.float32)
                    
                    x_px_fit = np.array([known_ball[f]["x_pixel"] for f in context_frames], dtype=np.float32)
                    y_px_fit = np.array([known_ball[f]["y_pixel"] for f in context_frames], dtype=np.float32)
                    
                    poly_x = np.polyfit(t_fit, x_fit, 2)
                    poly_y = np.polyfit(t_fit, y_fit, 2)
                    
                    poly_x_px = np.polyfit(t_fit, x_px_fit, 2)
                    poly_y_px = np.polyfit(t_fit, y_px_fit, 2)
                else:
                    # Fallback to linear interpolation (degree 1) if not enough points
                    t_fit = np.array([gap_start - 1, gap_end + 1], dtype=np.float32)
                    x_fit = np.array([known_ball[gap_start - 1]["x_meter"], known_ball[gap_end + 1]["x_meter"]], dtype=np.float32)
                    y_fit = np.array([known_ball[gap_start - 1]["y_meter"], known_ball[gap_end + 1]["y_meter"]], dtype=np.float32)
                    
                    x_px_fit = np.array([known_ball[gap_start - 1]["x_pixel"], known_ball[gap_end + 1]["x_pixel"]], dtype=np.float32)
                    y_px_fit = np.array([known_ball[gap_start - 1]["y_pixel"], known_ball[gap_end + 1]["y_pixel"]], dtype=np.float32)
                    
                    poly_x = np.polyfit(t_fit, x_fit, 1)
                    poly_y = np.polyfit(t_fit, y_fit, 1)
                    
                    poly_x_px = np.polyfit(t_fit, x_px_fit, 1)
                    poly_y_px = np.polyfit(t_fit, y_px_fit, 1)
                
                # Reconstruct coordinates for the gap
                for t in range(gap_start, gap_end + 1):
                    # Compute coordinates
                    x_m = float(np.polyval(poly_x, t))
                    y_m = float(np.polyval(poly_y, t))
                    
                    x_px = float(np.polyval(poly_x_px, t))
                    y_px = float(np.polyval(poly_y_px, t))
                    
                    # Clamp to physical pitch boundaries to prevent projection outliers
                    x_m = np.clip(x_m, 0.0, 105.0)
                    y_m = np.clip(y_m, 0.0, 68.0)
                    
                    # Draw dummy bounding boxes representing reconstructed coordinates
                    half_w = 10.0  # mock 10px ball size
                    xmin = max(0.0, x_px - half_w)
                    ymin = max(0.0, y_px - half_w)
                    xmax = x_px + half_w
                    ymax = y_px + half_w
                    
                    imputed_rows.append({
                        "frame_id": int(t),
                        "player_id": ball_track_id,
                        "x_pixel": float(x_px),
                        "y_pixel": float(y_px),
                        "x_meter": float(x_m),
                        "y_meter": float(y_m),
                        "xmin": float(xmin),
                        "ymin": float(ymin),
                        "xmax": float(xmax),
                        "ymax": float(ymax),
                        "label": "ball",
                        "team_id": -1,
                        "confidence": 0.3,  # flagged low confidence for reconstructed state
                        "reconstructed": True
                    })
            
            frame_idx += 1
            
        if imputed_rows:
            df_imputed = pd.DataFrame(imputed_rows)
            df_flat = pd.concat([df_flat, df_imputed], ignore_index=True)
            
        # Re-set indices
        df_flat.set_index(["frame_id", "player_id"], inplace=True)
        df_flat.sort_index(inplace=True)
        
        logger.info(f"Ball trajectory filtering complete. Imputed {len(imputed_rows)} missing ball coordinates.")
        return df_flat

