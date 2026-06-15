"""
Automated Soccer Tracking and Drone Analytics Pipeline - Orchestration Entrypoint
main.py

This script coordinates the soccer video tracking pipeline, loading components 
sequentially and orchestrating the data flow from raw video to downstream analytical insights.
It supports real video loading via OpenCV (with seeking sub-sampling) and generates 
multi-format reports (CSV, MD, HTML Dashboard).
"""

import os
import glob
import json
import argparse
import logging
import datetime
import numpy as np
import pandas as pd

# Pipeline imports
from core.detector import DroneDetector
from core.tracker import DroneTracker
from core.homography import PitchRegistrator
from wrappers.data_layers import TrajectoryDataLayer
import analytics

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("pipeline_orchestrator")

def parse_arguments() -> argparse.Namespace:
    """
    Parses command-line arguments.

    Returns:
        argparse.Namespace: Object containing argument values.
    """
    parser = argparse.ArgumentParser(
        description="Automated Offline Soccer Tracking and Drone Analytics Data Pipeline (Option 1)"
    )
    parser.add_argument(
        "--video", "-v",
        type=str,
        default="",
        help="Path to the input raw mp4 video asset. Required if not running in batch mode."
    )
    parser.add_argument(
        "--batch", "-b",
        action="store_true",
        help="Process all .mp4 files found in the inputs/ folder sequentially."
    )
    parser.add_argument(
        "--frames", "-f",
        type=int,
        default=0,
        help="Limit number of frames to process per video. Set to 0 for unlimited (entire video)."
    )
    parser.add_argument(
        "--stride", "-s",
        type=int,
        default=30,
        help="Sub-sampling stride factor. Stride 30 processes 1 Frame Per Second for 30 FPS video."
    )
    parser.add_argument(
        "--resize-1080p",
        action="store_true",
        help="Downscale high-resolution frames (e.g. 4K) to 1080p to optimize processing speed."
    )
    parser.add_argument(
        "--weights",
        type=str,
        default="yolov8-p2s3a.pt",
        help="Path to YOLO weights file. Fallback is simulated detections."
    )
    parser.add_argument(
        "--iou-threshold",
        type=float,
        default=0.7,
        help="Tracker overlapping bounding box IoU threshold. Default is 0.7."
    )
    return parser.parse_args()

def setup_pipeline_directories(match_id: str) -> dict:
    """
    Creates structural output directories for intermediate pipeline deliverables.

    Args:
        match_id (str): Derived ID of the match from the video file name.

    Returns:
        dict: Dictionary mapping directory keys to their absolute path strings.
    """
    base_output_dir = os.path.abspath(f"outputs/{match_id}")
    
    subdirs = {
        "base": base_output_dir,
        "raw_detections": os.path.join(base_output_dir, "raw_detections"),
        "tracklets": os.path.join(base_output_dir, "tracklets"),
        "calibration": os.path.join(base_output_dir, "calibration"),
        "final_dataset": os.path.join(base_output_dir, "final_dataset"),
        "reports": os.path.join(base_output_dir, "reports")
    }
    
    for name, path in subdirs.items():
        os.makedirs(path, exist_ok=True)
        logger.debug(f"Directory verified/created: {path}")
        
    return subdirs

def generate_markdown_report(
    filepath: str, 
    match_id: str, 
    stats: dict, 
    possession_df: pd.DataFrame
) -> None:
    """
    Generates a structured, clean Markdown summary report.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Calculate possession metrics
    tot_frames = len(possession_df)
    if tot_frames > 0:
        counts = possession_df["possession_team_id"].value_counts()
        team_0_count = counts.get(0, 0)
        team_1_count = counts.get(1, 0)
        uncontested_count = counts.get(-1, 0)
        
        team_0_pct = (team_0_count / tot_frames) * 100
        team_1_pct = (team_1_count / tot_frames) * 100
        uncontested_pct = (uncontested_count / tot_frames) * 100
    else:
        team_0_pct = team_1_pct = uncontested_pct = 0.0
        
    # Calculate streaks
    streaks = {0: 0, 1: 0}
    current_team = -1
    current_streak = 0
    for team in possession_df["possession_team_id"]:
        if team in [0, 1]:
            if team == current_team:
                current_streak += 1
            else:
                if current_team in [0, 1]:
                    streaks[current_team] = max(streaks[current_team], current_streak)
                current_team = team
                current_streak = 1
        else:
            if current_team in [0, 1]:
                streaks[current_team] = max(streaks[current_team], current_streak)
            current_team = -1
            current_streak = 0
            
    if current_team in [0, 1]:
        streaks[current_team] = max(streaks[current_team], current_streak)

    fps_adj = stats["fps"] / stats["stride"]
    team_0_streak_sec = streaks[0] / fps_adj if fps_adj > 0 else 0
    team_1_streak_sec = streaks[1] / fps_adj if fps_adj > 0 else 0

    content = f"""# Soccer Match Analysis Report
