# plan.md — E2E Testing Track Plan

## 1. Objectives
- Establish the comprehensive, requirement-driven E2E Testing Track.
- Ensure the codebase features are covered under 4 Tiers of testing.
- Verify that tests can run successfully or document baseline failures.
- Publish `TEST_READY.md` containing the E2E test suite information.

## 2. Steps
- **Step 1: Codebase & Feature Analysis**
  - Search codebase files, identify user features, and examine input/output behaviors of the main Entry Points (e.g. `scripts/run_phase1_step1.py`, etc.).
  - Identify features (N). Determine expected test counts.
- **Step 2: Test Infra & Design**
  - Define how tests will run (using pytest or a custom Python runner).
  - Draft `TEST_INFRA.md` in the project root containing the feature inventory, test design, boundary conditions, combinations, and application workloads.
- **Step 3: Implement Test Suite**
  - Setup a tests directory (`tests/`) if it doesn't exist.
  - Implement E2E tests (`tests/test_e2e.py` or similar).
  - Tests must be opaque-box (running CLI commands/scripts in a subprocess and verifying outputs, exit codes, side effects).
- **Step 4: Verify and Audit**
  - Run the test suite using a worker.
  - Spawn reviewer and auditor to verify authenticity and robustness.
  - If tests fail, iterate on fixing code or refining tests (if tests themselves were wrong or if they expose real bugs).
- **Step 5: Publish & Handoff**
  - Write and publish `TEST_READY.md` at the project root.
  - Update BRIEFING.md and progress.md.
  - Send message to parent (Project Orchestrator).
