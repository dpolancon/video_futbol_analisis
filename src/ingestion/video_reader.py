import ctypes
import os
import threading
from typing import Union, List, Sequence
import numpy as np
import decord

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

class DroneVideoIngestor:
    """
    High-performance CPU-based video frame ingestor using decord.
    Supports zero-copy frame retrieval on CPU via ctypes pointer casting.
    """
    def __init__(self, video_path: str):
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        # Initialize thread-safety lock
        self._lock = threading.Lock()
        
        # Initialize decord VideoReader on CPU
        self._vr = decord.VideoReader(video_path, ctx=decord.cpu(0), num_threads=0)
        self._len = len(self._vr)
        
        # Determine shape of frames
        if self._len > 0:
            first_frame = self._vr[0]
            self._frame_shape = first_frame.shape
        else:
            self._frame_shape = None


    def __len__(self) -> int:
        return self._len

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

    def get_frame(self, index: int) -> np.ndarray:
        """
        Retrieve a single frame as a numpy array in RGB format (zero-copy).
        """
        # Bounds checking
        if index < -self._len or index >= self._len:
            raise IndexError(f"Index {index} out of bounds for DroneVideoIngestor of length {self._len}")
        
        # Resolve negative index
        if index < 0:
            index += self._len
            
        with self._lock:
            decord_frame = self._vr[index]
        np_arr = self._to_numpy_zerocopy(decord_frame)
        return DecordFrameArray(np_arr, decord_frame)

    def get_batch(self, indices: Union[List[int], Sequence[int]]) -> np.ndarray:
        """
        Retrieve multiple frames as a batch.
        """
        if not isinstance(indices, (list, tuple, np.ndarray, range)):
            raise TypeError(f"Indices must be a sequence, got {type(indices)}")

        # Convert to a flat list for bounds checking and conversion
        indices_list = list(indices)
        
        # If indices list is empty, return an empty 4D array of correct dimensions
        if not indices_list:
            if self._frame_shape:
                return np.empty((0, *self._frame_shape), dtype=np.uint8)
            else:
                return np.empty((0, 0, 0, 3), dtype=np.uint8)

        # Bounds checking and negative index resolution
        resolved_indices = []
        for idx in indices_list:
            if idx < -self._len or idx >= self._len:
                raise IndexError(f"Index {idx} out of bounds for DroneVideoIngestor of length {self._len}")
            if idx < 0:
                idx += self._len
            resolved_indices.append(idx)

        # Fetch batch
        with self._lock:
            decord_batch = self._vr.get_batch(resolved_indices)
        np_arr = self._to_numpy_zerocopy(decord_batch)
        return DecordFrameArray(np_arr, decord_batch)


    def __getitem__(self, index: Union[int, slice, List[int], Sequence[int], np.ndarray]) -> np.ndarray:
        """
        Support indexing by integer, slice, or sequence of indices.
        """
        if isinstance(index, (int, np.integer)):
            return self.get_frame(int(index))
        elif isinstance(index, slice):
            # Resolve slice to list of indices
            start, stop, step = index.indices(self._len)
            indices = list(range(start, stop, step))
            return self.get_batch(indices)
        elif isinstance(index, (list, tuple, np.ndarray, range)):
            return self.get_batch(index)
        else:
            raise TypeError(f"Invalid index type: {type(index)}")
