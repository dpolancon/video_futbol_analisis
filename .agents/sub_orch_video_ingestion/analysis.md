# Video Ingestion Synthesis Analysis

## Consensus
1. **Engine and Backend**: We will use the `decord` library on CPU to load 4K drone video footage.
2. **Buffer Lifetime Problem**: decord's C++ library owns the raw memory buffer. The python-side `decord.ndarray.NDArray` wrapper manages its lifecycle. When this python object is deleted, its C++ buffer is freed.
3. **Memory Safety Enforcement**: If we create a zero-copy NumPy array pointing to the raw C++ buffer, the NumPy array does not increment the refcount of the `decord.ndarray.NDArray` wrapper. If the wrapper goes out of scope, it is garbage collected, the C++ buffer is freed, and any subsequent access to the NumPy array causes a Segmentation Fault. We must subclass `np.ndarray` (e.g. `DecordFrameArray`) to store a strong reference to the decord frame object, ensuring the backing C++ buffer is kept alive as long as the NumPy array itself exists.
4. **Interface Contract Compatibility**: `decord.VideoReader`'s native slicing works for batches, but passing a list/range of indices fails with `TypeError`. Conversely, `get_batch` accepts lists/ranges of indices but fails on slices. The wrapper class `DroneVideoIngestor.__getitem__` must normalize slices, ranges, lists, and individual integers before passing them to the underlying reader methods.

## Resolved Conflicts
- **Zero-Copy Support**:
  - *Explorer 1* reported that true zero-copy is not supported on CPU because `asnumpy()` performs a copy and `from_dlpack` fails on PyCapsule.
  - *Explorer 2* and *Explorer 3* successfully verified that a true zero-copy NumPy view can be achieved in <1 ms on CPU by casting the backing C++ memory pointer in the `DECORDArray` handle via Python's `ctypes` library, and then converting it using `np.ctypeslib.as_array`.
  - *Resolution*: We adopt the ctypes-based zero-copy method as it satisfies the requirements and provides a **100x+ speedup** over `asnumpy()`.

## Code Layout and Target
- Target source file: `src/ingestion/video_reader.py`
- Target unit tests: `tests/test_video_reader.py` (Wait, does `tests/` directory exist? Yes, Explorer 2 mentioned it).

## Signatures & Implementation Detail

The worker will implement:

```python
import ctypes
import os
from typing import Union, List, Sequence
import numpy as np
import decord

class DecordFrameArray(np.ndarray):
    """
    Custom NumPy array subclass that holds a reference to a decord NDArray
    to ensure the underlying C++ buffer is not garbage collected.
    """
    def __new__(cls, input_array: np.ndarray, decord_frame: decord.ndarray.NDArray):
        obj = np.asarray(input_array).view(cls)
        obj._decord_frame = decord_frame
        return obj

    def __array_finalize__(self, obj):
        if obj is None:
            return
        self._decord_frame = getattr(obj, '_decord_frame', None)

class DroneVideoIngestor:
    def __init__(self, video_path: str):
        # Initialize decord VideoReader on CPU
        ...
```

The worker must also implement a test suite at `tests/test_video_reader.py` using unittest or pytest to verify:
1. Retrieval of single frames with zero-copy.
2. Batch retrieval via slice indexing.
3. Batch retrieval via list/sequence of indices.
4. Bounds checks and negative index resolution.
5. Lifetime safety checks (forcing garbage collection and accessing frame values).
