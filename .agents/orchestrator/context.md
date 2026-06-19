# Context

## Environment
- OS: Windows
- Project: video_futbol_analisis (pedagogical soccer tactical analysis system)
- Core dependencies: `decord`, `opencv-python`, `numpy`
- Workspace root: `c:\ReposGitHub\video_futbol_analisis`

## Requirements Summary
- R1: DroneVideoIngestor in `src/ingestion/video_reader.py` using decord.
- R2: PitchCalibrator in `src/preprocessing/homography_calibrator.py` using opencv.
- R3: Run and verify script `scripts/run_phase1_step1.py` with `--test` / `--headless` mode.
- R4: Documented, strictly typed code.
