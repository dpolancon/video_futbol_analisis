"""
Automated Soccer Tracking and Drone Analytics Pipeline - Computer Vision Module
core/tracker.py

This module contains a robust multi-object tracker incorporating Kalman filter motion 
models, Hungarian algorithm assignment, and offline tracklet Re-ID stitching.
"""

import logging
from typing import Dict, List, Tuple, Union, Any, Set
import numpy as np
from scipy.optimize import linear_sum_assignment

# Configure logging
logger = logging.getLogger(__name__)

class KalmanFilter2D:
    """
    Predicts player motion coordinates based on velocity vectors.
    Uses a constant velocity state space representation:
    State: X = [x, y, vx, vy]^T
    Measurement: Z = [x, y]^T
    """
    def __init__(self, dt: float = 1.0, initial_x: float = 0.0, initial_y: float = 0.0):
        # State vector: [x, y, vx, vy]
        self.x = np.array([initial_x, initial_y, 0.0, 0.0], dtype=np.float32)
        
        # State transition matrix
        self.F = np.array([
            [1.0, 0.0,  dt, 0.0],
            [0.0, 1.0, 0.0,  dt],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype=np.float32)
        
        # Measurement matrix (we only observe positions)
        self.H = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0]
        ], dtype=np.float32)
        
        # Covariance matrices
        self.P = np.eye(4, dtype=np.float32) * 10.0
        self.R = np.eye(2, dtype=np.float32) * 1.5   # Measurement noise
        self.Q = np.eye(4, dtype=np.float32) * 0.05  # Process noise

    def predict(self) -> Tuple[float, float]:
        """
        Predicts the next state of the Kalman Filter.
        """
        self.x = np.dot(self.F, self.x)
        self.P = np.dot(np.dot(self.F, self.P), self.F.T) + self.Q
        return float(self.x[0]), float(self.x[1])

    def update(self, z: Tuple[float, float]) -> None:
        """
        Updates the state vector with a new measurement z.
        """
        z_arr = np.array(z, dtype=np.float32)
        y = z_arr - np.dot(self.H, self.x)  # Innovation
        S = np.dot(np.dot(self.H, self.P), self.H.T) + self.R
        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(S))  # Kalman Gain
        
        self.x = self.x + np.dot(K, y)
        self.P = self.P - np.dot(np.dot(K, self.H), self.P)

