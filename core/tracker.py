"""
Automated Soccer Tracking and Drone Analytics Pipeline - Computer Vision Module
core/tracker.py

This module contains the multi-object tracking skeleton incorporating offline tracklet split
heuristics based on the paradigms of Maglo et al. (2023).
"""

import logging
from typing import Dict, List, Tuple, Union, Set
import numpy as np

# Configure logging
logger = logging.getLogger(__name__)

class DroneTracker:
    """
    DroneTracker tracks detected soccer players and the ball across frames.
    
    It incorporates the offline tracklet split metrics from Maglo et al. (2023). 
    Instead of allowing ambiguous associations during player-to-player crossovers 
    (which cause identity swaps), the tracker forces an intentional tracklet break 
    when the Intersection-over-Union (IoU) of two tracked entities exceeds a critical threshold.
    These fractured, high-purity tracklets are saved to be stitched later by downstream 
    appearance-based Re-ID merge routines.
    """
    
    def __init__(self, iou_threshold: float = 0.7):
        """
        Initializes the DroneTracker.

        Args:
            iou_threshold (float): Overlap threshold above which tracklets are broken 
                                   due to spatial ambiguity. Default is 0.7.
        """
        self.iou_threshold = iou_threshold
        self.next_track_id = 0
        self.active_tracks: Dict[int, Dict[str, Union[List[float], str, int]]] = {}
        # Keep track of tracklets that were broken intentionally for Re-ID merging documentation
        self.split_history: List[Dict[str, Union[int, List[float]]]] = []
        logger.info(f"DroneTracker initialized with iou_threshold={self.iou_threshold}")

    @staticmethod
    def calculate_iou(box1: List[float], box2: List[float]) -> float:
        """
        Computes the Intersection over Union (IoU) of two bounding boxes.

        Args:
            box1 (List[float]): Bounding box [xmin, ymin, xmax, ymax].
            box2 (List[float]): Bounding box [xmin, ymin, xmax, ymax].

        Returns:
            float: IoU value between 0.0 and 1.0.
        """
        x_left = max(box1[0], box2[0])
        y_top = max(box1[1], box2[1])
        x_right = min(box1[2], box2[2])
        y_bottom = min(box1[3], box2[3])

        if x_right < x_left or y_bottom < y_top:
            return 0.0

        intersection_area = (x_right - x_left) * (y_bottom - y_top)
        
        box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
        box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
        
        union_area = float(box1_area + box2_area - intersection_area)
        if union_area == 0:
            return 0.0
            
        return intersection_area / union_area

    def update(self, detections: Dict[str, Union[List[List[float]], List[str], List[float], List[int]]]) -> List[int]:
        """
        Updates tracking states with new frame detections.
        
        Enforces Maglo et al. (2023)'s offline tracklet split paradigm:
        If two targets have overlapping bounding boxes where IoU >= iou_threshold,
        we terminate the old tracklets and assign new ones. This avoids identity leaks
        and prepares the data for global Re-ID optimization downstream.

        Args:
            detections (dict): Detector outputs containing 'boxes', 'labels', 'confidences', 'teams'.

        Returns:
            List[int]: Assigned track IDs for each box in the current frame.
        """
        boxes = detections["boxes"]
        labels = detections["labels"]
        confidences = detections["confidences"]
        teams = detections["teams"]
        
        assigned_track_ids = [-1] * len(boxes)
        
        # 1. Detect spatial overlap conflicts between current detections
        # If two detections are too close, they trigger a tracklet split warning.
        conflict_indices: Set[int] = set()
        
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                iou = self.calculate_iou(boxes[i], boxes[j])
                if iou >= self.iou_threshold:
                    logger.warning(
                        f"Tracklet collision detected between detections {i} and {j} (IoU={iou:.2f}). "
                        f"Enforcing intentional tracklet break according to Maglo et al. (2023)."
                    )
                    conflict_indices.add(i)
                    conflict_indices.add(j)

        # 2. Match current detections with active tracks
        # For simplicity in this offline skeleton, we match based on proximity (Euclidean distance of centroids)
        new_active_tracks = {}
        
        for idx, (box, label, conf, team) in enumerate(zip(boxes, labels, confidences, teams)):
            centroid = [(box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0]
            
            # Check if this index was flagged for an intentional split
            is_split = idx in conflict_indices
            
            best_track_id = -1
            best_dist = float('inf')
            
            # Match only if not flagged for splitting
            if not is_split:
                for track_id, track_info in self.active_tracks.items():
                    if track_info["label"] != label:
                        continue
                    
                    last_box = track_info["box"]
                    last_centroid = [(last_box[0] + last_box[2]) / 2.0, (last_box[1] + last_box[3]) / 2.0]
                    dist = np.hypot(centroid[0] - last_centroid[0], centroid[1] - last_centroid[1])
                    
                    # Accept match if within a maximum pixel displacement (e.g., 100 pixels)
                    if dist < 100.0 and dist < best_dist:
                        best_dist = dist
                        best_track_id = track_id

            if best_track_id != -1:
                # Update existing track
                assigned_track_ids[idx] = best_track_id
                new_active_tracks[best_track_id] = {
                    "box": box,
                    "label": label,
                    "confidence": conf,
                    "team": team
                }
            else:
                # Create a new tracklet ID
                new_id = self.next_track_id
                self.next_track_id += 1
                assigned_track_ids[idx] = new_id
                new_active_tracks[new_id] = {
                    "box": box,
                    "label": label,
                    "confidence": conf,
                    "team": team
                }
                
                if is_split:
                    self.split_history.append({
                        "frame_track_id": new_id,
                        "box": box,
                        "reason": "intentional_iou_split"
                    })
                    logger.debug(f"Forced creation of broken tracklet {new_id} to ensure tracklet purity.")

        self.active_tracks = new_active_tracks
        return assigned_track_ids
