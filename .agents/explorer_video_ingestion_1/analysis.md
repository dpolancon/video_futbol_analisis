# Drone Video Ingestion Exploration (Milestone 3)

## Executive Summary
This report analyzes the requirements, API characteristics, memory behaviors, and implementation strategies for the `DroneVideoIngestor` class using the `decord` library. Through empirical local tests on the 4K video assets, we have investigated zero-copy CPU retrieval, slice-based batching, and index mapping. We present a detailed class structure and implementation plan that integrates cleanly with the project architecture.

---

## 1. Implementing `DroneVideoIngestor` with `decord`

`decord` is a high-performance Python library wrapping FFmpeg for fast video decoding. It is particularly suited for high-resolution drone footage because it avoids the standard frame-by-frame decoding bottlenecks of OpenCV.

### Key API Discoveries
- **Initialization**: `decord.VideoReader(video_path, ctx=decord.cpu(0))` initializes a reader on the CPU. It parses the video container and indexes frame positions.
- **Metadata**: Calling `len(vr)` yields the total number of frames in the video, and `vr.get_avg_fps()` provides the frame rate.
- **Decoder Downsampling**: The constructor allows optional `width` and `height` parameters:
  ```python
  decord.VideoReader(video_path, ctx=decord.cpu(0), width=1920, height=1080)
  ```
  This is a critical optimization parameter because it performs fast hardware/FFmpeg-level resizing during decoding, reducing CPU payload for 4K video processing downstream. We will expose optional `width`, `height`, and `num_threads` in the constructor.

---

## 2. Zero-Copy vs. Minimal-Copy Frame Retrieval on CPU

A core requirement is to achieve zero-copy (or minimal-copy) frame retrieval on the CPU. We conducted tests to probe if the decoded frame buffers can share memory with NumPy arrays:

### Empirical Test Findings
1. **Memory Ownership (`asnumpy()` and `np.asarray()`)**:
   - Calling `frame.asnumpy()` on a `decord.ndarray.NDArray` returns a NumPy array with the `OWNDATA` flag set to `True` and the `.base` reference set to `None`.
   - Calling `numpy.asarray(frame)` also returns a NumPy array with `OWNDATA: True` and `.base: None`.
   - **Conclusion**: Both methods copy the decoded frame buffer from decord's internal C++ memory space into a new NumPy-managed buffer.

2. **DLPack Interface Compatibility**:
   - Calling `frame.to_dlpack()` returns a standard PyCapsule.
   - Attempting `numpy.from_dlpack(frame)` or `numpy.from_dlpack(frame.to_dlpack())` raises an error:
     ```
     AttributeError: 'NDArray' object has no attribute '__dlpack__'
     AttributeError: 'PyCapsule' object has no attribute '__dlpack__'
     ```
   - **Conclusion**: Decord's `NDArray` does not implement the modern Python buffer protocol or standard DLPack `__dlpack__` attribute expected by NumPy 2.x for zero-copy sharing on CPU.

3. **Optimal Retrieval Strategy**:
   - Although true zero-copy is not possible due to library boundaries, `decord`'s `.asnumpy()` method is written in C++ and performs a direct, block-aligned memory copy. This is extremely fast and represents the **minimal-copy** approach on CPU.
   - Using `asnumpy()` is the standard, safest, and most performant way to ingest frames into NumPy.

---

## 3. Slice-Based Batch Generation

Our experiments verified how `decord` handles sliced frame retrieval:

### Decord Behavior on Slices and Index Lists
- **Native Slice Support**: Accessing frames with a slice object, e.g., `vr[0:2]`, is natively supported by `decord.VideoReader` and returns a `decord.ndarray.NDArray` of shape `(N, H, W, C)`.
- **List of Indices Failure**: Accessing frames via a list, e.g., `vr[[0, 2]]`, raises `TypeError: '<' not supported between instances of 'list' and 'int'`.
- **`get_batch` API**: `decord.VideoReader.get_batch(indices)` accepts a list of integers and returns a `decord.ndarray.NDArray` of shape `(N, H, W, C)`. It optimizes decoding by using internal seeking and sharing duplicate frames.
- **Negative and Out-of-Bounds Indices**:
  - `vr.get_batch([-1])` natively handles negative indices and returns the last frame.
  - `vr.get_batch([0, 9999999])` correctly raises `IndexError: Out of bound indices: [9999999]`.