**Match Identifier**: `{match_id}`  
**Report Generated**: `{now}`

## 1. Video Metadata
* **Source Filename**: `{stats["filename"]}`
* **Native Resolution**: `{stats["width"]} x {stats["height"]}`
* **Frame Rate**: `{stats["fps"]:.2f} FPS`
* **Total Video Frames**: `{stats["total_frames"]:,}`
* **Sub-sampling Stride**: `{stats["stride"]} (processed 1 frame every {stats["stride"]} frames)`
* **Total Processed Frames**: `{stats["processed_frames"]:,}`
* **Effective Analytics Time**: `{stats["processed_frames"] / fps_adj:.2f} seconds` (approx. `{(stats["processed_frames"] / fps_adj) / 60.0:.2f} minutes`)

## 2. Possession Summary Statistics
Based on normalized spatial proximity algorithms from Guo et al. (2026):

| Category | Frames | Share (%) | Total Time (Est) |
| :--- | :--- | :--- | :--- |
| **Team 0 (Estrella Roja)** | `{team_0_count}` | `{team_0_pct:.2f}%` | `{team_0_count / fps_adj:.1f}s` |
| **Team 1 (Norton Contreras)** | `{team_1_count}` | `{team_1_pct:.2f}%` | `{team_1_count / fps_adj:.1f}s` |
| **Uncontested / Ball Out** | `{uncontested_count}` | `{uncontested_pct:.2f}%` | `{uncontested_count / fps_adj:.1f}s` |

## 3. High-Performance Metrics
* **Estrella Roja Max Uninterrupted Streak**: `{streaks[0]} frames` (`{team_0_streak_sec:.1f} seconds`)
* **Norton Contreras Max Uninterrupted Streak**: `{streaks[1]} frames` (`{team_1_streak_sec:.1f} seconds`)
* **Ball Detection Rate**: `{possession_df["ball_detected"].mean() * 100:.1f}%`

---
*Report generated programmatically via the Drone Tracking & Analytics Pipeline.*
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"Markdown report generated: {filepath}")

