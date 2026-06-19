# Handoff Report: Forensic Audit of Video Ingestion (Milestone 3)

## 1. Observation

### Source Code Details
In `c:\ReposGitHub\video_futbol_analisis\src\ingestion\video_reader.py`, the `DroneVideoIngestor` class retrieves frames dynamically using the `decord` library and converts them using a low-level `ctypes` mapping.

Lines 48–69 of `src/ingestion/video_reader.py`:
```python
    def _to_numpy_zerocopy(self, decord_frame: decord.ndarray.NDArray) -> np.ndarray:
        """
        Convert a decord NDArray to a zero-copy NumPy array via ctypes pointer casting.
        """
        shape = decord_frame.shape
        size = 1
        for dim in shape:
            size *= dim

        handle = decord_frame.handle
        data_ptr = handle.contents.data
        byte_offset = getattr(handle.contents, 'byte_offset', 0)
        addr = data_ptr + byte_offset

        # Cast raw memory address to a ctypes array of c_uint8
        ctypes_type = ctypes.c_uint8 * size
        data_array_ptr = ctypes.cast(addr, ctypes.POINTER(ctypes_type))

        # Wrap in NumPy array (zero-copy) and reshape
        np_arr = np.ctypeslib.as_array(data_array_ptr.contents)
        return np_arr.reshape(shape)
```

And lines 7–24 of `src/ingestion/video_reader.py`:
```python
class DecordFrameArray(np.ndarray):
    """
    Custom NumPy array subclass that holds a strong reference to a decord NDArray
    to ensure the underlying C++ buffer is not garbage collected.
    """
    def __new__(cls, input_array: np.ndarray, decord_frame: decord.ndarray.NDArray):
        # Cast input array to this subclass type
        obj = np.asarray(input_array).view(cls)
        # Hold a strong reference to the backing decord NDArray
        obj._decord_frame = decord_frame
        return obj

    def __array_finalize__(self, obj):
        if obj is None:
            return
        # Copy the reference to the backing decord NDArray when sliced/viewed
        self._decord_frame = getattr(obj, '_decord_frame', None)
```

### Test Case Verification
The tests in `c:\ReposGitHub\video_futbol_analisis\tests\test_video_reader.py` assert zero-copy properties explicitly:
```python
    frame = ingestor[0]
    assert isinstance(frame, np.ndarray)
    assert isinstance(frame, DecordFrameArray)
    assert frame.shape == (360, 640, 3)
    assert frame.dtype == np.uint8
    assert frame.flags.owndata is False
```

### Test Output Command & Results
Running the command `python -m pytest tests/test_video_reader.py` yielded:
```
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\ReposGitHub\video_futbol_analisis
configfile: pytest.ini
plugins: anyio-4.12.1
collected 6 items

tests/test_video_reader.py::test_video_reader_len PASSED                 [ 16%]
tests/test_video_reader.py::test_video_reader_single_frame PASSED        [ 33%]
tests/test_video_reader.py::test_video_reader_batch_slice PASSED         [ 50%]
tests/test_video_reader.py::test_video_reader_batch_list PASSED          [ 66%]
tests/test_video_reader.py::test_video_reader_bounds_checking PASSED     [ 83%]
tests/test_video_reader.py::test_video_reader_lifetime_safety PASSED     [100%]

============================== 6 passed in 3.31s ==============================
```

---

## 2. Logic Chain

1. **Instantiation and Decord Binding**: In `DroneVideoIngestor.__init__`, a `decord.VideoReader` is instantiated on the CPU. The length of the ingestor matches the video frame count retrieved directly from Decord (`self._len = len(self._vr)`).
2. **True Zero-Copy Verification**: The `_to_numpy_zerocopy` function casts the raw memory address of the backing Decord NDArray (obtained from `decord_frame.handle.contents.data`) to a ctypes POINTER to a ctypes array, wrapping it with `np.ctypeslib.as_array`. As a result, the returned NumPy array has its `owndata` flag set to `False`. The tests verify that `frame.flags.owndata is False`, proving that no data duplication takes place.
3. **Reference Count and GC Safety**: Because the NumPy array is a direct view of Decord's C++ buffer, freeing the Decord frame object while the NumPy array is still in scope would lead to a segmentation fault. The code resolves this by defining `DecordFrameArray`, a NumPy subclass that retains a strong Python reference to the backing `decord_frame` in its `_decord_frame` attribute. The `test_video_reader_lifetime_safety` test deletes the ingestor, forces garbage collection via `gc.collect()`, and verifies that the retrieved frame remains accessible and uncorrupted, confirming memory safety.
4. **No Bypass/Cheating**: Analysis of the source code confirms there are no hardcoded outputs, constant frames, or mocks designed to trick the test cases. All inputs are parsed dynamically through Decord.

---

## 3. Caveats

The wider test suite (`tests/test_tier1.py`, `tests/test_tier2.py`, etc.) fails during pytest collection because `RobustDroneTracker` cannot be imported from `core.tracker`. However, these errors are due to unimplemented features/modules outside the scope of **Milestone 3: Video Ingestion** (which is restricted to `video_reader.py` and its direct tests). No other caveats exist.

---

## 4. Conclusion

### Forensic Audit Report

**Work Product**: `c:\ReposGitHub\video_futbol_analisis\src\ingestion\video_reader.py`  
**Profile**: General Project  
**Verdict**: **CLEAN**

### Phase Results
- **Source Code Analysis**: PASS — Code dynamically parses frames using Decord. No hardcoded arrays, facade implementations, or bypasses are present.
- **Behavioral Verification**: PASS — Tests successfully run and pass.
- **Zero-Copy Performance**: PASS — Verified via array flags (`owndata = False`) and ctypes casting.
- **Memory Safety/GC**: PASS — Subclassed array correctly preserves decord references to prevent segfaults.

---

## 5. Verification Method

To independently run and verify the tests:
```powershell
python -m pytest tests/test_video_reader.py
```
Ensure that `decord`, `numpy`, and `pytest` are installed in your Python environment.
