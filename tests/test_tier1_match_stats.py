"""
Automated Soccer Tracking and Drone Analytics Pipeline - Tier 1 Tests
tests/test_tier1_match_stats.py

Verifies the Stage 1 match statistics calculator.
"""

import pytest
import pandas as pd
import numpy as np
from analytics.match_stats import MatchStatsAnalyzer

@pytest.fixture
def mock_trajectory_df():
    # MultiIndex (frame_id, player_id)
    index = pd.MultiIndex.from_tuples([
        (1, 0), (1, 1), (1, 99),
        (2, 0), (2, 1), (2, 99),
        (3, 0), (3, 1), (3, 99),
    ], names=["frame_id", "player_id"])
    
    data = [
        # Frame 1
        {"x_meter": 10.0, "y_meter": 20.0, "label": "player", "team_id": 0},
        {"x_meter": 50.0, "y_meter": 30.0, "label": "player", "team_id": 1},
        {"x_meter": 25.0, "y_meter": 25.0, "label": "ball", "team_id": -1},
        # Frame 2
        {"x_meter": 12.0, "y_meter": 20.0, "label": "player", "team_id": 0}, # Dist = 2.0
        {"x_meter": 50.0, "y_meter": 34.0, "label": "player", "team_id": 1}, # Dist = 4.0
        {"x_meter": 26.0, "y_meter": 26.0, "label": "ball", "team_id": -1},
        # Frame 3
        {"x_meter": 15.0, "y_meter": 24.0, "label": "player", "team_id": 0}, # Dist = 5.0 (Total: 7.0)
        {"x_meter": 45.0, "y_meter": 34.0, "label": "player", "team_id": 1}, # Dist = 5.0 (Total: 9.0)
        {"x_meter": 30.0, "y_meter": 30.0, "label": "ball", "team_id": -1},
    ]
    
    return pd.DataFrame(data, index=index)

@pytest.fixture
def mock_possession_df():
    # Indexed by frame_id
    index = [1, 2, 3]
    data = [
        {"possession_team_id": 0, "ball_detected": True},
        {"possession_team_id": 0, "ball_detected": True},
        {"possession_team_id": 1, "ball_detected": True},
    ]
    return pd.DataFrame(data, index=index)

def test_match_stats_volume_metrics(mock_trajectory_df, mock_possession_df):
    analyzer = MatchStatsAnalyzer()
    stats = analyzer.calculate(mock_trajectory_df, mock_possession_df, fps=30.0, stride=30)
    
    # Volume metrics
    assert stats["total_frames_procesados"] == 3
    assert stats["duracion_efectiva_segundos"] == 3.0 # effective_fps = 30/30 = 1.0
    assert stats["observaciones_jugadores_total"] == 6
    assert stats["tasa_deteccion_balon_pct"] == 100.0
    assert stats["promedio_jugadores_activos_por_frame"] == 2.0
    assert stats["max_jugadores_activos_frame"] == 2

def test_match_stats_possession(mock_trajectory_df, mock_possession_df):
    analyzer = MatchStatsAnalyzer()
    stats = analyzer.calculate(mock_trajectory_df, mock_possession_df, fps=30.0, stride=30)
    
    # Possession
    assert stats["posesion_pct_Equipo_A"] == 66.67 # 2 out of 3 contested
    assert stats["posesion_pct_Equipo_B"] == 33.33 # 1 out of 3 contested
    assert stats["posesion_no_disputada_pct"] == 0.0
    
    assert stats["racha_max_posesion_seg_Equipo_A"] == 2.0 # 2 frames / 1 effective fps
    assert stats["racha_max_posesion_seg_Equipo_B"] == 1.0 # 1 frame / 1 effective fps
    assert stats["cambios_de_posesion"] == 1 # 0 to 1

def test_match_stats_distance_calculation(mock_trajectory_df, mock_possession_df):
    analyzer = MatchStatsAnalyzer()
    stats = analyzer.calculate(mock_trajectory_df, mock_possession_df, fps=30.0, stride=30)
    
    # Distance
    assert stats["distancia_total_recorrida_m_Equipo_A"] == 7.0
    assert stats["distancia_total_recorrida_m_Equipo_B"] == 9.0
    
    assert stats["distancia_max_jugador_individual_m"] == 9.0 # Max is team 1 player
    
    # Speed: max dist step is 5.0. Effective fps = 1.0. Speed = 5.0 * 1.0 = 5.0 m/s
    assert stats["velocidad_pico_jugador_ms"] == 5.0

def test_match_stats_empty_trajectory():
    analyzer = MatchStatsAnalyzer()
    empty_traj = pd.DataFrame()
    empty_poss = pd.DataFrame()
    
    stats = analyzer.calculate(empty_traj, empty_poss, fps=30.0, stride=30)
    assert stats == {}
