"""
Automated Soccer Tracking and Drone Analytics Pipeline - Tactical Analysis Orchestrator
run_tactical_analysis.py

This script processes completed tracking trajectories using the FootballTacticalAnalyzer
to perform convex hull compactness calculations, generate possession-weighted heatmaps,
and extract key video highlights with HUD overlays in Spanish.
"""

import os
import argparse
import logging
import pandas as pd
import numpy as np

# Import the tactical engine
from football_tactical_analytics_engine import FootballTacticalAnalyzer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("tactical_analysis_runner")

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Advanced Tactical Analytics and Generate Spanish Reports"
    )
    parser.add_argument(
        "--match", "-m",
        type=str,
        default="",
        help="Match ID to analyze (e.g. fecha06_1era or fecha6_2nda). If blank, runs on all processed matches."
    )
    parser.add_argument(
        "--highlights",
        action="store_true",
        help="Extract video highlight clips with HUD overlays. (Slow on CPU for 4K video)."
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=47.95,
        help="Frame rate of the video. Default is 47.95 FPS."
    )
    return parser.parse_args()

def convert_to_tactical_df(pipeline_df: pd.DataFrame) -> pd.DataFrame:
    """
    Converts a pipeline trajectory DataFrame with index (frame_id, player_id)
    into the multi-level column DataFrame expected by FootballTacticalAnalyzer.
    """
    logger.info("Converting pipeline DataFrame to tactical schema index...")
    df_reset = pipeline_df.reset_index()
    
    # Map pipeline labels to match tactical classes ('player_team0', 'player_team1', 'ball', 'referee')
    def map_class(row):
        label = row['label']
        team_id = int(row['team_id'])
        if label == 'player':
            return f"player_team{team_id}" if team_id in [0, 1] else "referee"
        return label

    df_reset['tactical_class'] = df_reset.apply(map_class, axis=1)
    
    # Ensure correct coordinate columns are available
    x_col = 'x_meter' if 'x_meter' in df_reset.columns else 'x_pixel'
    y_col = 'y_meter' if 'y_meter' in df_reset.columns else 'y_pixel'
    
    # Pivot the table to create columns for each class, player, and axis
    pivoted_x = df_reset.pivot(index='frame_id', columns=['tactical_class', 'player_id'], values=x_col)
    pivoted_y = df_reset.pivot(index='frame_id', columns=['tactical_class', 'player_id'], values=y_col)
    
    # Merge x and y coordinates under a new MultiIndex level
    combined = pd.concat({'x': pivoted_x, 'y': pivoted_y}, axis=1)
    
    # Reorder levels to: [tactical_class, player_id, coordinate_axis]
    # combined columns are currently: [coordinate_axis ('x'/'y'), tactical_class, player_id]
    combined = combined.reorder_levels([1, 2, 0], axis=1)
    combined.sort_index(axis=1, inplace=True)
    
    return combined

def run_analysis_for_match(match_id: str, run_highlights: bool, fps: float) -> None:
    logger.info("=" * 60)
    logger.info(f"Running Tactical Analytics in Spanish for Match: {match_id}")
    logger.info("=" * 60)
    
    # Locate trajectory files
    trajectory_file = os.path.abspath(f"outputs/{match_id}/final_dataset/trajectories.csv")
    reports_dir = os.path.abspath(f"outputs/{match_id}/reports")
    video_path = os.path.abspath(f"inputs/{match_id}.mp4")
    
    if not os.path.exists(trajectory_file):
        logger.error(f"Tracking data trajectories file not found at: {trajectory_file}")
        logger.error("Please run the main pipeline first to generate the coordinates dataset.")
        return
        
    os.makedirs(reports_dir, exist_ok=True)
    
    # 1. Load pipeline trajectories
    logger.info(f"Loading trajectory coordinates from {trajectory_file}...")
    pipeline_df = pd.read_csv(trajectory_file, index_col=["frame_id", "player_id"])
    
    # 2. Convert to tactical MultiIndex schema
    tactical_df = convert_to_tactical_df(pipeline_df)
    
    # 3. Instantiate tactical analyzer in Spanish
    logger.info("Initializing FootballTacticalAnalyzer with Spanish language settings...")
    analyzer = FootballTacticalAnalyzer(fps=int(fps), language="es")
    
    # 4. Compute Team Compactness metrics
    logger.info("Calculating team tactical compactness (Convex Hull Area & SDD)...")
    compactness_df = analyzer.calculate_team_compactness(tactical_df)
    
    # Translate compactness column headers to Spanish for reporting
    compactness_es = compactness_df.rename(columns={
        "team0_centroid_x": "centroide_x_eq0",
        "team0_centroid_y": "centroide_y_eq0",
        "team0_hull_area": "area_convex_hull_eq0_m2",
        "team0_sdd": "desviacion_estandar_distancia_eq0_m",
        "team1_centroid_x": "centroide_x_eq1",
        "team1_centroid_y": "centroide_y_eq1",
        "team1_hull_area": "area_convex_hull_eq1_m2",
        "team1_sdd": "desviacion_estandar_distancia_eq1_m"
    })
    
    compactness_csv_path = os.path.join(reports_dir, "metricas_compactacion_es.csv")
    compactness_es.to_csv(compactness_csv_path)
    logger.info(f"Spanish compactness metrics saved: {compactness_csv_path}")
    
    # 5. Generate Possession-Weighted Heatmaps in Spanish
    logger.info("Generating possession-weighted spatial heatmaps...")
    analyzer.generate_possession_weighted_heatmaps(tactical_df, reports_dir)
    # Rename default heatmap filename to Spanish
    default_heatmap_path = os.path.join(reports_dir, "possession_weighted_heatmaps.png")
    spanish_heatmap_path = os.path.join(reports_dir, "mapas_calor_posesion_es.png")
    if os.path.exists(default_heatmap_path):
        if os.path.exists(spanish_heatmap_path):
            os.remove(spanish_heatmap_path)
        os.rename(default_heatmap_path, spanish_heatmap_path)
        logger.info(f"Spanish heatmaps generated: {spanish_heatmap_path}")
        
    # 6. Optional: Extract Highlight clips with Spanish HUD
    if run_highlights:
        if not os.path.exists(video_path):
            logger.warning(f"Video file not found at {video_path}; skipping highlight video extraction.")
        else:
            logger.info("Extracting highlight clips with Spanish HUD overlays (Counter-Attacks, Turnovers)...")
            analyzer.extract_highlight_clips(video_path, tactical_df, reports_dir)
    else:
        logger.info("Highlight video clip extraction skipped. Run with --highlights to extract MP4 HUD clips.")
        
    logger.info(f"Tactical analysis successfully completed for Match {match_id}.")

def main() -> None:
    args = parse_arguments()
    
    if args.match:
        run_analysis_for_match(args.match, args.highlights, args.fps)
    else:
        # Auto-discover already processed matches under outputs/
        processed_folders = [d for d in os.listdir("outputs") if os.path.isdir(os.path.join("outputs", d))]
        # Filter out git folder markers
        processed_folders = [f for f in processed_folders if f not in [".gitkeep", ".git"]]
        
        if not processed_folders:
            logger.warning("No processed matches found in outputs/ directory.")
            logger.info("Run the main pipeline first or specify a match folder.")
            return
            
        logger.info(f"Discovered processed match folders: {processed_folders}")
        for match in processed_folders:
            run_analysis_for_match(match, args.highlights, args.fps)

if __name__ == "__main__":
    main()
