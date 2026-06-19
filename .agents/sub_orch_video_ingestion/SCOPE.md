# Scope: Milestone 3 - Video Ingestion

## Architecture
The Video Ingestion Module provides high-performance video frame loading using the `decord` library on CPU. It bypasses standard OpenCV CPU decoding bottlenecks on 4K drone footage.

## Milestones
| # | Name | Scope | Dependencies | Status | Conv ID |
|---|------|-------|-------------|--------|---------|
| 1 | Implementation & Verification | Implement `DroneVideoIngestor` in `src/ingestion/video_reader.py` with decord. | Exploration | PLANNED | TBD |

## Interface Contracts
### DroneVideoIngestor
- Class location: `src.ingestion.video_reader.DroneVideoIngestor`
- Public Methods:
  - `__init__(self, video_path: str)`: Initialize decord VideoReader.
  - `get_frame(self, index: int) -> np.ndarray`: Retrieve a single frame as a numpy array in RGB format (zero-copy if possible).
  - `get_batch(self, indices: list[int]) -> np.ndarray`: Retrieve multiple frames as a batch.
  - `__len__(self) -> int`: Total frame count.

## Code Layout
- `src/ingestion/video_reader.py`: Contains `DroneVideoIngestor`.