def generate_html_dashboard(
    filepath: str, 
    match_id: str, 
    stats: dict, 
    possession_df: pd.DataFrame
) -> None:
    """
    Generates a standalone, rich-aesthetic HTML interactive dashboard with Chart.js.
    """
    # Prepare chart data
    tot_frames = len(possession_df)
    if tot_frames > 0:
        counts = possession_df["possession_team_id"].value_counts()
        team_0_share = float(counts.get(0, 0))
        team_1_share = float(counts.get(1, 0))
        uncontested_share = float(counts.get(-1, 0))
    else:
        team_0_share = team_1_share = uncontested_share = 0.0

    timeline_data = []
    timeline_labels = []
    
    # Take a maximum of 100 points for the timeline chart to prevent page clutter
    step = max(1, tot_frames // 100)
    for i in range(0, tot_frames, step):
        row = possession_df.iloc[i]
        frame_id = possession_df.index[i]
        team_id = int(row["possession_team_id"])
        
        # Human-readable labels
        if team_id == 0:
            label = "Estrella Roja (Team 0)"
            val = 0
        elif team_id == 1:
            label = "Norton Contreras (Team 1)"
            val = 1
        else:
            label = "Uncontested"
            val = -1
            
        timeline_labels.append(f"F-{frame_id}")
        timeline_data.append(val)

    # Convert to JSON for injection
    chart_shares_json = json.dumps([team_0_share, team_1_share, uncontested_share])
    timeline_labels_json = json.dumps(timeline_labels)
    timeline_data_json = json.dumps(timeline_data)
    
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_content = f"""<!DOCTYPE html>
<html lang="en" class="h-full bg-slate-950 text-slate-100">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Match Performance Dashboard - {match_id}</title>
    <!-- Tailwind CSS for styling -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Chart.js for data visualization -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    colors: {{
                        brandTeal: '#06b6d4',
                        brandViolet: '#6366f1',
                    }}
                }}
            }}
        }}
    </script>
    <style>
        .glass-panel {{
            background: rgba(30, 41, 59, 0.7);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }}
    </style>
</head>
<body class="min-h-full flex flex-col font-sans">

    <!-- Header Section -->
    <header class="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <span class="text-2xl font-black bg-gradient-to-r from-cyan-400 to-indigo-500 bg-clip-text text-transparent tracking-wider">
                    SOCCER ANALYTICS
                </span>
                <span class="text-xs bg-slate-800 px-2.5 py-1 rounded-full text-slate-400 font-medium">Pipeline Option 1</span>
            </div>
            <div class="text-right text-xs text-slate-400">
                Generated: <span class="font-mono text-slate-200">{now}</span>
            </div>
        </div>
    </header>

    <!-- Main Content Area -->
    <main class="flex-grow max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        
        <!-- Welcome / Title Row -->
        <div class="flex flex-col md:flex-row md:items-center md:justify-between space-y-4 md:space-y-0">
            <div>
                <h1 class="text-3xl font-extrabold text-white tracking-tight">Match Dashboard</h1>
                <p class="text-slate-400 mt-1">Real-time statistics extracted via high-altitude drone tracking pipeline.</p>
            </div>
            <div class="flex items-center space-x-3">
                <span class="text-sm font-semibold text-slate-300">Match ID:</span>
                <span class="font-mono bg-cyan-950/60 border border-cyan-800/50 text-cyan-400 px-4 py-1.5 rounded-lg text-sm font-bold">
                    {match_id}
                </span>
            </div>
        </div>

        <!-- Metrics Grid -->
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="glass-panel p-6 rounded-2xl flex flex-col justify-between">
                <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Video Filename</span>
                <span class="text-lg font-bold text-white mt-2 truncate" title="{stats["filename"]}">{stats["filename"]}</span>
            </div>
            <div class="glass-panel p-6 rounded-2xl flex flex-col justify-between">
                <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Inference Size</span>
                <span class="text-2xl font-black text-cyan-400 mt-2">{stats["width"]} × {stats["height"]}</span>
            </div>
            <div class="glass-panel p-6 rounded-2xl flex flex-col justify-between">
                <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Frame Skip Stride</span>
                <span class="text-2xl font-black text-indigo-400 mt-2">1 in {stats["stride"]} <span class="text-xs font-normal text-slate-400">({stats["fps"]:.1f} FPS)</span></span>
            </div>
            <div class="glass-panel p-6 rounded-2xl flex flex-col justify-between">
                <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Processed Frames</span>
                <span class="text-2xl font-black text-emerald-400 mt-2">{stats["processed_frames"]} / {stats["total_frames"]}</span>
            </div>
        </div>

        <!-- Analytics Charts Grid -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            
            <!-- Possession Share Card -->
            <div class="glass-panel p-6 rounded-3xl lg:col-span-1 flex flex-col">
                <h3 class="text-lg font-bold text-white tracking-tight">Possession Share</h3>
                <p class="text-xs text-slate-400 mb-6">Normalized player proximity ratio (Guo et al. 2026)</p>
                <div class="relative flex-grow flex items-center justify-center min-h-[250px]">
                    <canvas id="possessionDoughnut"></canvas>
                </div>
            </div>

            <!-- Timeline Chart Card -->
            <div class="glass-panel p-6 rounded-3xl lg:col-span-2 flex flex-col">
                <h3 class="text-lg font-bold text-white tracking-tight">Possession Flow Timeline</h3>
                <p class="text-xs text-slate-400 mb-6">Chronological timeline of state handovers (1 represents Norton Contreras, 0 Estrella Roja, -1 Uncontested)</p>
                <div class="relative flex-grow min-h-[250px]">
                    <canvas id="possessionTimeline"></canvas>
                </div>
            </div>

        </div>

    </main>

    <!-- Footer -->
    <footer class="border-t border-slate-900 bg-slate-950 py-6 text-center text-xs text-slate-500">
        &copy; 2026 Soccer Tracking and Analytics Data Pipeline. Developed with Advanced AI Agents.
    </footer>

    <!-- Chart Configuration Script -->
    <script>
        document.addEventListener("DOMContentLoaded", function() {{
            const shareData = {chart_shares_json};
            const timelineLabels = {timeline_labels_json};
            const timelineData = {timeline_data_json};

            // Doughnut Chart
            const ctxDoughnut = document.getElementById('possessionDoughnut').getContext('2d');
            new Chart(ctxDoughnut, {{
                type: 'doughnut',
                data: {{
                    labels: ['Estrella Roja (Team 0)', 'Norton Contreras (Team 1)', 'Uncontested/Out'],
                    datasets: [{{
                        data: shareData,
                        backgroundColor: [
                            'rgba(6, 182, 212, 0.8)',   // Cyan
                            'rgba(99, 102, 241, 0.8)',  // Indigo
                            'rgba(148, 163, 184, 0.4)'  // Slate Gray
                        ]],
                        borderColor: [
                            '#06b6d4',
                            '#6366f1',
                            '#94a3b8'
                        ],
                        borderWidth: 2
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{
                            position: 'bottom',
                            labels: {{
                                color: '#cbd5e1',
                                font: {{ family: 'sans-serif', size: 11 }}
                            }}
                        }}
                    }}
                }}
            }});

            // Timeline Chart
            const ctxTimeline = document.getElementById('possessionTimeline').getContext('2d');
            new Chart(ctxTimeline, {{
                type: 'line',
                data: {{
                    labels: timelineLabels,
                    datasets: [{{
                        label: 'Possession Owner',
                        data: timelineData,
                        borderColor: 'rgba(6, 182, 212, 0.8)',
                        backgroundColor: 'rgba(6, 182, 212, 0.1)',
                        borderWidth: 2,
                        stepped: true,
                        fill: true,
                        pointRadius: 0,
                        tension: 0.1
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        y: {{
                            min: -1.2,
                            max: 1.2,
                            ticks: {{
                                callback: function(value) {{
                                    if (value === 1) return 'Norton Contreras';
                                    if (value === 0) return 'Estrella Roja';
                                    if (value === -1) return 'Uncontested';
                                    return '';
                                }},
                                color: '#94a3b8'
                            }},
                            grid: {{ color: 'rgba(255, 255, 255, 0.05)' }}
                        }},
                        x: {{
                            ticks: {{ color: '#94a3b8', maxTicksLimit: 15 }},
                            grid: {{ display: false }}
                        }}
                    }},
                    plugins: {{
                        legend: {{ display: false }}
                    }}
                }}
            }});
        }});
    </script>
</body>
</html>
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info(f"Interactive dashboard generated: {filepath}")

def process_single_video(video_path: str, args: argparse.Namespace) -> None:
    """
    Processes a single video file.
    """
    video_filename = os.path.basename(video_path)
    match_id = os.path.splitext(video_filename)[0]
    
    logger.info("=" * 60)
    logger.info(f"Starting Soccer Tracking Pipeline for Match: {match_id}")
    logger.info(f"Target Video Path: {video_path}")
    logger.info(f"Configuration: Stride={args.stride}, MaxFrames={args.frames if args.frames > 0 else 'Full'}")
    logger.info("=" * 60)
    
    # Setup directories
    output_dirs = setup_pipeline_directories(match_id)
    
    # Initialize components
    detector = DroneDetector(model_weights=args.weights)
    tracker = DroneTracker(iou_threshold=args.iou_threshold)
    registrator = PitchRegistrator()
    data_layer = TrajectoryDataLayer(registrator=registrator)
    
    # Setup calibration matrix
    calibration_matrix = registrator.default_homography
    calibration_file = os.path.join(output_dirs["calibration"], "homography_matrix.npy")
    np.save(calibration_file, calibration_matrix)
    logger.info(f"Saved homography calibration parameters to {calibration_file}")

    # Variables to track execution
    total_video_frames = 0
    processed_count = 0
    width, height = 1920, 1080
    fps = 30.0
    
    # Try using OpenCV for actual video reading
    has_cv2 = False
    cap = None
    
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            has_cv2 = True
            total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if fps <= 0:
                fps = 30.0
            logger.info(f"OpenCV successfully loaded video. Metadata: {width}x{height} @ {fps:.2f} FPS. Total Frames: {total_video_frames:,}")
        else:
            logger.warning(f"OpenCV could not open video file: {video_path}. Falling back to simulation.")
    except ImportError:
        logger.warning("OpenCV (cv2) is not installed. Falling back to simulation.")
    except Exception as e:
        logger.warning(f"Error opening video {video_path}: {e}. Falling back to simulation.")

    if has_cv2 and cap is not None:
        # Loop with Seek Optimization to skip frames
        frame_idx = 0
        limit_frames = args.frames if args.frames > 0 else total_video_frames
        
        while frame_idx < total_video_frames and processed_count < limit_frames:
            # Seek to target frame index
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                break
                
            frame_id = frame_idx + 1
            
            # Optional Downscaling for speed/accuracy trade-off
            if args.resize_1080p and (width > 1920 or height > 1080):
                frame = cv2.resize(frame, (1920, 1080))
                
            # Process Frame
            detections = detector.process_frame(frame)
            track_ids = tracker.update(detections)
            
            # Save raw detections for debug
            # In production, you would save this as a JSON or raw text file
            
            # Feed data layer
            data_layer.add_frame_data(
                frame_id=frame_id, 
                track_ids=track_ids, 
                detections=detections, 
                homography_matrix=calibration_matrix
            )
            
            processed_count += 1
            frame_idx += args.stride
            
            if processed_count % 10 == 0:
                logger.info(f"Processed {processed_count} frames (Last frame index: {frame_idx})...")
        cap.release()
    else:
        # Fallback simulated frame loop
        # We simulate a 2-minute slice of video at 30 fps (3600 frames)
        sim_total = 3600 if args.frames == 0 else args.frames
        logger.info(f"Simulating pipeline execution for {sim_total} frames with stride {args.stride}...")
        
        dummy_frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame_idx = 0
        while frame_idx < sim_total:
            frame_id = frame_idx + 1
            detections = detector.process_frame(dummy_frame)
            track_ids = tracker.update(detections)
            data_layer.add_frame_data(
                frame_id=frame_id, 
                track_ids=track_ids, 
                detections=detections, 
                homography_matrix=calibration_matrix
            )
            processed_count += 1
            frame_idx += args.stride
        total_video_frames = sim_total

    # Serialize trajectory data
    logger.info("Serializing processed trajectory records...")
    csv_out_path = os.path.join(output_dirs["final_dataset"], "trajectories.csv")
    parquet_out_path = os.path.join(output_dirs["final_dataset"], "trajectories.parquet")
    
    data_layer.save_to_csv(csv_out_path)
    data_layer.save_to_parquet(parquet_out_path)
    
    trajectory_df = data_layer.to_dataframe()
    logger.info(f"Structured trajectory dataset generated: {trajectory_df.shape[0]} total tracklet points.")
    
    # Downstream Analytics
    logger.info("Executing downstream analytics skills...")
    try:
        PossessionClass = analytics.get_skill("possession")
        possession_analyzer = PossessionClass(t_in=1.5, t_out=2.5)
        
        possession_summary_df = possession_analyzer.calculate_possession(trajectory_df)
        
        # Save CSV possession logs
        possession_csv_path = os.path.join(output_dirs["reports"], "possession_summary.csv")
        possession_summary_df.to_csv(possession_csv_path)
        
        # Gather execution stats for report injection
        execution_stats = {
            "filename": video_filename,
            "width": width,
            "height": height,
            "fps": fps,
            "total_frames": total_video_frames,
            "stride": args.stride,
            "processed_frames": processed_count
        }
        
        # Save Markdown and HTML reports
        md_report_path = os.path.join(output_dirs["reports"], "match_report.md")
        html_report_path = os.path.join(output_dirs["reports"], "dashboard.html")
        
        generate_markdown_report(md_report_path, match_id, execution_stats, possession_summary_df)
        generate_html_dashboard(html_report_path, match_id, execution_stats, possession_summary_df)
        
        # Output console summary
        team_possessions = possession_summary_df["possession_team_id"].value_counts(normalize=True) * 100
        logger.info("=" * 60)
        logger.info(f"MATCH {match_id} COMPLETION SUMMARY:")
        logger.info("=" * 60)
        for team, pct in team_possessions.items():
            team_label = "Uncontested/Ball-Out" if team == -1 else f"Team {int(team)}"
            logger.info(f" -> Possession {team_label}: {pct:.2f}%")
        logger.info("=" * 60)
        
    except KeyError as e:
        logger.error(f"Downstream possession skill not registered: {e}")
    except Exception as e:
        logger.exception(f"Error executing analytics: {e}")

def main() -> None:
    """
    Main pipeline execution flow.
    """
    args = parse_arguments()
    
    if args.batch:
        logger.info("Batch mode enabled. Scanning inputs/ directory for video assets...")
        # Search for all mp4 videos in inputs
        video_files = glob.glob(os.path.join("inputs", "*.mp4"))
        
        if not video_files:
            logger.error("No video assets (*.mp4) found in inputs/ directory.")
            return
            
        logger.info(f"Discovered {len(video_files)} video assets in inputs/: {[os.path.basename(f) for f in video_files]}")
        
        for idx, video_path in enumerate(video_files, 1):
            logger.info(f"\nProcessing Video {idx}/{len(video_files)}...")
            process_single_video(video_path, args)
            
        logger.info("\nAll batch video analytics processed successfully.")
    else:
        # Standard single video mode
        if not args.video:
            logger.error("No input video specified. Please provide a video path using --video or run in --batch mode.")
            return
            
        process_single_video(args.video, args)

if __name__ == "__main__":
    main()
