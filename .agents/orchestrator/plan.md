# Plan

## Step 1: Initial Exploration
- Spawn `teamwork_preview_explorer` to analyze the workspace, existing files, python environment, and installed libraries (specifically `decord` and `opencv`).
- Deliverable: Exploration report and recommendations on design/implementation strategies.

## Step 2: Test Infrastructure Setup (E2E Track)
- Spawn an E2E Testing Orchestrator (or do it recursively/parallel) to design the E2E test plan (`TEST_INFRA.md`).
- Implement E2E test suite/cases to cover happy path, boundaries, and real-world inputs.
- Deliverable: `TEST_READY.md`.

## Step 3: Implement Core Modules (Implementation Track)
- Milestone 1: High-Performance Video Ingestion (using `decord`).
- Milestone 2: Pitch Calibration (Homography Mapping).
- Milestone 3: Execution and Automated Verification.
- Each milestone runs: Worker -> Reviewer -> Challenger -> Auditor -> Gate.

## Step 4: Final Acceptance and Adversarial Hardening
- Run E2E test suite.
- Run Challenger-led adversarial hardening.
- Perform final audit.
