"""
Automated Soccer Tracking and Drone Analytics Pipeline - Statistical Analysis Skills
analytics/match_stats.py

This module implements the calculation of basic descriptive statistics from the 
trajectory and possession DataFrames, grouped by Volume, Possession, and Distance.
"""

import logging
from typing import Dict, Any
import pandas as pd
import numpy as np
from analytics import register_skill

# Configure logging
logger = logging.getLogger(__name__)

@register_skill("match_stats")
class MatchStatsAnalyzer:
    """
    MatchStatsAnalyzer computes basic descriptive statistics from tracking data.
    
    Groups Implemented (Stage 1):
      - A: Volume (frames, detection rates)
      - B: Possession (percentages, longest streaks, turnovers)
      - C: Movement & Distance (total distance, speed)
    """
    
    def __init__(self, team0_name: str = "Equipo A", team1_name: str = "Equipo B"):
        """
        Initializes the MatchStatsAnalyzer.
        
        Args:
            team0_name (str): Display name for Team 0.
            team1_name (str): Display name for Team 1.
        """
        self.team0_name = team0_name
        self.team1_name = team1_name
        logger.info(f"MatchStatsAnalyzer initialized for {team0_name} vs {team1_name}")

    def calculate(self, trajectory_df: pd.DataFrame, possession_df: pd.DataFrame, fps: float, stride: int) -> Dict[str, Any]:
        """
        Calculates basic descriptive match statistics.

        Args:
            trajectory_df (pd.DataFrame): Tracking DataFrame with MultiIndex (frame_id, player_id)
            possession_df (pd.DataFrame): Possession summary DataFrame indexed by frame_id
            fps (float): Native frame rate of the video
            stride (int): Frame sub-sampling stride

        Returns:
            Dict[str, Any]: Dictionary containing all calculated statistics (in Spanish).
        """
        stats = {}
        
        if trajectory_df.empty:
            logger.warning("Empty trajectory DataFrame passed to MatchStatsAnalyzer.")
            return stats
            
        # Effective FPS after stride
        effective_fps = fps / stride if stride > 0 else fps
        
        # --- GROUP A: VOLUMEN (Volume Metrics) ---
        df_flat = trajectory_df.reset_index()
        total_frames = df_flat["frame_id"].nunique()
        
        stats["total_frames_procesados"] = total_frames
        stats["duracion_efectiva_segundos"] = round(total_frames / effective_fps, 2)
        
        player_rows = df_flat[df_flat["label"] == "player"]
        stats["observaciones_jugadores_total"] = len(player_rows)
        
        ball_rows = df_flat[df_flat["label"] == "ball"]
        frames_with_ball = ball_rows["frame_id"].nunique()
        stats["tasa_deteccion_balon_pct"] = round((frames_with_ball / total_frames) * 100.0, 2) if total_frames > 0 else 0.0
        
        players_per_frame = player_rows.groupby("frame_id").size()
        stats["promedio_jugadores_activos_por_frame"] = round(players_per_frame.mean(), 2) if not players_per_frame.empty else 0.0
        stats["max_jugadores_activos_frame"] = int(players_per_frame.max()) if not players_per_frame.empty else 0

        # --- GROUP B: POSESION (Possession Summary) ---
        if not possession_df.empty:
            # Recompute total frames from possession df in case it differs slightly
            total_poss_frames = len(possession_df)
            counts = possession_df["possession_team_id"].value_counts()
            
            t0_frames = counts.get(0, 0)
            t1_frames = counts.get(1, 0)
            contested_frames = t0_frames + t1_frames
            
            stats[f"posesion_pct_{self.team0_name.replace(' ', '_')}"] = round((t0_frames / contested_frames) * 100.0, 2) if contested_frames > 0 else 0.0
            stats[f"posesion_pct_{self.team1_name.replace(' ', '_')}"] = round((t1_frames / contested_frames) * 100.0, 2) if contested_frames > 0 else 0.0
            stats["posesion_no_disputada_pct"] = round((counts.get(-1, 0) / total_poss_frames) * 100.0, 2) if total_poss_frames > 0 else 0.0
            
            # Calculate streaks and turnovers
            streaks = {0: 0, 1: 0}
            turnovers = 0
            current_team = -1
            current_streak = 0
            
            for team in possession_df["possession_team_id"]:
                if team in [0, 1]:
                    if team == current_team:
                        current_streak += 1
                    else:
                        if current_team in [0, 1]:
                            streaks[current_team] = max(streaks[current_team], current_streak)
                            turnovers += 1  # Transition from team to team (or team to contested)
                        current_team = team
                        current_streak = 1
                else:
                    if current_team in [0, 1]:
                        streaks[current_team] = max(streaks[current_team], current_streak)
                    current_team = -1
                    current_streak = 0
                    
            if current_team in [0, 1]:
                streaks[current_team] = max(streaks[current_team], current_streak)
                
            stats[f"racha_max_posesion_seg_{self.team0_name.replace(' ', '_')}"] = round(streaks[0] / effective_fps, 1) if effective_fps > 0 else 0.0
            stats[f"racha_max_posesion_seg_{self.team1_name.replace(' ', '_')}"] = round(streaks[1] / effective_fps, 1) if effective_fps > 0 else 0.0
            stats["cambios_de_posesion"] = turnovers
        else:
            stats[f"posesion_pct_{self.team0_name.replace(' ', '_')}"] = 0.0
            stats[f"posesion_pct_{self.team1_name.replace(' ', '_')}"] = 0.0
            stats["posesion_no_disputada_pct"] = 0.0
            stats[f"racha_max_posesion_seg_{self.team0_name.replace(' ', '_')}"] = 0.0
            stats[f"racha_max_posesion_seg_{self.team1_name.replace(' ', '_')}"] = 0.0
            stats["cambios_de_posesion"] = 0

        # --- GROUP C: DISTANCIA Y MOVIMIENTO (Movement & Distance) ---
        # Sort by player, then frame to compute deltas
        player_df = df_flat[df_flat["label"] == "player"].sort_values(["player_id", "frame_id"])
        
        # Calculate Euclidean distance between consecutive frames for each player
        player_df["dx"] = player_df.groupby("player_id")["x_meter"].diff()
        player_df["dy"] = player_df.groupby("player_id")["y_meter"].diff()
        player_df["dist_step"] = np.sqrt(player_df["dx"]**2 + player_df["dy"]**2)
        
        # Fill NaNs with 0 for summation
        player_df["dist_step"] = player_df["dist_step"].fillna(0)
        
        # Aggregate distance per player
        dist_per_player = player_df.groupby(["player_id", "team_id"])["dist_step"].sum().reset_index()
        
        # Filter by team
        t0_dists = dist_per_player[dist_per_player["team_id"] == 0]["dist_step"]
        t1_dists = dist_per_player[dist_per_player["team_id"] == 1]["dist_step"]
        
        t0_total_dist = t0_dists.sum()
        t1_total_dist = t1_dists.sum()
        
        stats[f"distancia_total_recorrida_m_{self.team0_name.replace(' ', '_')}"] = round(t0_total_dist, 2)
        stats[f"distancia_total_recorrida_m_{self.team1_name.replace(' ', '_')}"] = round(t1_total_dist, 2)
        
        stats[f"distancia_media_por_jugador_m_{self.team0_name.replace(' ', '_')}"] = round(t0_dists.mean(), 2) if not t0_dists.empty else 0.0
        stats[f"distancia_media_por_jugador_m_{self.team1_name.replace(' ', '_')}"] = round(t1_dists.mean(), 2) if not t1_dists.empty else 0.0
        
        stats["distancia_max_jugador_individual_m"] = round(dist_per_player["dist_step"].max(), 2) if not dist_per_player.empty else 0.0
        
        # Speed: dist_step is distance per processed frame. Time per processed frame is 1 / effective_fps.
        # So speed (m/s) = dist_step * effective_fps
        if not player_df.empty and effective_fps > 0:
            player_df["speed"] = player_df["dist_step"] * effective_fps
            stats["velocidad_pico_jugador_ms"] = round(player_df["speed"].max(), 2)
        else:
            stats["velocidad_pico_jugador_ms"] = 0.0

        return stats
