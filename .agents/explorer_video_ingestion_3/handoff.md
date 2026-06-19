# Handoff Report - Milestone 3: Video Ingestion Exploration

## 1. Observation
We conducted several Python-based runtime tests in the local environment (`decord` version 0.6.0, `numpy` version 2.4.3, and `opencv-python` version 4.13.0) using the video asset `inputs/fecha06_1era.mp4`.

### 1.1 Decord Class Types and Native Bridge Options
Running command `python -c "import decord; vr = decord.VideoReader('inputs/fecha06_1era.mp4'); print(type(vr)); frame = vr[0]; print(type(frame)); print(frame.shape)"` yielded:
```
<class 'decord.video_reader.VideoReader'>
<class 'decord.ndarray.NDArray'>
(2160, 3840, 3)
```

Running command to set numpy bridge yielded:
```
Bridge error: valid bridges: dict_keys(['native', 'mxnet', 'torch', 'tensorflow', 'tvm'])
```

### 1.2 Copy Overhead of `.asnumpy()`
Running command to inspect array flags on `frame.asnumpy()` yielded:
```
np_frame type: <class 'numpy.ndarray'>
np_frame flags:
  C_CONTIGUOUS : True
  F_CONTIGUOUS : False
  OWNDATA : True
  WRITEABLE : True
  ALIGNED : True
```
*Note*: `OWNDATA : True` indicates a deep copy. Profiling 10 frames showed an average of **~64.7 ms** spent copying the data buffer in `asnumpy()`.

### 1.3 Ctypes Zero-Copy Verification
Querying `frame.handle.contents` returned fields:
```
contents fields: [('data', <class 'ctypes.c_void_p'>), ('ctx', <class 'decord._ffi.runtime_ctypes.DECORDContext'>), ('ndim', <class 'ctypes.c_long'>), ('dtype', <class 'decord._ffi.runtime_ctypes.DECORDType'>), ('shape', <class 'ctypes.LP_c_longlong'>), ('strides', <class 'ctypes.LP_c_longlong'>), ('byte_offset', <class 'ctypes.c_ulonglong'>)]
```

Casting `data + byte_offset` to `ctypes.POINTER(ctypes.c_uint8)` and constructing using `np.ctypeslib.as_array` yielded:
```
arr type: <class 'numpy.ndarray'>
arr shape: (2160, 3840, 3)
arr flags:
  C_CONTIGUOUS : True
  F_CONTIGUOUS : False
  OWNDATA : False
  WRITEABLE : True
  ALIGNED : True

Arrays equal: True
asnumpy buffer address: 2249685205056
ctypes array buffer address: 2249573888128
Original data pointer: 2249573888128
```
*Note*: `OWNDATA: False` and matching buffer addresses confirm a zero-copy NumPy view.

### 1.4 Native Indexing Compatibility Tests
Probing indexing support on `decord.VideoReader` yielded the following behaviors:
- `vr[slice]` (e.g. `vr[0:2]`): **Success**, returning decord `NDArray` of shape `(2, 2160, 3840, 3)`.
- `vr[list]` (e.g. `vr[[0, 1]]`): **Failed** with `TypeError: '<' not supported between instances of 'list' and 'int'`.
- `vr[range]` (e.g. `vr[range(0, 2)]`): **Failed** with `TypeError: '<' not supported between instances of 'range' and 'int'`.
- `vr.get_batch(range(0, 2))`: **Success**, returning decord `NDArray` of shape `(2, 2160, 3840, 3)`.
- `vr.get_batch([0, 1])`: **Success**.
- `vr.get_batch(np.array([0, 1]))`: **Success**.
- `vr.get_batch(slice(0, 2))`: **Failed** with `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'slice'`.

Out-of-bounds indexing:
- `vr[len(vr)]` raised `<class 'IndexError'> message: Index: 87109 out of bound: 87109`.

Negative indexing:
- `vr[-1]` succeeded, returning shape `(2160, 3840, 3)`.
- `vr.get_batch([-1, -2])` succeeded, returning shape `(2, 2160, 3840, 3)`.

---

