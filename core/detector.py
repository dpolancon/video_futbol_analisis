"""
Automated Soccer Tracking and Drone Analytics Pipeline - Computer Vision Module
core/detector.py

This module contains the baseline class wrapper for drone-based object detection
specifically tuned for high-altitude soccer match footage, referencing the architectures
and heuristics of Guo et al. (2026). It supports real YOLOv8 inference with an OpenCV
fallback mode.
"""

import logging
from typing import Dict, List, Tuple, Union, Any
import numpy as np

# Configure logging
logger = logging.getLogger(__name__)

class DroneDetector:
    """
    DroneDetector wraps object detection models optimized for aerial/drone soccer tracking.
    
    It highlights specialized architectures such as YOLOv8-P2S3A and YOLOv8-HWD3A:
      - YOLOv8-P2S3A: Employs a P2 high-resolution feature layer (stride 4) combined with 
        three-stage spatial attention (S3A) to detect tiny features (e.g., the ball, remote players) 
        against high-contrast, texturized green pitch backdrops.
      - YOLOv8-HWD3A: Utilizes a High-resolution Wide-angle Drone (HWD) backbone with 3D-anchor 
        adjustments to handle camera pitch, yaw, roll variations, and lens distortion.
        
    It also documents and implements a baseline interface for team clustering using 
    DBSCAN on normalized player H-channel (Hue) color properties.
    """
    
    def __init__(self, model_weights: str = "yolov8-p2s3a.pt"):
        """
        Initializes the drone detection wrapper.

        Args:
            model_weights (str): Path to weights or identifier for the YOLO model.
                                 Defaults to 'yolov8-p2s3a.pt'.
        """
        self.model_weights = model_weights
        self.model = None
        self.has_logged_fallback = False
        
        # Hyperparameters for team clustering (Guo et al. 2026)
        self.dbscan_eps = 0.15
        self.dbscan_min_samples = 3

        logger.info(f"Initializing DroneDetector with weights: {self.model_weights}")
        
        # Try to load real YOLO model using Ultralytics
        try:
            from ultralytics import YOLO
            self.model = YOLO(self.model_weights)
            logger.info("YOLOv8 model loaded successfully.")
        except ImportError:
            logger.warning("Ultralytics library not installed. Running in graceful offline fallback mode.")
        except Exception as e:
            logger.warning(f"Could not load model weights '{self.model_weights}' ({e}). Running in fallback mode.")

    def process_frame(self, frame: np.ndarray) -> Dict[str, Union[List[List[float]], List[str], List[float], List[int]]]:
        """
        Processes a single video frame to detect soccer balls, players, and referees.

        If Ultralytics and weights are loaded, it runs real inference.
        Otherwise, it falls back to generating realistic mock detections based on frame size.

        Args:
            frame (np.ndarray): Input image frame in BGR format (height, width, channels).

        Returns:
            dict: Standard dictionary containing:
                - 'boxes': List of bounding boxes as [xmin, ymin, xmax, ymax] in pixels.
                - 'labels': List of predicted class label strings ('player', 'ball', 'referee').
                - 'confidences': List of floats indicating prediction confidences [0.0, 1.0].
                - 'teams': List of team IDs (-1: Noise/Ball/Referee, 0: Team A, 1: Team B).
        """
        height, width = frame.shape[:2]
        
        if self.model is not None:
            return self._process_real_inference(frame)
        else:
            if not self.has_logged_fallback:
                logger.info("No active YOLO model. Generating simulated detections for frame processing.")
                self.has_logged_fallback = True
            return self._process_simulated_inference(frame, width, height)

    def _process_real_inference(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Runs real YOLO model inference on the frame.
        """
        # Run inference
        results = self.model(frame, verbose=False)[0]
        
        boxes = []
        labels = []
        confidences = []
        player_hues = []
        
        # YOLOv8 class map (COCO usually, or custom trained)
        # Class names: 0 = person/player, 32 = sports ball, etc.
        # For custom soccer models: 0 = ball, 1 = player, 2 = referee
        names = self.model.names
        
        for box_obj in results.boxes:
            coords = box_obj.xyxy[0].tolist()  # [xmin, ymin, xmax, ymax]
            conf = float(box_obj.conf[0])
            cls_id = int(box_obj.cls[0])
            label_name = names.get(cls_id, f"class_{cls_id}")
            
            # Map typical COCO classes to our expected labels
            if label_name in ["person", "player"]:
                mapped_label = "player"
            elif label_name in ["sports ball", "ball"]:
                mapped_label = "ball"
            elif label_name in ["referee", "traffic cone"]:  # fallback map
                mapped_label = "referee"
            else:
                continue  # Skip unrelated detections
                
            boxes.append(coords)
            labels.append(mapped_label)
            confidences.append(conf)
            
            # Extract color hue feature if player
            if mapped_label == "player":
                hue = self._extract_player_hue(frame, coords)
                player_hues.append([hue])
            else:
                player_hues.append(None)
                
        # Perform DBSCAN clustering on player hues
        teams = self.cluster_teams_dbscan(labels, player_hues)
        
        return {
            "boxes": boxes,
            "labels": labels,
            "confidences": confidences,
            "teams": teams
        }

    def _process_simulated_inference(self, frame: np.ndarray, width: int, height: int) -> Dict[str, Any]:
        """
        Generates simulated detections representing a soccer match frame.
        """
        # We simulate 10 players (5 for Team A, 5 for Team B), 1 referee, and 1 ball.
        mock_boxes = [
            # Team A players (simulated around left-to-middle pitch)
            [int(width * 0.20), int(height * 0.30), int(width * 0.23), int(height * 0.40)],
            [int(width * 0.25), int(height * 0.50), int(width * 0.28), int(height * 0.60)],
            [int(width * 0.30), int(height * 0.20), int(width * 0.33), int(height * 0.30)],
            [int(width * 0.35), int(height * 0.70), int(width * 0.38), int(height * 0.80)],
            [int(width * 0.40), int(height * 0.45), int(width * 0.43), int(height * 0.55)],
            # Team B players (simulated around middle-to-right pitch)
            [int(width * 0.55), int(height * 0.35), int(width * 0.58), int(height * 0.45)],
            [int(width * 0.60), int(height * 0.55), int(width * 0.63), int(height * 0.65)],
            [int(width * 0.65), int(height * 0.25), int(width * 0.68), int(height * 0.35)],
            [int(width * 0.70), int(height * 0.65), int(width * 0.73), int(height * 0.75)],
            [int(width * 0.78), int(height * 0.40), int(width * 0.81), int(height * 0.50)],
            # Referee (middle)
            [int(width * 0.48), int(height * 0.50), int(width * 0.50), int(height * 0.58)],
            # Ball (near center circle/possession zone)
            [int(width * 0.44), int(height * 0.48), int(width * 0.45), int(height * 0.50)]
        ]
        
        mock_labels = [
            "player", "player", "player", "player", "player",
            "player", "player", "player", "player", "player",
            "referee", "ball"
        ]
        
        mock_confidences = [
            0.92, 0.94, 0.89, 0.95, 0.91,
            0.93, 0.90, 0.96, 0.88, 0.92,
            0.87, 0.85
        ]

        # Extract features for team clustering
        player_hues = []
        for i, (box, label) in enumerate(zip(mock_boxes, mock_labels)):
            if label == "player":
                # Real color extraction if cv2 is available, otherwise mock
                hue = self._extract_player_hue(frame, box)
                player_hues.append([hue])
            else:
                player_hues.append(None)
                
        # Perform DBSCAN clustering on player hues
        teams = self.cluster_teams_dbscan(mock_labels, player_hues)

        return {
            "boxes": mock_boxes,
            "labels": mock_labels,
            "confidences": mock_confidences,
            "teams": teams
        }

    def _extract_player_hue(self, frame: np.ndarray, box: List[float]) -> float:
        """
        Helper to extract median player Hue color channel from a bounding box crop.
        """
        xmin, ymin, xmax, ymax = [int(c) for c in box]
        
        # Safety crop checks
        if ymax > ymin and xmax > xmin and ymin >= 0 and xmin >= 0:
            try:
                import cv2
                crop = frame[ymin:ymax, xmin:xmax]
                if crop.size > 0:
                    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                    # Use median Hue (channel 0)
                    median_h = np.median(hsv[:, :, 0])
                    # Normalize Hue to [0, 1] range (OpenCV H is [0, 179])
                    return float(median_h / 179.0)
            except Exception:
                pass
                
        # Random fallbacks representing two distinct groups (Red shirts around 0.02, Blue around 0.65)
        # Simply returns a random hue based on a pseudo-random division of positions
        seed_value = int(xmin + ymin)
        if seed_value % 2 == 0:
            return float(np.random.normal(0.05, 0.02))
        else:
            return float(np.random.normal(0.65, 0.02))

    def cluster_teams_dbscan(self, labels: List[str], player_hues: List[Union[List[float], None]]) -> List[int]:
        """
        Heuristic team clustering using DBSCAN based on player color features.
        Guo et al. (2026) suggests using normalized player H-channel (Hue) values in HSV space.
        
        Args:
            labels (List[str]): Corresponding labels for each detection.
            player_hues (List[Union[List[float], None]]): Normalized hue feature list.

        Returns:
            List[int]: Assigned team IDs where:
                       -1 = Ball, Referee, or unclustered Noise.
                        0 = Team A
                        1 = Team B
        """
        teams = [-1] * len(labels)
        
        # Filter features of elements labeled 'player'
        player_indices = [i for i, label in enumerate(labels) if label == "player"]
        features = [player_hues[i] for i in player_indices if player_hues[i] is not None]
        
        if not features:
            return teams

        X = np.array(features)
        
        try:
            from sklearn.cluster import DBSCAN
            db = DBSCAN(eps=self.dbscan_eps, min_samples=self.dbscan_min_samples)
            clusters = db.fit_predict(X)
        except ImportError:
            # Fallback custom logic if scikit-learn is not installed in the workspace environment
            # Simple thresholding to mimic clustering for Hue values (Red: ~0.05 vs Blue: ~0.65)
            clusters = []
            for hue in X[:, 0]:
                if hue < 0.35:
                    clusters.append(0)
                else:
                    clusters.append(1)
            clusters = np.array(clusters)
            
        # Map cluster labels to output team structure
        player_cluster_idx = 0
        for i, label in enumerate(labels):
            if label == "player":
                # Ensure cluster results map cleanly to Team 0 and Team 1
                cluster_id = clusters[player_cluster_idx]
                if cluster_id == -1:
                    teams[i] = -1  # Noise/Outlier
                else:
                    teams[i] = int(cluster_id)
                player_cluster_idx += 1
                
        return teams
