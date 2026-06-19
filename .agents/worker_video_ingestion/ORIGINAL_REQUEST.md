## 2026-06-18T00:14:23Z
You are teamwork_preview_worker_video_ingestion.
Your working directory is c:\ReposGitHub\video_futbol_analisis\.agents\worker_video_ingestion\.
Your mission is to implement and unit test the high-performance CPU-based `DroneVideoIngestor` using the `decord` library.

Refer to the synthesized analysis and design at:
c:\ReposGitHub\video_futbol_analisis\.agents\sub_orch_video_ingestion\analysis.md
and Explorer reports:
- c:\ReposGitHub\video_futbol_analisis\.agents\explorer_video_ingestion_2\handoff.md
- c:\ReposGitHub\video_futbol_analisis\.agents\explorer_video_ingestion_3\handoff.md

Requirements:
1. Ensure the directories `src/ingestion/` are created.
2. Implement `DecordFrameArray` (subclass of `np.ndarray` that stores a strong reference to the backing decord NDArray to prevent memory garbage collection and access violation/segfaults).
3. Implement `DroneVideoIngestor` in `src/ingestion/video_reader.py` using `decord`.
   - The class must support zero-copy frame retrieval on CPU via ctypes pointer casting.
   - It must support slice-based batch generation and list/sequence based batch generation.
   - It must support single frame fetching by index (with bounds checking and negative index resolution).
4. Perform unit testing on the implementation. Write tests to `tests/test_video_reader.py` verifying:
   - Length of ingestor.
   - Single frame retrieval shape, type (np.ndarray), and zero-copy flag (`OWNDATA: False`).
   - Batch retrieval shape, type, and zero-copy flags for slices (e.g. `ingestor[0:5]`) and list of indices (e.g. `ingestor[[0, 2, 4]]`).
   - Bounds checking (raising `IndexError` for invalid indices).
   - Lifetime safety guard (fetching a frame, deleting the ingestor/frame references, forcing garbage collection via `gc.collect()`, and verifying that the array's data remains accessible and is not corrupted, without Python segfaulting).
5. Run the unit tests and document the results.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Write your handoff report to c:\ReposGitHub\video_futbol_analisis\.agents\worker_video_ingestion\handoff.md including:
- Detailed list of changes made.
- Build and test commands run and their exact console outputs.
- Complete verification of the implementation.

When done, send a message to the sub-orchestrator parent (Conversation ID: d27bfb5b-c1db-4b91-9539-ce11ef8242b3).