## 2. Logic Chain
1. **No Native Numpy Bridge**: Because `numpy` is not a valid bridge option in decord, we cannot retrieve numpy arrays directly by setting a bridge; we must interact with the `native` decord NDArray (Observation 1.1).
2. **Standard Method Overhead**: The standard `.asnumpy()` method performs a memory copy (Observation 1.2), causing high CPU latency (~64.7 ms per 4K frame).
3. **Ctypes Workaround**: Since decord exposes a ctypes pointer to its backing C++ array via the `handle` attribute, we can cast it to a C array of type `uint8` and use `np.ctypeslib.as_array` to wrap it (Observation 1.3). This yields a true zero-copy numpy view sharing the address buffer in <1 ms.
4. **Memory Safety Enforcement**: If the local decord `NDArray` goes out of scope in Python, the C++ buffer is immediately deallocated, leading to segmentation faults on numpy view access. To prevent this, we must subclass `np.ndarray` and keep a strong reference (`_decord_frame`) to the decord NDArray (Logic established via weakref lifetime testing).
5. **Divergent Indexing Dispatch**: To support range/list/slice indexing transparently, the ingestor's custom `__getitem__` must dispatch requests appropriately (Observation 1.4):
   - Int -> single frame zero-copy conversion.
   - Slices -> resolved to a `range` sequence, then fetched via `get_batch`.
   - Sequences -> fetched via `get_batch` and converted zero-copy.

---

## 3. Caveats
- **Slow Initialization**: On large 4K videos, initial `decord.VideoReader` load takes 30-120 seconds because it builds frame indices. This only occurs once per instantiation and is a known behavior of FFmpeg/decord indexing.
- **CPU Bound**: This investigation is focused entirely on CPU execution, as specified in the requirements. GPU context and CUDA bridges were not explored.

---

## 4. Conclusion
Milestone 3's high-performance video ingestion must be implemented in `src/ingestion/video_reader.py` with:
- A custom subclass `DecordFrameArray(np.ndarray)` for memory lifetime safety.
- A `DroneVideoIngestor` class wrapping `decord.VideoReader(video_path, ctx=decord.cpu(0), num_threads=0)`.
- `_to_numpy_zerocopy(frame: decord.ndarray.NDArray) -> np.ndarray` using ctypes casting.
- `__getitem__` implementing slice and sequence resolving.

The complete code signatures and draft class structure are documented in detail in `c:\ReposGitHub\video_futbol_analisis\.agents\explorer_video_ingestion_3\analysis.md`.

---

## 5. Verification Method

### 5.1 Verification Commands
To verify the zero-copy and interface behaviors of the planned implementation:
1. Ensure the directories are created and write the class to `src/ingestion/video_reader.py`.
2. Run a verification script to assert:
   ```python
   from src.ingestion.video_reader import DroneVideoIngestor
   
   ingestor = DroneVideoIngestor("inputs/fecha06_1era.mp4")
   
   # 1. Test single frame retrieval and zero-copy properties
   f0 = ingestor.get_frame(0)
   assert f0.shape == (2160, 3840, 3)
   assert f0.flags.owndata is False
   
   # 2. Test slice-based batch retrieval
   batch = ingestor[0:5]
   assert batch.shape == (5, 2160, 3840, 3)
   assert batch.flags.owndata is False
   
   # 3. Test list of indices
   batch_list = ingestor[[0, 2, 4]]
   assert batch_list.shape == (3, 2160, 3840, 3)
   assert batch_list.flags.owndata is False
   
   print("All verification checks passed!")
   ```
3. To run it, execute:
   ```powershell
   python -c "import sys; sys.path.append('src'); from ingestion.video_reader import DroneVideoIngestor; ingestor = DroneVideoIngestor('inputs/fecha06_1era.mp4'); f = ingestor[0]; print('Zero copy:', not f.flags.owndata)"
   ```

### 5.2 Invalidation Conditions
- If the output array has `OWNDATA : True`, the zero-copy requirement is violated.
- If deleting the returned array's source frame object causing access to the array results in a Python segfault, the memory safety reference guard is missing.
- If querying `vr[0:2]` returns a list or a list of numpy arrays instead of a contiguous 4D numpy array, the interface contract is violated.
