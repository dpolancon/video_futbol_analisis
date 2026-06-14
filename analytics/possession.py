"""
Automated Soccer Tracking and Drone Analytics Pipeline - Statistical Analysis Skills
analytics/possession.py

This module implements the time-series mathematical metrics of Guo et al. (2026) for
calculating player and team ball possession using normalized spatial proximity
and entry/exit hysteresis parameters.
"""

import logging
from typing import Dict, Tuple, Union, Any, Optional
import pandas as pd
import numpy as np
from analytics import register_skill

# Configure logging
logger = logging.getLogger(__name__)

@register_skill("possession")
class PossessionAnalyzer:
    """
    PossessionAnalyzer calculates possession based on player-ball proximity.
    
    Mathematical details from Guo et al. (2026):
    The spatial proximity of a player i to the ball is normalized by the player's 
    bounding box height to account for varying drone altitudes and perspective tilts:
    
        D_norm(i) = d(player_i, ball) / H_i
        
    where:
        - d(player_i, ball) is the Euclidean distance in pixels between the player's centroid 
          and the ball's centroid.
        - H_i = ymax_i - ymin_i is the bounding box height of player i in pixels.
        
    State switches between 'in possession' and 'out of possession' are managed via 
    hysteresis parameters T_in and T_out:
        - Entry (Gaining Possession): A player not in possession gains it if:
            D_norm(i) < T_in  (e.g., T_in = 1.5)
        - Exit (Losing Possession): The player in possession loses it only if:
            D_norm(i) > T_out (e.g., T_out = 2.5)
            
    This hysteresis window (T_in, T_out) prevents rapid toggle noise during contested 
    scrimmages or high-frequency tracker oscillations.
    """
    
    def __init__(self, t_in: float = 1.5, t_out: float = 2.5):
        """
        Initializes the PossessionAnalyzer.

        Args:
            t_in (float): Normalized distance entry threshold for gaining possession.
            t_out (float): Normalized distance exit threshold for losing possession.
        """
        self.t_in = t_in
        self.t_out = t_out
        logger.info(f"PossessionAnalyzer initialized with T_in={self.t_in}, T_out={self.t_out}")

    def calculate_possession(self, coordinates_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates frame-by-frame player and team possession.

        Args:
            coordinates_df (pd.DataFrame): Tracking DataFrame with MultiIndex (frame_id, player_id) 
                                           and standard pipeline columns.

        Returns:
            pd.DataFrame: A possession summary DataFrame indexed by 'frame_id' with columns:
                          - 'ball_detected': boolean
                          - 'possession_player_id': int or None (ID of player in possession)
                          - 'possession_team_id': int or -1 (Team ID in possession, -1 for none)
                          - 'possession_confidence': float
        """
        if coordinates_df.empty:
            logger.warning("Empty tracking DataFrame passed. Returning empty possession summary.")
            return pd.DataFrame(columns=["ball_detected", "possession_player_id", "possession_team_id", "possession_confidence"])

        # Reset index temporarily for easier grouping
        df = coordinates_df.reset_index()
        frames = sorted(df["frame_id"].unique())
        
        possession_history = []
        
        # State trackers across frames
        current_possessor_id: Optional[int] = None
        current_team_id: int = -1
        
        for frame_id in frames:
            frame_data = df[df["frame_id"] == frame_id]
            
            # Find the ball detection in the current frame
            ball_rows = frame_data[frame_data["label"] == "ball"]
            if ball_rows.empty:
                # Ball not detected: carry over the previous possession state
                possession_history.append({
                    "frame_id": frame_id,
                    "ball_detected": False,
                    "possession_player_id": current_possessor_id,
                    "possession_team_id": current_team_id,
                    "possession_confidence": 0.5 if current_possessor_id is not None else 0.0
                })
                continue
                
            ball_row = ball_rows.iloc[0]
            x_ball, y_ball = ball_row["x_pixel"], ball_row["y_pixel"]
            
            # Find players in the current frame
            player_rows = frame_data[frame_data["label"] == "player"]
            if player_rows.empty:
                # No players detected: carry over previous state
                possession_history.append({
                    "frame_id": frame_id,
                    "ball_detected": True,
                    "possession_player_id": current_possessor_id,
                    "possession_team_id": current_team_id,
                    "possession_confidence": 0.0
                })
                continue
            
            # Compute normalized proximity metrics for all players
            players_metrics = []
            
            for _, player in player_rows.iterrows():
                p_id = int(player["player_id"])
                # Player centroid
                x_p = player["x_pixel"]
                # For height-normalized spatial proximity, calculate player box center or centroid
                y_p = (player["ymin"] + player["ymax"]) / 2.0
                
                # Euclidean distance
                dist = np.hypot(x_p - x_ball, y_p - y_ball)
                
                # Player height in pixels
                height = float(player["ymax"] - player["ymin"])
                if height <= 0:
                    height = 1.0  # Safe division fallback
                    
                d_norm = dist / height
                
                players_metrics.append({
                    "player_id": p_id,
                    "team_id": int(player["team_id"]),
                    "d_norm": d_norm,
                    "confidence": float(player["confidence"])
                })
                
            # Sort players by normalized proximity (closest first)
            players_metrics.sort(key=lambda x: x["d_norm"])
            closest_player = players_metrics[0]
            
            # Hysteresis update logic:
            # Check if the currently registered possessor is still within the frame
            current_possessor_in_frame = next((p for p in players_metrics if p["player_id"] == current_possessor_id), None)
            
            if current_possessor_id is not None and current_possessor_in_frame is not None:
                # If a player had possession, they keep it unless they exceed T_out
                # OR if another player enters very close (less than T_in) AND closer than the current possessor
                if current_possessor_in_frame["d_norm"] > self.t_out:
                    # Current possessor lost possession
                    if closest_player["d_norm"] < self.t_in:
                        # Direct handover
                        current_possessor_id = closest_player["player_id"]
                        current_team_id = closest_player["team_id"]
                    else:
                        # Free ball / Contested
                        current_possessor_id = None
                        current_team_id = -1
                else:
                    # Check if a different player intercepts the ball (closer than current and below T_in)
                    if closest_player["player_id"] != current_possessor_id and closest_player["d_norm"] < self.t_in:
                        current_possessor_id = closest_player["player_id"]
                        current_team_id = closest_player["team_id"]
            else:
                # No active possessor registered: check if the closest player falls below T_in
                if closest_player["d_norm"] < self.t_in:
                    current_possessor_id = closest_player["player_id"]
                    current_team_id = closest_player["team_id"]
                else:
                    current_possessor_id = None
                    current_team_id = -1
                    
            possession_history.append({
                "frame_id": frame_id,
                "ball_detected": True,
                "possession_player_id": current_possessor_id,
                "possession_team_id": current_team_id,
                "possession_confidence": 1.0 - (closest_player["d_norm"] / self.t_out) if current_possessor_id is not None else 0.0
            })
            
        # Rebuild summary dataframe
        summary_df = pd.DataFrame(possession_history)
        summary_df.set_index("frame_id", inplace=True)
        
        # Clip possession confidence to [0.0, 1.0] range
        summary_df["possession_confidence"] = summary_df["possession_confidence"].clip(0.0, 1.0)
        
        logger.info(f"Possession computation finished across {len(frames)} frames.")
        return summary_df
