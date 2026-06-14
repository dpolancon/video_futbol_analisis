"""
Automated Soccer Tracking and Drone Analytics Pipeline - Spatial Transformation Module
core/homography.py

This module contains the spatial registration engine mapping 2D image coordinates (pixels)
to 2D real-world soccer pitch metric coordinates (meters).
"""

import logging
from typing import List, Tuple, Union
import numpy as np

# Configure logging
logger = logging.getLogger(__name__)

class PitchRegistrator:
    """
    PitchRegistrator registers the camera image coordinates against the physical soccer field coordinates.
    
    It allows mapping of coordinates from the distorted image plane (pixels) to the flat 2D projection
    of the field (meters). Standard dimensions are typically 105m x 68m.
    """
    
    def __init__(self):
        """
        Initializes the PitchRegistrator.
        """
        # Default soccer pitch dimensions in meters (FIFA standard: 105m length x 68m width)
        self.pitch_length = 105.0
        self.pitch_width = 68.0
        
        # A default placeholder homography matrix to act as a fallback.
        # This maps a typical 1920x1080 resolution frame directly into the 105x68m grid.
        self.default_homography = np.array([
            [0.0546875,  0.0,         0.0],
            [0.0,        0.06296296,  0.0],
            [0.0,        0.0,         1.0]
        ])
        logger.info("PitchRegistrator initialized.")

    def compute_homography(
        self, 
        src_points: List[Tuple[float, float]], 
        dst_points: List[Tuple[float, float]], 
        method: str = "RANSAC"
    ) -> np.ndarray:
        """
        Computes the 3x3 homography matrix transforming image plane coordinates 
        to real-world pitch coordinates.

        Args:
            src_points (List[Tuple[float, float]]): Source coordinates in image plane (pixels).
                                                    Minimally 4 points required.
            dst_points (List[Tuple[float, float]]): Destination coordinates in pitch plane (meters).
                                                    Must correspond 1:1 with src_points.
            method (str): Algorithm for matching. Supported values: 'RANSAC', 'LMEDS', 'DIRECT'.
                          Defaults to 'RANSAC'.

        Returns:
            np.ndarray: A 3x3 homography matrix.
        """
        if len(src_points) < 4 or len(dst_points) < 4:
            raise ValueError("At least 4 corresponding point-anchors are required to compute a homography matrix.")

        logger.info(f"Computing homography matrix using method: {method} with {len(src_points)} source points.")

        src_arr = np.array(src_points, dtype=np.float32)
        dst_arr = np.array(dst_points, dtype=np.float32)

        try:
            import cv2
            
            # Map method string to OpenCV flag
            if method.upper() == "RANSAC":
                flag = cv2.RANSAC
            elif method.upper() == "LMEDS":
                flag = cv2.LMEDS
            else:
                flag = 0  # Least squares solution
                
            homography_matrix, mask = cv2.findHomography(src_arr, dst_arr, flag, 5.0)
            logger.info("Homography successfully computed via OpenCV findHomography.")
            return homography_matrix
            
        except ImportError:
            logger.warning(
                "OpenCV (cv2) is not installed in the execution environment. "
                "Computing homography matrix using a basic NumPy direct linear transform (DLT)."
            )
            # Standard Direct Linear Transformation (DLT) solver
            A = []
            for i in range(len(src_arr)):
                x, y = src_arr[i][0], src_arr[i][1]
                u, v = dst_arr[i][0], dst_arr[i][1]
                A.append([-x, -y, -1, 0, 0, 0, x*u, y*u, u])
                A.append([0, 0, 0, -x, -y, -1, x*v, y*v, v])
            
            A = np.array(A)
            _, _, Vh = np.linalg.svd(A)
            L = Vh[-1, :]
            homography_matrix = L.reshape(3, 3)
            # Normalize matrix so that h33 is 1.0
            if homography_matrix[2, 2] != 0:
                homography_matrix = homography_matrix / homography_matrix[2, 2]
                
            return homography_matrix

    def pixel_to_meters(self, x: float, y: float, homography_matrix: np.ndarray = None) -> Tuple[float, float]:
        """
        Projects an image coordinate (x, y) into a flat 2D pitch coordinate (x_meters, y_meters).

        Uses the standard homography transformation math:
        x_meters = (h11*x + h12*y + h13) / (h31*x + h32*y + h33)
        y_meters = (h21*x + h22*y + h23) / (h31*x + h32*y + h33)

        Args:
            x (float): Pixel x-coordinate.
            y (float): Pixel y-coordinate.
            homography_matrix (np.ndarray, optional): 3x3 projection matrix. If None,
                                                      uses the default internal matrix.

        Returns:
            Tuple[float, float]: Position in meters on the physical field:
                                 - x_meters: distance along the length of the pitch (e.g., 0 to 105m)
                                 - y_meters: distance across the width of the pitch (e.g., 0 to 68m)
        """
        if homography_matrix is None:
            homography_matrix = self.default_homography

        # Convert to homogeneous coordinate [x, y, 1]^T
        point_vector = np.array([x, y, 1.0], dtype=np.float32)
        
        # Execute project transformation multiplication: H * p
        projected_vector = np.dot(homography_matrix, point_vector)
        
        w = projected_vector[2]
        if w == 0:
            logger.error("Homography division by zero encountered. Returning projection coordinates as (0.0, 0.0).")
            return 0.0, 0.0

        x_meters = projected_vector[0] / w
        y_meters = projected_vector[1] / w
        
        return float(x_meters), float(y_meters)
