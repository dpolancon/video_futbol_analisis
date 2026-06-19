# plan.md — E2E Testing Track Plan (Gen 2)

## 1. Objectives
- Resume and complete E2E Testing Track verification.
- Verify E2E test suite correctness and integrity by running new validation agents (Reviewer, Challenger, Auditor).
- Ensure TEST_INFRA.md and TEST_READY.md are accurate and complete.
- Report status and handoff to the parent Project Orchestrator.

## 2. Steps
- **Step 1: Recovery and Initialization**
  - Read predecessor state from `sub_orch_e2e_testing`.
  - Initialize BRIEFING.md, progress.md, and plan.md in gen2 workspace.
  - Setup heartbeat cron.
- **Step 2: Verification Loop**
  - Spawn `teamwork_preview_reviewer` to review the E2E tests, verifying that they map to requirements and avoid regression/deprecation.
  - Spawn `teamwork_preview_challenger` to conduct adversarial checking, testing edge behaviors, boundary conditions, and verifying 60/60 tests run properly.
  - Spawn `teamwork_preview_auditor` to audit the code and tests, checking for facades or hardcoded values.
- **Step 3: Document Verification & Finalize**
  - Read TEST_INFRA.md and TEST_READY.md and confirm they match the actual code and test files in `tests/`.
  - Compile the synthesis report.
- **Step 4: Report to Parent**
  - Report status to the parent orchestrator via send_message.
