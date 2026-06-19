# Original User Request

## Initial Request — 2026-06-17T23:51:03Z

<USER_REQUEST>
This project implements the foundational modules (Phase 1, Step 1) of a modular, pedagogical soccer tactical analysis system: High-Performance Video Ingestion (using `decord`) and Homography Pitch Calibration (using OpenCV).

Working directory: `c:\ReposGitHub\video_futbol_analisis`
Integrity mode: demo

## Requirements

### R1. High-Performance Video Ingestion
* Create `src/ingestion/video_reader.py` containing a `DroneVideoIngestor` class using the `decord` library.
* It must support zero-copy frame retrieval on CPU, slice-based batch generation, and single frame fetching by index to bypass standard OpenCV CPU decoding bottlenecks on 4K drone footage.

### R2. Pitch Calibration (Homography Mapping)
* Create `src/preprocessing/homography_calibrator.py` containing a `PitchCalibrator` class.
* It must compute a 3x3 homography matrix transforming perspective-distorted camera views to a flat, top-down tactical grid of size `(1050, 680)`.
* It must support both:
  1. An interactive calibration mode (`calibrate_interactive`) utilizing OpenCV mouse click callbacks (Top-Left -> Top-Right -> Bottom-Right -> Bottom-Left).
  2. A programmatic non-interactive mode where calibration source points can be passed directly as arguments to allow automated headless testing.
* It must implement methods to warp whole frames (`apply_transform`) and project specific `(x, y)` coordinate arrays (`transform_coordinates`).

### R3. Execution and Automated Verification
* Create `scripts/run_phase1_step1.py` to orchestrate video ingestion and calibration.
* The script must look for a sample video at `data/raw/sample_drone_match.mp4` (which should be symlinked to `inputs/fecha06_1era.mp4`).
* It must support a `--test` or `--headless` mode that bypasses the mouse callback, uses pre-selected mock points, and saves 30 warped test frames in `data/processed/calibration_test/` to verify mathematical transformation correctness.

### R4. Pedagogical and Literate Programming Code Style
* Every module must contain extensive docstrings explaining the underlying mathematical or computer vision concept (e.g. projective geometry, homography scaling, hardware-accelerated decoding).
* Maintain strict typing and type hints across all classes.

## Acceptance Criteria

### Directory and Module Structure
- [ ] Folder structure exists: `src/ingestion/`, `src/preprocessing/`, `scripts/`, `data/raw/`, `data/processed/`.
- [ ] `__init__.py` files exist in `src/`, `src/ingestion/`, and `src/preprocessing/` to enable package imports.

### Functional Verification
- [ ] Running `python scripts/run_phase1_step1.py --test` finishes successfully without showing OpenCV GUI windows or hanging.
- [ ] The folder `data/processed/calibration_test/` contains 30 successfully warped top-down JPEG images of size `1050 x 680`.
- [ ] Bounding box coordinate transformations map correctly onto the target coordinates.
</USER_REQUEST>
