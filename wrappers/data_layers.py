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
