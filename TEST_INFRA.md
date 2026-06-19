# Advanced Soccer Tracking and Drone Analytics Pipeline - E2E Testing Infrastructure

This document outlines the testing strategy, speed optimizations, and full catalog of designed End-to-End (E2E) integration test cases for the Automated Soccer Tracking and Drone Analytics Pipeline.

---

## 1. Testing Strategy Overview

The testing framework is built on an **opaque-box E2E testing paradigm**. Due to the high computational cost of processing production match videos (~17-18 GB each), live datasets are replaced with programmatically generated, low-overhead mocks.

### 4-Tier Test Classification

```
+-----------------------------------------------------------------+
|               TIER 4: REAL-WORLD SCENARIOS                      |
| (Full walkthroughs, batching, edge matchups, CLI scripts run)  |
+-----------------------------------------------------------------+
                                |
+-----------------------------------------------------------------+
|             TIER 3: CROSS-FEATURE COMBINATIONS                  |
| (Pairwise interactions, trackers to Re-ID, homography to math)  |
+-----------------------------------------------------------------+
                                |
+-----------------------------------------------------------------+
|             TIER 2: BOUNDARY & CORNER CASES                     |
| (Empty videos, collinear hulls, extreme distortions, outliers)   |
+-----------------------------------------------------------------+
                                |
+-----------------------------------------------------------------+
|               TIER 1: FEATURE COVERAGE                          |
| (Baseline checks, parameter bounds, nominal functionality)      |
+-----------------------------------------------------------------+
```

1. **Tier 1: Feature Coverage** (N = 25): Evaluates standard operations under nominal input bounds for all 5 core features.
2. **Tier 2: Boundary & Corner Cases** (N = 25): Probes failure resilience, division-by-zeros, out-of-bounds coords, corrupt inputs, and math singularities.
3. **Tier 3: Cross-Feature Combinations** (N = 5): Verifies data flow integrity and state transfer across independent modules.
4. **Tier 4: Real-World Scenarios** (N = 5): Validates complete system entrypoints (`main.py` and `run_tactical_analysis.py`) in subprocesses.

---

## 2. Speed Optimization Principles

To keep E2E tests executing within milliseconds per test, we utilize four speed-gating patterns:

1. **Programmatic Mock Video Generation**: Generates 2-10 frame BGR/HSV green pitch mocks via `cv2.VideoWriter`. Avoids binary bloat in the git repository and disk read latency.
2. **Mandatory Frame/Stride Gating**: Passes `-f 2` or `-f 5` and `--stride 30` to subprocess executions, causing CLI loops to exit almost instantly.
3. **Simulated Detector Fallbacks**: Passes `--weights mock_none.pt` to trigger the automatic detection simulation fallback, bypassing heavy PyTorch model initialization.
4. **Direct Trajectory Mocking**: Programmatically generates mini `trajectories.csv` tables to verify downstream metrics in isolation.

---

## 3. Core Features Map

The E2E testing plan covers 5 primary features:

* **Feature 1: Video Ingestion & Object Detection**: Frame streaming via OpenCV, stride sub-sampling, downscaling, and object identification (`player`, `ball`, `referee`) with DBSCAN player color clustering.
* **Feature 2: Multi-Object Tracking (MOT) & Split Management**: Target associations via Hungarian algorithm (IoU + distance + hue cost), lost target archiving, and high-IoU splits.
* **Feature 3: Pitch Registration & Homography Mapping**: Camera-to-grid coordinate transforms using 3x3 homography projection matrices with DLT solver fallbacks and coordinate boundary clamping.
* **Feature 4: Trajectory Post-Processing & Interpolation**: Offline temporal Re-ID stitching and quadratic curve fitting for ball gaps.
* **Feature 5: Tactical & Possession Analytics**: Mathematical algorithms calculating possession hysteresis (Guo et al. 2026), convex hull compactness, passing lanes, and Spanish HUD overlays.

---

## 4. Test Catalog (N = 60)

### Tier 1: Feature Coverage (N = 25)

#### Feature 1: Video Ingestion & Object Detection
1. **`test_tier1_f1_ingest_standard_video`**: Verifies that standard video is successfully opened and parsed by OpenCV.
2. **`test_tier1_f1_ingest_stride_subsampling`**: Checks that frame skipping logic resolves indices correctly under a custom stride.
3. **`test_tier1_f1_ingest_frame_limiter`**: Confirms frame limits stop the frame iteration loop at the target count.
4. **`test_tier1_f1_ingest_downscaling_active`**: Ensures resizing high-resolution frames (e.g. 4K to 1080p) performs downscaling.
5. **`test_tier1_f1_detector_clustering_teams`**: Verifies DBSCAN clusters mock player color hues into Team 0 and Team 1.

