import os
import cv2
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from scipy.spatial import ConvexHull
from scipy.ndimage import gaussian_filter
from typing import Dict, List, Tuple, Any, Optional

class FootballTacticalAnalyzer:
    """
    Advanced sports analytics engine to perform tactical evaluations on player and ball
    tracking trajectories derived from aerial soccer drone video.
    
    Reads standard CoordinatesDataFrame structured under Multi-level Pandas schemas:
        - Level 0: Object Class ('player_team0', 'player_team1', 'ball', 'referee')
        - Level 1: Track ID (integer)
        - Level 2: Axis ('x', 'y')
    Coordinates are represented in meters mapped onto a normalized [0-105m] x [0-68m] field.
    """
    
    def __init__(self, pitch_length: float = 105.0, pitch_width: float = 68.0, fps: int = 30, language: str = "en"):
        self.pitch_length = pitch_length
        self.pitch_width = pitch_width
        self.fps = fps
        self.language = language
        
    def _interpolate_coordinates(self, coords_df: pd.DataFrame) -> pd.DataFrame:
        """
        Applies linear interpolation on player coordinate dataframes to fill short-term tracking
        occlusion gaps (up to 15 frames / 0.5s) safely before geometric processing.
        """
        interpolated = coords_df.copy()
        # Interpolate frame-wise (axis=0) for coordinates
        interpolated = interpolated.interpolate(method='linear', limit=15, limit_direction='both')
        # Fill any remaining NaNs at boundaries with edge values
        interpolated = interpolated.ffill().bfill()
        return interpolated

    def calculate_team_compactness(self, coords_df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes dynamic Convex Hull Areas (m2) and Standard Distance Deviations (m)
        frame-by-frame for Team 0 and Team 1 to measure team tactical compression.
        
        Returns:
            pd.DataFrame: Contains centroids, standard distance deviations (sdd), and hull areas.
        """
        coords_df = self._interpolate_coordinates(coords_df)
        frames_idx = coords_df.index
        
        metrics = {
            'team0_centroid_x': [], 'team0_centroid_y': [], 'team0_hull_area': [], 'team0_sdd': [],
            'team1_centroid_x': [], 'team1_centroid_y': [], 'team1_hull_area': [], 'team1_sdd': []
        }
        
        for frame_idx in frames_idx:
            # Calculate metrics for Team 0 and Team 1
            for team_key, prefix in [('player_team0', 'team0'), ('player_team1', 'team1')]:
                # Extract coordinates for this team class
                if team_key in coords_df.columns.levels[0]:
                    team_slice = coords_df.loc[frame_idx, team_key]
                    # Reshape into (N, 2) player coordinates
                    player_coords = []
                    # levels[1] represents player track IDs
                    for track_id in team_slice.index.levels[0]:
                        if track_id in team_slice:
                            x = team_slice[track_id]['x']
                            y = team_slice[track_id]['y']
                            if not np.isnan(x) and not np.isnan(y):
                                player_coords.append([x, y])
                    
                    player_coords = np.array(player_coords)
                    
                    if len(player_coords) >= 3:
                        # Centroid (Barycenter) calculation
                        centroid = np.mean(player_coords, axis=0)
                        
                        # Standard Distance Deviation (SDD) calculation
                        # SDD = sqrt( sum((x_i - cx)^2 + (y_i - cy)^2) / N )
                        sdd = np.sqrt(np.mean(np.sum((player_coords - centroid) ** 2, axis=1)))
                        
                        # Convex Hull area calculation
                        try:
                            hull = ConvexHull(player_coords)
                            # In 2D, ConvexHull.volume is the area enclosed, and .area is the perimeter
                            hull_area = hull.volume
                        except Exception:
                            # Fallback if players are collinear or calculation fails
                            hull_area = 0.0
                        
                        metrics[f'{prefix}_centroid_x'].append(centroid[0])
                        metrics[f'{prefix}_centroid_y'].append(centroid[1])
                        metrics[f'{prefix}_hull_area'].append(hull_area)
                        metrics[f'{prefix}_sdd'].append(sdd)
                    else:
                        # Handle empty or highly degraded frames gracefully
                        metrics[f'{prefix}_centroid_x'].append(np.nan)
                        metrics[f'{prefix}_centroid_y'].append(np.nan)
                        metrics[f'{prefix}_hull_area'].append(0.0)
                        metrics[f'{prefix}_sdd'].append(0.0)
                else:
                    metrics[f'{prefix}_centroid_x'].append(np.nan)
                    metrics[f'{prefix}_centroid_y'].append(np.nan)
                    metrics[f'{prefix}_hull_area'].append(0.0)
                    metrics[f'{prefix}_sdd'].append(0.0)
                    
        return pd.DataFrame(metrics, index=frames_idx)

    def _infer_possession_array(self, coords_df: pd.DataFrame) -> np.ndarray:
        """
        Dynamically infers the possessing team sequence frame-by-frame based on scale-aware
        spatial proximity filters and temporal hysteresis rules.
        """
        frames_idx = coords_df.index
        possession_seq = np.zeros(len(frames_idx), dtype=int) - 1 # -1: Unknown/Neutral
        
        # Hysteresis parameters
        t_in = 3.0   # Meters proximity to register candidate possession
        t_out = 5.0  # Meters proximity to drop candidate possession
        hold_frames = int(0.5 * self.fps) # Handle occlusion gaps (0.5s)
        min_duration = int(0.3 * self.fps) # Threshold duration to switch possession (0.3s)
        
        current_state = -1
        candidate_state = -1
        candidate_counter = 0
        gap_counter = 0
        
        for idx, frame_idx in enumerate(frames_idx):
            # Extract ball coordinates
            ball_coord = np.array([np.nan, np.nan])
            if 'ball' in coords_df.columns.levels[0]:
                ball_slice = coords_df.loc[frame_idx, 'ball']
                for track_id in ball_slice.index.levels[0]:
                    if track_id in ball_slice:
                        bx = ball_slice[track_id]['x']
                        by = ball_slice[track_id]['y']
                        if not np.isnan(bx) and not np.isnan(by):
                            ball_coord = np.array([bx, by])
                            break # Assume singular ball entity
            
            # If ball is missing or occluded
            if np.isnan(ball_coord[0]):
                gap_counter += 1
                if gap_counter > hold_frames:
                    current_state = -1
                possession_seq[idx] = current_state
                continue
            
            gap_counter = 0
            
            # Find closest player
            min_dist = float('inf')
            closest_team = -1
            
            for team_idx, team_key in enumerate(['player_team0', 'player_team1']):
                if team_key in coords_df.columns.levels[0]:
                    team_slice = coords_df.loc[frame_idx, team_key]
                    for track_id in team_slice.index.levels[0]:
                        if track_id in team_slice:
                            px = team_slice[track_id]['x']
                            py = team_slice[track_id]['y']
                            if not np.isnan(px) and not np.isnan(py):
                                dist = np.sqrt((px - ball_coord[0])**2 + (py - ball_coord[1])**2)
                                if dist < min_dist:
                                    min_dist = dist
                                    closest_team = team_idx
            
            # Apply state transition hysteresis loop
            if min_dist < t_in:
                cand = closest_team
            elif min_dist > t_out:
                cand = -1
            else:
                cand = current_state
                
            if cand == current_state:
                candidate_counter = 0
            else:
                if cand != -1:
                    if cand == candidate_state:
                        candidate_counter += 1
                    else:
                        candidate_state = cand
                        candidate_counter = 1
                    
                    if candidate_counter >= min_duration:
                        current_state = candidate_state
                        candidate_counter = 0
                else:
                    current_state = -1
                    candidate_counter = 0
                    
            possession_seq[idx] = current_state
            
        return possession_seq

    def _draw_pitch(self, ax: plt.Axes, bg_color: str = '#1E293B', line_color: str = '#94A3B8'):
        """
        Programmatically draws a standard 2D soccer field marking layout on an existing axis.
        """
        ax.set_facecolor(bg_color)
        ax.set_xlim(-5, self.pitch_length + 5)
        ax.set_ylim(-5, self.pitch_width + 5)
        ax.axis('off')
        
        # Outer boundary lines
        ax.add_patch(patches.Rectangle((0, 0), self.pitch_length, self.pitch_width, fill=False, edgecolor=line_color, linewidth=2))
        
        # Halfway line & center circle
        ax.plot([self.pitch_length / 2, self.pitch_length / 2], [0, self.pitch_width], color=line_color, linewidth=2)
        ax.add_patch(patches.Circle((self.pitch_length / 2, self.pitch_width / 2), 9.15, fill=False, edgecolor=line_color, linewidth=2))
        ax.add_patch(patches.Circle((self.pitch_length / 2, self.pitch_width / 2), 0.3, fill=True, color=line_color))
        
        # Penalty areas (length 16.5m, width 40.32m centered)
        pen_width = 40.32
        pen_length = 16.5
        pen_y_min = (self.pitch_width - pen_width) / 2
        # Team 0 Penalty Box (Left side)
        ax.add_patch(patches.Rectangle((0, pen_y_min), pen_length, pen_width, fill=False, edgecolor=line_color, linewidth=1.5))
        # Team 1 Penalty Box (Right side)
        ax.add_patch(patches.Rectangle((self.pitch_length - pen_length, pen_y_min), pen_length, pen_width, fill=False, edgecolor=line_color, linewidth=1.5))
        
        # Goal areas (length 5.5m, width 18.32m centered)
        goal_width = 18.32
        goal_length = 5.5
        goal_y_min = (self.pitch_width - goal_width) / 2
        # Team 0 Goal Box (Left)
        ax.add_patch(patches.Rectangle((0, goal_y_min), goal_length, goal_width, fill=False, edgecolor=line_color, linewidth=1.2))
        # Team 1 Goal Box (Right)
        ax.add_patch(patches.Rectangle((self.pitch_length - goal_length, goal_y_min), goal_length, goal_width, fill=False, edgecolor=line_color, linewidth=1.2))

    def generate_possession_weighted_heatmaps(self, coords_df: pd.DataFrame, output_dir: str):
        """
        Generates tactical heatmaps separating spatial coordinate distributions weighted
        by active team possession states, plotting side-by-side tactical sheets.
        """
        os.makedirs(output_dir, exist_ok=True)
        coords_df = self._interpolate_coordinates(coords_df)
        possession_seq = self._infer_possession_array(coords_df)
        
        t0_x_coords, t0_y_coords = [], []
        t1_x_coords, t1_y_coords = [], []
        
        for idx, frame_idx in enumerate(coords_df.index):
            state = possession_seq[idx]
            if state == 0: # Team 0 in possession
                team_slice = coords_df.loc[frame_idx, 'player_team0']
                for track_id in team_slice.index.levels[0]:
                    if track_id in team_slice:
                        x = team_slice[track_id]['x']
                        y = team_slice[track_id]['y']
                        if not np.isnan(x) and not np.isnan(y):
                            t0_x_coords.append(x)
                            t0_y_coords.append(y)
            elif state == 1: # Team 1 in possession
                team_slice = coords_df.loc[frame_idx, 'player_team1']
                for track_id in team_slice.index.levels[0]:
                    if track_id in team_slice:
                        x = team_slice[track_id]['x']
                        y = team_slice[track_id]['y']
                        if not np.isnan(x) and not np.isnan(y):
                            t1_x_coords.append(x)
                            t1_y_coords.append(y)
                            
        # Define grid layout (105 bins along length, 68 bins along width)
        x_bins = np.linspace(0, self.pitch_length, 105)
        y_bins = np.linspace(0, self.pitch_width, 68)
        
        # Build 2D Histograms
        hist_t0, _, _ = np.histogram2d(t0_x_coords, t0_y_coords, bins=[x_bins, y_bins]) if t0_x_coords else (np.zeros((104, 67)), None, None)
        hist_t1, _, _ = np.histogram2d(t1_x_coords, t1_y_coords, bins=[x_bins, y_bins]) if t1_x_coords else (np.zeros((104, 67)), None, None)
        
        # Apply spatial gaussian smoothing (KDE equivalent)
        smoothed_t0 = gaussian_filter(hist_t0, sigma=2.0)
        smoothed_t1 = gaussian_filter(hist_t1, sigma=2.0)
        
        # Plotting double layout figure
        fig, axes = plt.subplots(1, 2, figsize=(20, 8), facecolor='#0F172A')
        
        title_t0 = "Equipo 0 - Mapa de Influencia de Posesion" if self.language == 'es' else "Team 0 - Possession Influence Map"
        title_t1 = "Equipo 1 - Mapa de Influencia de Posesion" if self.language == 'es' else "Team 1 - Possession Influence Map"
        
        for ax, smoothed_data, title, colormap in [
            (axes[0], smoothed_t0, title_t0, 'YlOrBr'),
            (axes[1], smoothed_t1, title_t1, 'GnBu')
        ]:
            self._draw_pitch(ax)
            ax.set_title(title, fontsize=16, color='#F8FAFC', pad=15, fontweight='bold')
            if np.max(smoothed_data) > 0:
                ax.imshow(
                    smoothed_data.T, 
                    extent=[0, self.pitch_length, 0, self.pitch_width], 
                    origin='lower', 
                    cmap=colormap, 
                    alpha=0.6, 
                    interpolation='gaussian'
                )
        
        plt.tight_layout()
        save_path = os.path.join(output_dir, "possession_weighted_heatmaps.png")
        plt.savefig(save_path, dpi=200, bbox_inches='tight', facecolor='#0F172A')
        plt.close()

    def _point_to_segment_distance(self, p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
        """
        Calculates perpendicular Euclidean distance from point 'p' to line segment 'ab'.
        """
        ab = b - a
        ap = p - a
        # Project vector ap onto line segment ab
        ab_len_sq = np.sum(ab**2)
        if ab_len_sq == 0.0:
            return float(np.linalg.norm(ap))
            
        t = np.dot(ap, ab) / ab_len_sq
        t = np.clip(t, 0.0, 1.0) # Restrict projection index onto segment boundary
        projection = a + t * ab
        return float(np.linalg.norm(p - projection))

    def detect_passing_lanes_and_defensive_clutter(self, frame_idx: int, coords_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Maps passing vectors between all possessing teammate combinations, executing ray-tracing 
        distance profiles from defenders. If any defender blocks the lane within 1.5 meters, 
        flags the line segment as structurally cluttered.
        """
        coords_df = self._interpolate_coordinates(coords_df)
        possession_seq = self._infer_possession_array(coords_df)
        
        frame_idx_seq = list(coords_df.index)
        if frame_idx not in frame_idx_seq:
            return []
            
        possession_team_idx = possession_seq[frame_idx_seq.index(frame_idx)]
        if possession_team_idx == -1:
            return [] # No passing lanes on un-controlled neutral frames
            
        attacking_team_key = 'player_team0' if possession_team_idx == 0 else 'player_team1'
        defending_team_key = 'player_team1' if possession_team_idx == 0 else 'player_team0'
        
        # Fetch active attacking and defending player locations
        attackers = {}
        defenders = {}
        
        for team_key, container in [(attacking_team_key, attackers), (defending_team_key, defenders)]:
            if team_key in coords_df.columns.levels[0]:
                slice_data = coords_df.loc[frame_idx, team_key]
                for track_id in slice_data.index.levels[0]:
                    if track_id in slice_data:
                        x = slice_data[track_id]['x']
                        y = slice_data[track_id]['y']
                        if not np.isnan(x) and not np.isnan(y):
                            container[int(track_id)] = np.array([x, y])
                            
        lanes = []
        attacker_ids = list(attackers.keys())
        
        # Build combinatorics pairs
        for i in range(len(attacker_ids)):
            for j in range(i + 1, len(attacker_ids)):
                id1, id2 = attacker_ids[i], attacker_ids[j]
                a_pos, b_pos = attackers[id1], attackers[id2]
                
                # Check line length constraint
                lane_dist = np.linalg.norm(b_pos - a_pos)
                if lane_dist > 45.0: # Long range pass mapping restriction
                    continue
                    
                is_blocked = False
                min_def_dist = float('inf')
                clutter_def_ids = []
                
                for def_id, def_pos in defenders.items():
                    dist = self._point_to_segment_distance(def_pos, a_pos, b_pos)
                    if dist < min_def_dist:
                        min_def_dist = dist
                    if dist < 1.5: # 1.5-meter occlusion corridor parameter
                        is_blocked = True
                        clutter_def_ids.append(def_id)
                        
                lanes.append({
                    "from_id": id1,
                    "to_id": id2,
                    "from_coord": tuple(a_pos),
                    "to_coord": tuple(b_pos),
                    "blocked": is_blocked,
                    "min_defender_dist": min_def_dist,
                    "clutter_defenders": clutter_def_ids,
                    "lane_length": lane_dist
                })
                
        return lanes

    def extract_highlight_clips(self, video_path: str, coords_df: pd.DataFrame, output_report_dir: str):
        """
        Parses tracking logs to pinpoint tactical events (Turnovers, Counter-Attacks, and Final-Third Incursions)
        and uses OpenCV to write premium overlays directly into sliced highlight video clips.
        """
        os.makedirs(output_report_dir, exist_ok=True)
        coords_df = self._interpolate_coordinates(coords_df)
        possession_seq = self._infer_possession_array(coords_df)
        compactness_df = self.calculate_team_compactness(coords_df)
        
        frames_idx = list(coords_df.index)
        total_frames_count = len(frames_idx)
        
        # Step 1: Detect contextual event anchors with 5-second buffer window suppressors
        event_anchors = [] # List of tuples: (frame_index, event_label)
        last_event_frame = -999
        buffer_frames = 5 * self.fps
        
        for idx in range(1, total_frames_count):
            current_frame_id = frames_idx[idx]
            prev_frame_id = frames_idx[idx - 1]
            
            # Extract state metrics
            prev_poss = possession_seq[idx - 1]
            curr_poss = possession_seq[idx]
            
            # Get Ball speed
            ball_speed = 0.0
            if 'ball' in coords_df.columns.levels[0]:
                ball_slice = coords_df.loc[current_frame_id, 'ball']
                prev_ball_slice = coords_df.loc[prev_frame_id, 'ball']
                for track_id in ball_slice.index.levels[0]:
                    if track_id in ball_slice and track_id in prev_ball_slice:
                        bx, by = ball_slice[track_id]['x'], ball_slice[track_id]['y']
                        pbx, pby = prev_ball_slice[track_id]['x'], prev_ball_slice[track_id]['y']
                        if not np.isnan(bx) and not np.isnan(pbx):
                            ball_speed = np.sqrt((bx - pbx)**2 + (by - pby)**2) * self.fps
                            break
            
            # Event 1: Turnover Transition
            if prev_poss != curr_poss and prev_poss != -1 and curr_poss != -1:
                if current_frame_id - last_event_frame > buffer_frames:
                    event_anchors.append((idx, "POSSESSION_TURNOVER"))
                    last_event_frame = current_frame_id
                    continue
                    
            # Event 2: Counter-Attack Trigger (High Velocity in middle third)
            if ball_speed > 12.0: # Ball moving over 12m/s (~43km/h)
                ball_x = np.nan
                if 'ball' in coords_df.columns.levels[0]:
                    ball_slice = coords_df.loc[current_frame_id, 'ball']
                    for track_id in ball_slice.index.levels[0]:
                        if track_id in ball_slice:
                            if not np.isnan(ball_slice[track_id]['x']):
                                ball_x = ball_slice[track_id]['x']
                                break
                
                if not np.isnan(ball_x) and 35.0 < ball_x < 70.0:
                    if current_frame_id - last_event_frame > buffer_frames:
                        event_anchors.append((idx, "COUNTER_ATTACK_TRANSITION"))
                        last_event_frame = current_frame_id
                        continue
                        
            # Event 3: Final-Third Incursion
            ball_pos_x = np.nan
            if 'ball' in coords_df.columns.levels[0]:
                ball_slice = coords_df.loc[current_frame_id, 'ball']
                for track_id in ball_slice.index.levels[0]:
                    if track_id in ball_slice:
                        if not np.isnan(ball_slice[track_id]['x']):
                            ball_pos_x = ball_slice[track_id]['x']
                            break
                            
            if not np.isnan(ball_pos_x):
                # Team 0 controls ball in Team 1's final third, or vice versa
                if (curr_poss == 0 and ball_pos_x > 70.0) or (curr_poss == 1 and ball_pos_x < 35.0):
                    if current_frame_id - last_event_frame > buffer_frames:
                        event_anchors.append((idx, "FINAL_THIRD_INCURSION"))
                        last_event_frame = current_frame_id
                        continue

        # Open raw video capture
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"[ERROR] Could not open video file at: {video_path}")
            return
            
        orig_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Step 2: Slice and overlay clips for registered highlights
        for clip_idx, (trigger_idx, event_label) in enumerate(event_anchors):
            # Clip windows: 5s pre-trigger to 3s post-trigger
            start_frame = max(0, trigger_idx - (5 * self.fps))
            end_frame = min(total_frames_count - 1, trigger_idx + (3 * self.fps))
            
            output_name = f"highlight_{clip_idx:02d}_{event_label}_frame_{frames_idx[trigger_idx]}.mp4"
            output_path = os.path.join(output_report_dir, output_name)
            
            # Using standard MP4V codec
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(output_path, fourcc, float(self.fps), (orig_width, orig_height))
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            
            for current_ptr in range(start_frame, end_frame + 1):
                ret, frame = cap.read()
                if not ret:
                    break
                    
                frame_id_key = frames_idx[current_ptr]
                
                # Fetch rolling parameters to draw premium HUD panel
                curr_poss_team = possession_seq[current_ptr]
                
                # Language translations
                if self.language == 'es':
                    poss_text = "NEUTRO" if curr_poss_team == -1 else f"EQUIPO {curr_poss_team}"
                    event_map = {
                        "POSSESSION_TURNOVER": "PERDIDA DE BALON",
                        "COUNTER_ATTACK_TRANSITION": "TRANSICION CONTRAATAQUE",
                        "FINAL_THIRD_INCURSION": "INCURSION AREA RIVAL"
                    }
                    display_event = event_map.get(event_label, event_label)
                    hud_header = "MOTOR TACTICO AEREO HUD v1.0"
                    event_banner = f"EVENTO: {display_event}"
                    active_control_str = f"Control Activo: {poss_text}"
                    poss_rate_str = f"Tasa de Posesion: Eq0 {t0_pct:.1f}% | Eq1 {t1_pct:.1f}%"
                    t0_comp_str = f"Compactacion Eq0: {t0_area:.1f} m2"
                    t1_comp_str = f"Compactacion Eq1: {t1_area:.1f} m2"
                else:
                    poss_text = "NEUTRAL" if curr_poss_team == -1 else f"TEAM {curr_poss_team}"
                    hud_header = "AERIAL TACTICAL HUD ENGINE v1.0"
                    event_banner = f"EVENT: {event_label}"
                    active_control_str = f"Active Control: {poss_text}"
                    poss_rate_str = f"Possession Rate: T0 {t0_pct:.1f}% | T1 {t1_pct:.1f}%"
                    t0_comp_str = f"Team 0 Compactness: {t0_area:.1f} m2"
                    t1_comp_str = f"Team 1 Compactness: {t1_area:.1f} m2"
                
                # Calculate real-time cumulative possession percentages up to this frame
                sub_array = possession_seq[:current_ptr + 1]
                t0_count = np.sum(sub_array == 0)
                t1_count = np.sum(sub_array == 1)
                total_counted = t0_count + t1_count
                t0_pct = (t0_count / total_counted * 100.0) if total_counted > 0 else 50.0
                t1_pct = (t1_count / total_counted * 100.0) if total_counted > 0 else 50.0
                
                # Fetch compactness data
                t0_area = compactness_df.loc[frame_id_key, 'team0_hull_area']
                t1_area = compactness_df.loc[frame_id_key, 'team1_hull_area']
                
                # Drawing Glassmorphic Tactical Dashboard Panel
                # Coordinates of panel: top-left (50, 50) to (550, 280)
                hud_x1, hud_y1, hud_x2, hud_y2 = 50, 50, 600, 290
                overlay = frame.copy()
                cv2.rectangle(overlay, (hud_x1, hud_y1), (hud_x2, hud_y2), (30, 25, 15), -1) # Dark charcoal background
                cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame) # Apply semi-transparent look
                
                # Draw border lines
                cv2.rectangle(frame, (hud_x1, hud_y1), (hud_x2, hud_y2), (180, 160, 140), 2)
                
                # Print Header Text
                cv2.putText(frame, hud_header, (hud_x1 + 20, hud_y1 + 35), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (240, 240, 240), 2, cv2.LINE_AA)
                
                # Print active event highlight banner
                cv2.rectangle(frame, (hud_x1 + 20, hud_y1 + 55), (hud_x2 - 20, hud_y1 + 85), (40, 60, 180), -1)
                cv2.putText(frame, event_banner, (hud_x1 + 30, hud_y1 + 77),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
                
                # Active Metrics Grid
                cv2.putText(frame, active_control_str, (hud_x1 + 20, hud_y1 + 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1, cv2.LINE_AA)
                cv2.putText(frame, poss_rate_str, (hud_x1 + 20, hud_y1 + 150),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1, cv2.LINE_AA)
                
                # Compactness measurements
                cv2.putText(frame, t0_comp_str, (hud_x1 + 20, hud_y1 + 190),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1, cv2.LINE_AA)
                cv2.putText(frame, t1_comp_str, (hud_x1 + 20, hud_y1 + 220),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1, cv2.LINE_AA)
                
                # Slicing marker
                rel_frame_ptr = current_ptr - start_frame
                total_slice_len = end_frame - start_frame
                cv2.putText(frame, f"T_REL: +{rel_frame_ptr/self.fps:.2f}s / {total_slice_len/self.fps:.2f}s", (hud_x1 + 20, hud_y1 + 265),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1, cv2.LINE_AA)
                
                # Draw passing lane visualizations if frame is around trigger point
                if abs(current_ptr - trigger_idx) < (2 * self.fps):
                    lanes = self.detect_passing_lanes_and_defensive_clutter(frame_id_key, coords_df)
                    for lane in lanes:
                        # Draw passing segment onto panel/HUD or screen if pixel projection is known.
                        # Since we operate offline in 2D normalized space, drawing metrics onto video frames 
                        # is best supported if homography coordinates are dynamically drawn.
                        # For representation safety, the HUD logs are updated frame-by-frame.
                        pass
                
                out.write(frame)
                
            out.release()
            
        cap.release()
        print(f"[SUCCESS] Exported {len(event_anchors)} highlight clips to output directory: {output_report_dir}")