class RobustDroneTracker:
    """
    RobustDroneTracker implements multi-object tracking using Kalman Filters 
    for motion predictions and the Hungarian algorithm for optimal associations.
    
    It enforces tracklet splits on high-IoU overlap to prevent identity swaps (Maglo et al. 2023)
    and contains a global offline stitching method to merge split tracklets using Re-ID similarity.
    """
    def __init__(self, max_lost_frames: int = 30, iou_threshold: float = 0.7):
        """
        Initializes the RobustDroneTracker.
        """
        self.max_lost_frames = max_lost_frames
        self.iou_threshold = iou_threshold
        
        self.next_track_id = 0
        self.tracks: Dict[int, Dict[str, Any]] = {}  # track_id -> track_properties
        self.frame_count = 0
        
        # Metadata caching for Re-ID stitching
        # Stores completed tracklets: {track_id, label, team_id, start_frame, end_frame, mean_hue, start_pos, end_pos}
        self.tracklet_metadata: List[Dict[str, Any]] = []
        
        # Internal cache for current active tracklets
        self.active_tracklet_hues: Dict[int, List[float]] = {}
        self.active_tracklet_start_frames: Dict[int, int] = {}
        
        logger.info(f"RobustDroneTracker initialized with iou_threshold={self.iou_threshold}")

    @staticmethod
    def calculate_iou(box1: List[float], box2: List[float]) -> float:
        """
        Computes the Intersection over Union (IoU) of two bounding boxes.
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

    def _archive_track(self, track_id: int) -> None:
        """
        Archives a completed tracklet into metadata cache.
        """
        track = self.tracks.pop(track_id, None)
        if track:
            team_id = track["team_id"]
            mean_hue = 0.05 if team_id == 0 else (0.65 if team_id == 1 else 0.35)
            self.tracklet_metadata.append({
                "track_id": track["track_id"],
                "label": track["label"],
                "team_id": team_id,
                "start_frame": track["start_frame"],
                "end_frame": track["end_frame"],
                "mean_hue": mean_hue,
                "end_pos": track["positions"][-1]
            })

    def update(self, detections: Dict[str, Union[List[List[float]], List[str], List[float], List[int]]]) -> List[int]:
        self.frame_count += 1
        boxes = detections.get("boxes", [])
        labels = detections.get("labels", [])
        confidences = detections.get("confidences", [])
        teams = detections.get("teams", [])
        
        assigned_ids = [-1] * len(boxes)
        
        # 1. Identify which detections are in conflict (collision)
        conflicts = [False] * len(boxes)
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                iou = self.calculate_iou(boxes[i], boxes[j])
                if iou >= self.iou_threshold:
                    logger.warning(
                        f"Collision detected between tracks {i} and {j} (IoU={iou:.2f}). Enforcing tracklet split."
                    )
                    conflicts[i] = True
                    conflicts[j] = True
                    
        # 2. Get predictions and increment lost frames
        active_track_ids = list(self.tracks.keys())
        predictions = {}
        for track_id in active_track_ids:
            predictions[track_id] = self.tracks[track_id]["kf"].predict()
            self.tracks[track_id]["lost_frames"] += 1
            
        # 3. Match non-conflict detections to active tracks
        non_conflict_indices = [i for i in range(len(boxes)) if not conflicts[i]]
        
        if active_track_ids and non_conflict_indices:
            cost_matrix = np.ones((len(active_track_ids), len(non_conflict_indices)), dtype=np.float32) * 1.0
            
            for row_idx, track_id in enumerate(active_track_ids):
                track = self.tracks[track_id]
                pred_pos = predictions[track_id]
                
                for col_idx, det_idx in enumerate(non_conflict_indices):
                    det_box = boxes[det_idx]
                    det_label = labels[det_idx]
                    det_team = teams[det_idx]
                    
                    if track["label"] != det_label:
                        continue
                        
                    det_centroid = [(det_box[0] + det_box[2]) / 2.0, (det_box[1] + det_box[3]) / 2.0]
                    dist = np.hypot(det_centroid[0] - pred_pos[0], det_centroid[1] - pred_pos[1])
                    
                    # Distance gate
                    if dist > 200.0:
                        continue
                        
                    iou = self.calculate_iou(track["box"], det_box)
                    
                    # Team compatibility
                    team_cost = 0.0 if track["team_id"] == det_team else 0.5
                    
                    # Compute cost
                    cost = 0.5 * (1.0 - iou) + 0.3 * (dist / 200.0) + 0.2 * team_cost
                    cost_matrix[row_idx, col_idx] = cost
                    
            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            
            matched_dets = set()
            matched_tracks = set()
            
            for r, c in zip(row_ind, col_ind):
                if cost_matrix[r, c] < 0.85:
                    track_id = active_track_ids[r]
                    det_idx = non_conflict_indices[c]
                    
                    # Update track properties
                    track = self.tracks[track_id]
                    det_box = boxes[det_idx]
                    det_centroid = [(det_box[0] + det_box[2]) / 2.0, (det_box[1] + det_box[3]) / 2.0]
                    
                    track["kf"].update(det_centroid)
                    track["lost_frames"] = 0
                    track["box"] = det_box
                    track["team_id"] = teams[det_idx]
                    track["end_frame"] = self.frame_count
                    track["positions"].append(det_centroid)
                    
                    assigned_ids[det_idx] = track_id
                    matched_dets.add(det_idx)
                    matched_tracks.add(track_id)
                    
        # 4. Handle unmatched non-conflict detections (start new tracks)
        for idx in non_conflict_indices:
            if assigned_ids[idx] == -1:
                det_box = boxes[idx]
                det_centroid = [(det_box[0] + det_box[2]) / 2.0, (det_box[1] + det_box[3]) / 2.0]
                
                new_id = self.next_track_id
                self.next_track_id += 1
                
                self.tracks[new_id] = {
                    "track_id": new_id,
                    "label": labels[idx],
                    "team_id": teams[idx],
                    "start_frame": self.frame_count,
                    "end_frame": self.frame_count,
                    "kf": KalmanFilter2D(initial_x=det_centroid[0], initial_y=det_centroid[1]),
                    "lost_frames": 0,
                    "box": det_box,
                    "positions": [det_centroid]
                }
                assigned_ids[idx] = new_id
                
        # 5. Handle conflict detections (terminate active tracks and start brand new immediately-archived tracklets)
        for idx in range(len(boxes)):
            if not conflicts[idx]:
                continue
                
            det_box = boxes[idx]
            det_centroid = [(det_box[0] + det_box[2]) / 2.0, (det_box[1] + det_box[3]) / 2.0]
            det_label = labels[idx]
            det_team = teams[idx]
            
            # Find and terminate close active tracks
            for track_id in list(self.tracks.keys()):
                track = self.tracks[track_id]
                if track["label"] == det_label:
                    pred_pos = predictions[track_id]
                    dist = np.hypot(det_centroid[0] - pred_pos[0], det_centroid[1] - pred_pos[1])
                    if dist < 150.0:
                        self._archive_track(track_id)
                        
            # Assign new track ID and add to archived tracklets
            new_id = self.next_track_id
            self.next_track_id += 1
            assigned_ids[idx] = new_id
            
            mean_hue = 0.05 if det_team == 0 else (0.65 if det_team == 1 else 0.35)
            self.tracklet_metadata.append({
                "track_id": new_id,
                "label": det_label,
                "team_id": det_team,
                "start_frame": self.frame_count,
                "end_frame": self.frame_count,
                "mean_hue": mean_hue,
                "end_pos": det_centroid
            })
            
        # 6. Archive lost tracks
        for track_id in list(self.tracks.keys()):
            if self.tracks[track_id]["lost_frames"] > self.max_lost_frames:
                self._archive_track(track_id)
                
        return assigned_ids

    def offline_stitch(self, trajectory_df: pd.DataFrame, fps: float) -> pd.DataFrame:
        if trajectory_df.empty:
            return trajectory_df
            
        # Archive all active tracks
        for track_id in list(self.tracks.keys()):
            self._archive_track(track_id)
            
        # Sort metadata by end_frame
        metadata = sorted(self.tracklet_metadata, key=lambda x: x["end_frame"])
        
        mapping = {}
        merged = set()
        
        for i in range(len(metadata)):
            t1 = metadata[i]
            t1_id = t1["track_id"]
            if t1_id in merged:
                continue
                
            best_j = -1
            best_cost = float('inf')
            
            for j in range(i + 1, len(metadata)):
                t2 = metadata[j]
                t2_id = t2["track_id"]
                if t2_id in merged or t2_id == t1_id:
                    continue
                    
                if t1["label"] != t2["label"] or t1["team_id"] != t2["team_id"]:
                    continue
                    
                gap = t2["start_frame"] - t1["end_frame"]
                if gap < 0 or gap > 2.5 * fps:
                    continue
                    
                hue_diff = abs(t1["mean_hue"] - t2["mean_hue"])
                if hue_diff > 0.1:
                    continue
                    
                pos1 = np.array(t1["end_pos"])
                pos2 = np.array(t2["end_pos"])
                dist = np.linalg.norm(pos1 - pos2)
                
                if dist > 50.0:
                    continue
                    
                cost = dist + gap * 0.1
                if cost < best_cost:
                    best_cost = cost
                    best_j = j
                    
            if best_j != -1:
                t2 = metadata[best_j]
                t2_id = t2["track_id"]
                
                root_id = mapping.get(t1_id, t1_id)
                mapping[t2_id] = root_id
                merged.add(t2_id)
                
                t1["end_frame"] = t2["end_frame"]
                t1["end_pos"] = t2["end_pos"]
                
        if mapping:
            logger.info(f"Offline stitching merged {len(merged)} fragmented player tracklet identities.")
            df_reset = trajectory_df.reset_index()
            df_reset["player_id"] = df_reset["player_id"].map(lambda pid: mapping.get(pid, pid))
            trajectory_df = df_reset.set_index(["frame_id", "player_id"]).sort_index()
        else:
            logger.info("No fragmented tracklets were merged during offline stitching.")
            
        return trajectory_df