#### Feature 2: Multi-Object Tracking (MOT) & Split Management
6. **`test_tier1_f2_tracker_kalman_prediction`**: Checks constant-velocity motion predictions by the Kalman filter.
7. **`test_tier1_f2_tracker_hungarian_assignment`**: Verifies track ID continuity for stable sequential target detections.
8. **`test_tier1_f2_tracker_track_archiving`**: Confirms that lost tracks are archived after exceeding `max_lost_frames`.
9. **`test_tier1_f2_tracker_team_identification`**: Checks that tracking data maintains correct team IDs.
10. **`test_tier1_f2_tracker_split_enforcement`**: Verifies that colliding tracks (IoU >= threshold) are split and terminated to prevent ID swaps.

#### Feature 3: Pitch Registration & Homography Mapping
11. **`test_tier1_f3_homography_default_projection`**: Checks that the default homography projects image pixels to positive real-world meters.
12. **`test_tier1_f3_homography_custom_calculation`**: Computes a custom homography matrix using 4 point anchors.
13. **`test_tier1_f3_homography_numpy_fallback`**: Runs the NumPy DLT SVD solver fallback when OpenCV is mocked as unavailable.
14. **`test_tier1_f3_homography_coord_clamping`**: Confirms that out-of-pitch projected points clamp inside `[0.0, 105.0]x[0.0, 68.0]`.
15. **`test_tier1_f3_homography_point_mapping_player_vs_ball`**: Verifies that players are mapped at ymax (feet) and the ball at centroid center.

#### Feature 4: Trajectory Post-Processing & Interpolation
16. **`test_tier1_f4_postprocess_parquet_serialization`**: Verifies dataframe saving and reading using Parquet.
17. **`test_tier1_f4_postprocess_csv_serialization`**: Confirms backup saving to CSV format.
18. **`test_tier1_f4_postprocess_reid_stitching_active`**: Checks that offline Re-ID merges matching fragmented tracklets within the temporal gate.
19. **`test_tier1_f4_postprocess_reid_stitching_temporal_gate`**: Ensures Re-ID stitching rejects merges separated by gaps larger than `max_gap_frames`.
20. **`test_tier1_f4_postprocess_ball_imputation_quadratic`**: Verifies that missing ball coordinate gaps are filled using a quadratic motion fit.

#### Feature 5: Tactical & Possession Analytics
21. **`test_tier1_f5_possession_metrics_standard`**: Confirms possession switches to the closest player.
22. **`test_tier1_f5_possession_hysteresis_gate`**: Verifies that possession does not toggle rapidly when distances hover between T_in and T_out.
23. **`test_tier1_f5_analytics_compactness_calculation`**: Checks Convex Hull area and centroid calculations.
24. **`test_tier1_f5_analytics_passing_lanes`**: Checks passing lane blocking verification against defending players.
25. **`test_tier1_f5_reports_generation`**: Confirms that running downstream analytics outputs possession summaries, reports, and Spanish logs.

---

### Tier 2: Boundary & Corner Cases (N = 25)

#### Feature 1: Video Ingestion & Object Detection
26. **`test_tier2_f1_ingest_empty_video`**: Checks that empty (0-byte) files are caught and handled safely.
27. **`test_tier2_f1_ingest_invalid_format`**: Verifies graceful exit when reading corrupt non-video files.
28. **`test_tier2_f1_detector_no_detections_in_frame`**: Confirms solid blank frames return empty boxes without error.
29. **`test_tier2_f1_detector_dbscan_outliers`**: Verifies color outliers are tagged as team -1 (noise).
30. **`test_tier2_f1_detector_invalid_weights_path`**: Confirms that non-existent model weight paths trigger automatic simulated generator fallbacks.

#### Feature 2: Multi-Object Tracking (MOT) & Split Management
31. **`test_tier2_f2_tracker_no_detections`**: Confirms updating a tracker with empty detections is handled safely.
32. **`test_tier2_f2_tracker_extreme_iou_collision`**: Verifies immediate split termination on perfect overlaps (IoU = 1.0).
33. **`test_tier2_f2_tracker_track_id_overflow`**: Confirms high track ID values (e.g. >10^7) do not crash the tracker index.
34. **`test_tier2_f2_tracker_duplicate_detections`**: Verifies tracker processes overlapping duplicate detections without index failure.
35. **`test_tier2_f2_tracker_abrupt_velocity_change`**: Confirms extreme velocity jumps start new tracklets rather than misassociating.