### Implementation Strategy
To support slices, ranges, and lists of indices uniformly, the wrapper class will parse the index argument:
- If a `slice` is provided, we compute the indices using `list(range(*index.indices(len(self))))` and call `get_batch`.
- If a `range`, `list`, or `tuple` is provided, we convert it to a `list` and call `get_batch`.
- If an `int` is provided, we call `get_frame`.

---

## 4. Single Frame Fetching

Single frame fetching by index will be implemented via:
1. `get_frame(self, index: int) -> np.ndarray` (returns `(H, W, C)` array).
2. `__getitem__(self, index: int)` (delegates to `get_frame`).

We will implement explicit bounds checking and normalize negative indices in Python to raise meaningful python `IndexError` messages:
```python
total_frames = len(self)
if index < -total_frames or index >= total_frames:
    raise IndexError(f"Frame index {index} out of range for video with {total_frames} frames.")
if index < 0:
    index += total_frames
```

---

## 5. Implementation Plan & Signatures

### Class Location
The implementation will be located in `src/ingestion/video_reader.py`.

### Class Signatures

```python
import os
import numpy as np
import decord

class DroneVideoIngestor:
    def __init__(self, video_path: str, width: int = -1, height: int = -1, num_threads: int = 0):
        """
        Initializes the DroneVideoIngestor with a decord VideoReader.
        
        Args:
            video_path (str): Absolute or relative path to the video file.
            width (int, optional): Target width for hardware/decoder-level resizing. Defaults to -1 (original).
            height (int, optional): Target height for hardware/decoder-level resizing. Defaults to -1 (original).
            num_threads (int, optional): Number of CPU threads for decoding. Defaults to 0 (auto).
        """
        pass

    def get_frame(self, index: int) -> np.ndarray:
        """
        Retrieves a single frame by index as a NumPy array in RGB format.
        
        Args:
            index (int): Frame index. Supports negative indexing.
            
        Returns:
            np.ndarray: Image array of shape (H, W, 3) and type uint8.
            
        Raises:
            IndexError: If index is out of bounds.
        """
        pass

    def get_batch(self, indices: list[int]) -> np.ndarray:
        """
        Retrieves multiple frames by indices as a single batched NumPy array.
        
        Args:
            indices (list[int]): List of frame indices. Supports negative indexing.
            
        Returns:
            np.ndarray: Batched array of shape (N, H, W, 3) and type uint8.
            
        Raises:
            IndexError: If any index is out of bounds.
        """
        pass

    def __len__(self) -> int:
        """
        Returns the total number of frames in the video.
        """
        pass

    def __getitem__(self, index) -> np.ndarray:
        """
        Allows array-like slicing and indexing of the video.
        
        Args:
            index (int, slice, range, list, tuple): The index, slice, or collection of indices.
            
        Returns:
            np.ndarray: A single frame (H, W, 3) or a batch (N, H, W, 3).
        """
        pass

    @property
    def fps(self) -> float:
        """
        Returns the average frame rate (FPS) of the video.
        """
        pass
```

### Steps for implementation:
1. **Directory Setup**: Create directory `src/ingestion/` if it does not exist.
2. **Implementation**: Create `src/ingestion/video_reader.py` with the above class.
3. **Resizing Configuration**: Pass `width` and `height` parameters directly to `decord.VideoReader` to achieve fast decoder-level resizing.
4. **Unit Tests**: Place unit tests in `tests/ingestion/test_video_reader.py`. Test cases will verify:
   - Valid initialization and metadata reading (length, FPS).
   - Single frame fetching (shapes, bounds checks, negative indices).
   - Batch fetching via `get_batch`.
   - Slicing and range-based indexing via `__getitem__`.
   - Threading and resizing operations.
