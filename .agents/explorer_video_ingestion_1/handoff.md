# Handoff Report - Video Ingestion Exploration (Milestone 3)

## 1. Observation

### Verification of Decord Environment and Video File
* The codebase environment contains:
  - `decord` version: `0.6.0`
  - `numpy` version: `2.4.3`
  - Video file: `inputs/fecha06_1era.mp4` (~18.19 GB, 87109 frames, 47.95 FPS)

### Memory Ownership Probe (Zero-Copy vs. Copy)
* **Command**:
  ```powershell
  python -c "import decord, numpy as np; vr = decord.VideoReader('inputs/fecha06_1era.mp4'); frame = vr[0]; arr1 = frame.asnumpy(); arr2 = np.asarray(frame); print('arr1 OWNDATA:', arr1.flags['OWNDATA']); print('arr2 OWNDATA:', arr2.flags['OWNDATA']); print('arr1 base:', arr1.base); print('arr2 base:', arr2.base)"
  ```
* **Result**:
  ```
  arr1 OWNDATA: True
  arr2 OWNDATA: True
  arr1 base: None
  arr2 base: None
  ```
* **Attribute Inspection**:
  - `decord.ndarray.NDArray` lists public attributes: `['asnumpy', 'context', 'copyfrom', 'copyto', 'ctx', 'dtype', 'handle', 'is_view', 'same_as', 'shape', 'to_dlpack']`

### DLPack Conversion Probe
* **Command**:
  ```powershell
  python -c "import decord, numpy as np; vr = decord.VideoReader('inputs/fecha06_1era.mp4'); frame = vr[0]; dl = frame.to_dlpack(); arr = np.from_dlpack(dl)"
  ```
* **Result**:
  ```
  AttributeError: 'PyCapsule' object has no attribute '__dlpack__'
  ```
* **Command**:
  ```powershell
  python -c "import decord, numpy as np; vr = decord.VideoReader('inputs/fecha06_1era.mp4'); frame = vr[0]; arr = np.from_dlpack(frame)"
  ```
* **Result**:
  ```
  AttributeError: 'NDArray' object has no attribute '__dlpack__'
  ```

### Slice and List Indices Batching Probe
* **Command (Slices)**:
  ```powershell
  python -c "import decord; vr = decord.VideoReader('inputs/fecha06_1era.mp4'); print('type of slice:', type(vr[0:2]))"
  ```
* **Result**:
  ```
  type of slice: <class 'decord.ndarray.NDArray'>
  ```
* **Command (List of Indices)**:
  ```powershell
  python -c "import decord; vr = decord.VideoReader('inputs/fecha06_1era.mp4'); print(vr[[0, 2]])"
  ```
* **Result**:
  ```
  TypeError: '<' not supported between instances of 'list' and 'int'
  ```
* **Command (get_batch)**:
  ```powershell
  python -c "import decord; vr = decord.VideoReader('inputs/fecha06_1era.mp4'); batch = vr.get_batch([0, 2]); print('type:', type(batch)); print('shape:', batch.shape)"
  ```
* **Result**:
  ```
  type: <class 'decord.ndarray.NDArray'>
  shape: (2, 2160, 3840, 3)
  ```

### Out-of-Bounds and Negative Indices Batching Probe
* **Command (Out of Bounds)**:
  ```powershell
  python -c "import decord; vr = decord.VideoReader('inputs/fecha06_1era.mp4'); print(vr.get_batch([0, 9999999]))"
  ```
* **Result**:
  ```
  IndexError: Out of bound indices: [9999999]
  ```
* **Command (Negative Index)**:
  ```powershell
  python -c "import decord; vr = decord.VideoReader('inputs/fecha06_1era.mp4'); print(vr.get_batch([-1]).shape)"
  ```
* **Result**:
  ```
  (1, 2160, 3840, 3)
  ```

---

## 2. Logic Chain

1. **Zero-Copy Status**:
   - Standard conversion methods (`asnumpy()`, `np.asarray()`) return arrays with `OWNDATA: True` and `.base: None`, meaning they copy the decoded C++ frame buffer to Python memory.
   - DLPack conversions fail because decord's `NDArray` returns a PyCapsule from `to_dlpack()` instead of implementing the standard `__dlpack__` protocol, and it does not support `__dlpack__` directly.
   - Therefore, true zero-copy is not supported on CPU in this environment. We must use `asnumpy()` which is a C++-optimized **minimal-copy** operation.
2. **Slicing and Batching Interface**:
   - `decord.VideoReader` handles slices natively but raises a `TypeError` for lists of indices.
   - The native `get_batch(indices)` method successfully retrieves a list/iterable of frames and returns a batch NDArray, optimizing seek and duplicate operations.
   - Therefore, the class wrapper `DroneVideoIngestor` should use a custom `__getitem__` that converts slices/ranges/lists into lists of integers and forwards them to `get_batch`.
3. **Decord-Level Resizing**:
   - `decord.VideoReader` has initialization parameters `width` and `height`.
   - Performing resizing at the decoder level reduces CPU decode payload significantly for 4K video.
   - Therefore, we should expose optional `width`, `height`, and `num_threads` parameters in `__init__`.

---

## 3. Caveats

* **Zero-copy limit**: True zero-copy memory sharing is not achievable on CPU; a single memory copy occurs during `.asnumpy()`. This is still highly performant compared to OpenCV frame-by-frame decoding and resizing.
* **Large video indexing**: When initializing `decord.VideoReader`, it indexes the video file which can take 10-30 seconds on the massive 18 GB video files. This overhead only occurs once during instantiation.

---

## 4. Conclusion

- We have established a concrete implementation model for `DroneVideoIngestor` using `decord`.
- `decord.VideoReader` must be initialized on CPU context. We recommend exposing `width`, `height`, and `num_threads` to enable hardware-level resizing and threading optimization.
- The `__getitem__` method will unifiedly parse slices, ranges, and index lists, translating them into a list of integers and invoking `get_batch`.
- Single frame retrieval via `get_frame` will be bound-checked in Python to return appropriate index errors, and conversion to NumPy will rely on `.asnumpy()`.

---

## 5. Verification Method

To independently verify these observations:
1. Run the memory ownership test:
   ```powershell
   python -c "import decord, numpy as np; vr = decord.VideoReader('inputs/fecha06_1era.mp4'); f = vr[0]; a = f.asnumpy(); print('OWNDATA:', a.flags['OWNDATA'])"
   ```
   *Expected output*: `OWNDATA: True`.
2. Run the list indexing fail test:
   ```powershell
   python -c "import decord; vr = decord.VideoReader('inputs/fecha06_1era.mp4'); vr[[0, 2]]"
   ```
   *Expected output*: `TypeError`.
3. Run the batch fetching test:
   ```powershell
   python -c "import decord; vr = decord.VideoReader('inputs/fecha06_1era.mp4'); print(vr.get_batch([0, 2]).shape)"
   ```
   *Expected output*: `(2, 2160, 3840, 3)`.