#### Feature 3: Pitch Registration & Homography Mapping
36. **`test_tier2_f3_homography_collinear_points`**: Checks homography solver robustness when points are mathematically collinear.
37. **`test_tier2_f3_homography_insufficient_points`**: Asserts that sending < 4 point correspondences throws a ValueError.
38. **`test_tier2_f3_homography_zero_w_coordinate`**: Verifies that division-by-zero on homogeneous coord projection resolves to `(0.0, 0.0)`.
39. **`test_tier2_f3_homography_extreme_distortion`**: Confirms that extreme projection values are clamped correctly.
40. **`test_tier2_f3_homography_invalid_method`**: Ensures using an unsupported solver falls back to standard least-squares.

#### Feature 4: Trajectory Post-Processing & Interpolation
41. **`test_tier2_f4_postprocess_no_ball_in_dataset`**: Verifies that ball gap filtering is bypassed safely when ball data is absent.
42. **`test_tier2_f4_postprocess_linear_imputation_fallback`**: Confirms fallback to linear interpolation for ball gaps containing < 3 reference points.
43. **`test_tier2_f4_postprocess_excessive_ball_gap`**: Confirms ball gaps larger than `max_gap` are ignored (left blank).
44. **`test_tier2_f4_postprocess_reid_color_dissonance`**: Verifies that tracklets with mismatched color hues are rejected by the offline Re-ID stitcher.
45. **`test_tier2_f4_postprocess_reid_backwards_stitching`**: Confirms overlap check prevents backwards merging of tracklets in time.

#### Feature 5: Tactical & Possession Analytics
46. **`test_tier2_f5_possession_no_ball_detected`**: Checks possession defaults to neutral when ball detections are missing.
47. **`test_tier2_f5_possession_empty_dataframe`**: Confirms empty trajectory dataframes generate clean empty possession summary logs.
48. **`test_tier2_f5_analytics_collinear_hull_fail`**: Checks that collinear player layouts result in a compactness area of 0.0 without errors.
49. **`test_tier2_f5_analytics_no_defenders`**: Confirms that having 0 defenders returns all passing lanes as clear/open.
50. **`test_tier2_f5_highlights_missing_video`**: Ensures that highlight video clip extraction skips processing safely if the source video file does not exist.

---

### Tier 3: Cross-Feature Combinations (N = 5)

51. **`test_tier3_tracker_split_reid_stitching`**: Duel triggers a tracker split -> Post-processing Re-ID stitcher merges them post-duel. Checks that player identity is unified across duels.
52. **`test_tier3_homography_ballistic_interpolation`**: Projects pixel coordinates -> Ballistic curve-fitting runs on the metric coordinates -> Output clamps to pitch limits. Verifies coordinate pipeline continuity.
53. **`test_tier3_hue_clustering_reid_color_matching`**: DBSCAN colors -> Tracker maps tracks to team IDs -> Re-ID stitcher uses team ID and median Hue to resolve fragmented identities without shifting team labels.
54. **`test_tier3_stride_and_fps_scaling`**: Processes custom strides (e.g. `--stride 60`) and checks that downstream analytics adjust calculations to the effective frame rate.
55. **`test_tier3_detector_fallback_to_homography_mapping`**: Verifies coordinate pipeline continuity when the detector operates in simulated fallback.

---

### Tier 4: Real-World Scenarios (N = 5)

56. **`test_tier4_f5_full_headless_pipeline`**: Executes `main.py` and `run_tactical_analysis.py` sequentially via subprocess.
57. **`test_tier4_f5_headless_batch_execution`**: Exercises the `--batch` flag, verifying sequential outputs for multiple mock videos in inputs.
58. **`test_tier4_f5_missing_video_and_trajectory_robustness`**: Evaluates script behavior and exit codes when target paths are incorrect.
59. **`test_tier4_f5_uncontested_possession_match`**: Runs pipeline on empty frame video, checking that possession defaults to -1.
60. **`test_tier4_f5_extremely_fast_real_walkthrough`**: Executes E2E pipeline on tiny videos, validating Spanish column formats in `metricas_compactacion_es.csv`.

---

## 5. Execution Guide

Run all E2E test cases:
```powershell
pytest -v
```

Run specific tiers:
```powershell
pytest tests/test_tier1.py -v
pytest tests/test_tier2.py -v
pytest tests/test_tier3.py -v
pytest tests/test_tier4.py -v
```

Enable standard log prints:
```powershell
pytest -s -v
```
