# Handoff Report - Milestone 3: Video Ingestion Exploration

## 1. Observation
- **decord Installation**: Verified decord is installed and active in the Python environment (version 0.6.0).
- **`decord.VideoReader` properties**:
  - `VideoReader` contains `__getitem__`, `get_batch`, `__len__`, `get_avg_fps`.
  - Slice getitem native support: `slice: <class 'decord.ndarray.NDArray'>` (returned by `vr[0:3]`).
  - List getitem failure: `vr[[0, 2, 4]]` raises `TypeError: '<' not supported between instances of 'list' and 'int'` at `video_reader.py:100`.
- **Zero-Copy Attempts**:
  - bridge `numpy` configuration: `decord.bridge.set_bridge('numpy')` raises `AssertionError: valid bridges: dict_keys(['native', 'mxnet', 'torch', 'tensorflow', 'tvm'])`.
  - `from_dlpack` on `frame.to_dlpack()`: `np.from_dlpack(frame.to_dlpack())` raises `AttributeError: 'PyCapsule' object has no attribute '__dlpack__'`.
  - `asnumpy()` copy: `frame.asnumpy()` returns a numpy array with `OWNDATA : True`.
- **Ctypes Internal Structure**:
  - `decord_arr = frame.handle.contents` reveals `DECORDArray` struct fields: `data` (`ctypes.c_void_p`), `ctx` (`DECORDContext`), `ndim` (`ctypes.c_int`), `dtype` (`DECORDType`), `shape` (`POINTER(c_int64)`).
  - Data pointer location: `frame.handle.contents.data` points to the raw CPU address.
  - Zero-copy view using ctypes:
    ```python
    size = int(np.prod(shape))
    ctypes_type = ctypes.c_uint8 * size
    data_array_ptr = ctypes.cast(data_ptr, ctypes.POINTER(ctypes_type))
    np_arr = np.ctypeslib.as_array(data_array_ptr.contents).reshape(shape)
    ```
    This yields `OWNDATA : False`.
  - Garbage collection crash: Running `gc.collect()` on a local frame that has been converted to `np_arr` without references results in Windows Access Violation (Segfault, exit code `3221225477` / `0xC0000005`).
  - Reference Protection: Creating `DecordNumpyArray` subclass that stores `_decord_ref` prevents the Access Violation, resulting in exit code `0` and correct frame sum.
- **Performance Benchmark**:
  - Copy mode (`asnumpy()`): `0.288s` for 100 frames.
  - Zero-copy mode (ctypes): `0.000788s` for 100 frames.
  - Performance Speedup: **366.1x**.
- **Missing Directories**:
  - Root directory contains `analytics/`, `core/`, `wrappers/`, `tests/` but does not contain `src/` or `scripts/`.
- **Target File Contract**:
  - `PROJECT.md` specifies `DroneVideoIngestor` should be implemented in `src/ingestion/video_reader.py`.

---

## 2. Logic Chain
1. **Zero-Copy Necessity**: Slicing highlight clips and processing full-resolution 4K frames will be extremely CPU-bound. Standard `asnumpy()` frame retrieval is slow because it copies 24.8 MB of data per 4K frame.
2. **Buffer Lifetime Problem**: decord's C++ library owns the raw memory buffer. The python-side `decord.ndarray.NDArray` wrapper manages its lifecycle. When this python object is deleted, its C++ buffer is freed.
3. **Segfault Trigger**: If we create a zero-copy NumPy array pointing to the raw C++ buffer via `np.ctypeslib.as_array()`, the NumPy array does not increment the refcount of the `decord.ndarray.NDArray` wrapper. If the wrapper goes out of scope, it is garbage collected, the C++ buffer is freed, and any subsequent read/write to the NumPy array causes a Segmentation Fault.
4. **Resolution via Subclassing**: We subclass `np.ndarray` and store the `decord.ndarray.NDArray` object as a custom attribute (`_decord_ref`). Because Python's subclass instantiation retains a reference to this object, the parent wrapper is kept alive as long as the NumPy array (or any slice/view of it) exists. This completely resolves the lifetime and memory safety issue.
5. **Batch Ingestion Interface**: Because decord's `VideoReader` does not support lists of indices inside `__getitem__` (raising a `TypeError`), the ingestor must normalize slices, ranges, list of indices, and individual integers before passing them to the underlying reader methods (`get_frame` or `get_batch`).

---

## 3. Caveats
- **Decord Device Support**: This zero-copy implementation assumes the decord `VideoReader` is instantiated on the CPU (`decord.cpu(0)`). If GPU decoding is introduced in the future, the pointer cast will fail because `data_ptr` will point to GPU memory, and `np.ctypeslib.as_array` will cause a segfault or fail. For GPU support, the TVM/Torch bridge or GPU PyCapsules must be used instead.
- **Contiguous Buffer Assumption**: The ctypes mapping assumes CPU video frames returned by decord are always stored as contiguous `uint8` arrays in RGB format.

---

## 4. Conclusion
- Implementing zero-copy frame retrieval on CPU via ctypes pointer mapping provides a **366x speedup** over deep-copying (`asnumpy()`).
- Lifetime management of the C++ frame buffers is critical: a custom `np.ndarray` subclass `DecordNumpyArray` must be used to prevent garbage collection and subsequent segmentation faults.
- Slicing and list-indexing must be normalized in the ingestor's `__getitem__` method to prevent decord's internal `__getitem__` list TypeError.

---

## 5. Verification Method
1. **Unit Test for Lifetime Safety**:
   Verify that a frame retrieved from `DroneVideoIngestor` can survive manual garbage collection:
   ```python
   import gc
   ingestor = DroneVideoIngestor('inputs/fecha06_1era.mp4')
   frame = ingestor[0]
   # Force garbage collection
   gc.collect()
   # Access frame data - if unsafe, it will crash the Python process with exit code 0xC0000005
   _ = frame.sum()
   ```
2. **Unit Test for Shape and Types**:
   Verify indexing types return correct shapes:
   - `isinstance(ingestor[0], np.ndarray)` of shape `(2160, 3840, 3)`
   - `isinstance(ingestor[0:3], np.ndarray)` of shape `(3, 2160, 3840, 3)`
   - `isinstance(ingestor[[0, 2, 4]], np.ndarray)` of shape `(3, 2160, 3840, 3)`
3. **Performance Run**:
   Verify time taken to extract 100 frames is under `0.01` seconds using the ctypes-based zero-copy method.

---

## 6. Remaining Work
- Create the target folder `src/ingestion/` if it does not exist.
- Implement `DecordNumpyArray` and `DroneVideoIngestor` inside `src/ingestion/video_reader.py`.
- Write unit tests under a new file (e.g. `tests/test_video_reader.py`) to verify functionality, types, bounds checking, and lifetime safety.
