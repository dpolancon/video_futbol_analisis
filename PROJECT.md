# Project: soccer_tactical_analysis

## Architecture
This project implements the foundational modules of a modular, pedagogical soccer tactical analysis system.
1. **Video Ingestion Module**: High-performance video frame loading using `decord` on CPU. Bypasses standard OpenCV bottlenecks.
2. **Pitch Calibration Module**: Perspective transformation using OpenCV homography, converting camera views to a flat top-down tactical grid.
3. **Execution Script**: CLI script coordinating ingestion, calibration (interactive and headless), and automated validation.

## Code Layout
- `src/ingestion/video_reader.py`: Contains `DroneVideoIngestor`.
- `src/preprocessing/homography_calibrator.py`: Contains `PitchCalibrator`.
- `scripts/run_phase1_step1.py`: Ingestion & calibration coordinator.
- `data/raw/`: Place for raw videos/inputs.
- `data/processed/calibration_test/`: Place for processed output frames.

## Milestones
| # | Name | Scope | Dependencies | Status | Conv ID |
|---|------|-------|-------------|--------|---------|
| 1 | Exploration | Probe workspace, verify libraries (`decord`, `cv2`), check input files. | None | DONE | 0c0cab1d-60c4-4a21-b92b-2b0a63784d27 |
| 2 | E2E Test Suite | Design E2E test plan (`TEST_INFRA.md`) and create opaque-box E2E test cases. | Exploration | IN_PROGRESS | b0231053-7cb9-433b-bfa1-c1c9a8266321 |
| 3 | Video Ingestion | Implement `DroneVideoIngestor` in `src/ingestion/video_reader.py` with decord. | Exploration | IN_PROGRESS | 23074a09-95a6-45ac-a1aa-f1e4aaa15d21 |
| 4 | Pitch Calibration | Implement `PitchCalibrator` with interactive OpenCV and programmatic modes. | Video Ingestion | PLANNED | TBD |
| 5 | Execution Script | Create CLI tool `scripts/run_phase1_step1.py` with headless test mode. | Pitch Calibration, E2E Test Suite | PLANNED | TBD |
| 6 | Integration & Verification | Run full E2E test suite, perform adversarial hardening, and final audit. | Execution Script | PLANNED | TBD |

## Interface Contracts

### DroneVideoIngestor
- Class location: `src.ingestion.video_reader.DroneVideoIngestor`
- Public Methods:
  - `__init__(self, video_path: str)`: Initialize decord VideoReader.
  - `get_frame(self, index: int) -> np.ndarray`: Retrieve a single frame as a numpy array in RGB format (zero-copy if possible).
  - `get_batch(self, indices: list[int]) -> np.ndarray`: Retrieve multiple frames as a batch.
  - `__len__(self) -> int`: Total frame count.

### PitchCalibrator
- Class location: `src.preprocessing.homography_calibrator.PitchCalibrator`
- Public Methods:
  - `__init__(self, target_size: tuple[int, int] = (1050, 680))`: Target dimension of top-down tactical pitch.
  - `calibrate_interactive(self, video_path: str) -> np.ndarray`: Interactively get 4 points (Top-Left, Top-Right, Bottom-Right, Bottom-Left) and compute homography.
  - `calibrate_headless(self, src_points: np.ndarray) -> np.ndarray`: Programmatically compute 3x3 homography matrix from given 4 source points.
  - `apply_transform(self, frame: np.ndarray) -> np.ndarray`: Warp frame using the computed homography matrix to the target size.
  - `transform_coordinates(self, coords: np.ndarray) -> np.ndarray`: Transform a set of `(x, y)` pixel coordinates to the top-down tactical grid.
