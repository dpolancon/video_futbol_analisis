import os
import gc
import sys
import pytest
import numpy as np
import decord
import weakref
import threading
import time
from typing import List
from src.ingestion.video_reader import DroneVideoIngestor, DecordFrameArray

def test_adversarial_invalid_index_types(mock_video_factory):
    """Test accessing with invalid types raises TypeError."""
    video_path = mock_video_factory(name="test_adv_types.mp4", num_frames=5)
    ingestor = DroneVideoIngestor(video_path)

    # Float index
    with pytest.raises(TypeError):
        _ = ingestor[1.5]

    # String index
    with pytest.raises(TypeError):
        _ = ingestor["first"]

    # None index
    with pytest.raises(TypeError):
        _ = ingestor[None]

    # Sequence containing invalid types
    with pytest.raises(TypeError):
        _ = ingestor[[0, "1", 2]]

    with pytest.raises(TypeError):
        _ = ingestor[[0, None, 2]]


def test_adversarial_out_of_bounds_extremes(mock_video_factory):
    """Test index bounds checking with extreme numbers."""
    video_path = mock_video_factory(name="test_adv_extremes.mp4", num_frames=5)
    ingestor = DroneVideoIngestor(video_path)

    # Positive extreme
    with pytest.raises(IndexError):
        _ = ingestor[999999]

    # Negative extreme
    with pytest.raises(IndexError):
        _ = ingestor[-999999]

    # Sequence with out of bounds element
    with pytest.raises(IndexError):
        _ = ingestor[[0, 1, 999999]]


def test_adversarial_slice_resolving(mock_video_factory):
    """Test slice indexing behavior with out-of-bounds start/stop and negative step sizes."""
    video_path = mock_video_factory(name="test_adv_slices.mp4", num_frames=10, width=640, height=360)
    ingestor = DroneVideoIngestor(video_path)

    # Slice start out of bounds
    batch1 = ingestor[100:105]
    assert len(batch1) == 0

    # Slice stop out of bounds (should clamp to max length)
    batch2 = ingestor[5:100]
    assert len(batch2) == 5
    assert batch2.shape == (5, 360, 640, 3)

    # Slice negative step size (should return empty or step backwards)
    # Note: ingestor slice is resolved via:
    # start, stop, step = index.indices(self._len)
    # range(start, stop, step)
    # If step is negative, e.g. ingestor[::-1]:
    # index.indices(10) -> (9, -1, -1)
    # which resolves to list of indices [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
    batch_rev = ingestor[::-1]
    assert len(batch_rev) == 10
    assert batch_rev.shape == (10, 360, 640, 3)

    # Negative slice bounds
    batch_neg = ingestor[-5:-1]
    assert len(batch_neg) == 4


def test_zero_copy_pointer_equality(mock_video_factory):
    """Verify that the NumPy array points to the exact memory address of the decord NDArray."""
    video_path = mock_video_factory(name="test_adv_zerocopy.mp4", num_frames=5)
    ingestor = DroneVideoIngestor(video_path)

    # Get single frame
    frame = ingestor[0]
    
    # Get decord NDArray from frame metadata
    decord_frame = frame._decord_frame
    
    # Compute decord memory address
    handle = decord_frame.handle
    data_ptr = handle.contents.data
    byte_offset = getattr(handle.contents, 'byte_offset', 0)
    expected_addr = data_ptr + byte_offset

    # Get numpy memory address
    np_addr = frame.__array_interface__['data'][0]
    
    assert np_addr == expected_addr, f"NumPy address {np_addr} does not match decord address {expected_addr}"
    assert frame.base is not None or frame.flags.owndata is False


def test_decord_frame_array_finalization(mock_video_factory):
    """Verify DecordFrameArray finalization properly references decord's frame objects under slicing/viewing."""
    video_path = mock_video_factory(name="test_adv_finalize.mp4", num_frames=5)
    ingestor = DroneVideoIngestor(video_path)

    frame = ingestor[0]
    assert hasattr(frame, '_decord_frame')
    assert isinstance(frame._decord_frame, decord.ndarray.NDArray)

    # 1. Slice of a frame
    slice_of_frame = frame[10:20, 10:20, :]
    assert isinstance(slice_of_frame, DecordFrameArray)
    assert hasattr(slice_of_frame, '_decord_frame')
    assert slice_of_frame._decord_frame is frame._decord_frame

    # 2. View of a frame
    view_of_frame = frame.view(DecordFrameArray)
    assert isinstance(view_of_frame, DecordFrameArray)
    assert hasattr(view_of_frame, '_decord_frame')
    assert view_of_frame._decord_frame is frame._decord_frame

    # 3. Batch array finalization
    batch = ingestor[[0, 1, 2]]
    assert isinstance(batch, DecordFrameArray)
    assert hasattr(batch, '_decord_frame')
    
    # 4. Element from a batch
    element_from_batch = batch[1]
    assert isinstance(element_from_batch, DecordFrameArray)
    assert hasattr(element_from_batch, '_decord_frame')
    assert element_from_batch._decord_frame is batch._decord_frame


def test_lifetime_weakref_safety(mock_video_factory):
    """Verify that decord's NDArray is kept alive as long as any DecordFrameArray references it."""
    video_path = mock_video_factory(name="test_adv_lifetime.mp4", num_frames=5)
    ingestor = DroneVideoIngestor(video_path)

    frame = ingestor[0]
    decord_frame = frame._decord_frame
    
    # Track the decord frame lifetime with weakref
    try:
        ref = weakref.ref(decord_frame)
    except TypeError:
        # If decord's NDArray doesn't support weakref directly, we can check it
        # via tracking the refcount or checking that the reference is held.
        # In python, some C extensions don't support weak references.
        # Let's assert we can check reference counts instead.
        ref = None

    if ref is not None:
        # Delete ingestor and decord_frame local variable, only 'frame' holds the reference now
        del ingestor
        del decord_frame
        gc.collect()
        
        # Reference should still be alive
        assert ref() is not None
        
        # Slice it and delete original frame
        sub_frame = frame[5:15, 5:15]
        del frame
        gc.collect()
        
        # Reference should still be alive because sub_frame has _decord_frame
        assert ref() is not None
        
        # Delete subframe
        del sub_frame
        gc.collect()
        
        # Now reference must be dead
        assert ref() is None
    else:
        # Refcount check fallback if weakref is not supported
        # Get starting refcount
        ref_count_before = sys.getrefcount(decord_frame)
        
        # Add another reference (slice)
        sub_frame = frame[5:15, 5:15]
        ref_count_after = sys.getrefcount(decord_frame)
        
        # Since both frame and sub_frame reference the decord_frame, refcount should remain stable/increase
        assert ref_count_after >= ref_count_before
        
        # Delete slice
        del sub_frame
        gc.collect()
        
        # Refcount should decrease back
        assert sys.getrefcount(decord_frame) < ref_count_after


def test_concurrent_access_safety(mock_video_factory):
    """Verify DroneVideoIngestor handles concurrent requests in a multi-threaded context."""
    video_path = mock_video_factory(name="test_adv_concurrent.mp4", num_frames=10, width=640, height=360)
    ingestor = DroneVideoIngestor(video_path)

    num_threads = 8
    num_iterations = 20
    errors = []

    def worker(thread_idx):
        try:
            for _ in range(num_iterations):
                # Access random frame
                idx = (thread_idx + _) % 10
                frame = ingestor[idx]
                assert frame.shape == (360, 640, 3)
                assert frame.dtype == np.uint8
                
                # Access batch
                batch = ingestor[[0, idx, 9]]
                assert batch.shape == (3, 360, 640, 3)
        except Exception as e:
            errors.append(e)

    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert len(errors) == 0, f"Encountered concurrent access errors: {errors}"


def test_performance_zero_copy(mock_video_factory):
    """Measure and compare time to load frames with zero-copy vs copying (asnumpy())."""
    video_path = mock_video_factory(name="test_adv_perf.mp4", num_frames=20, width=1920, height=1080)
    ingestor = DroneVideoIngestor(video_path)

    # Warmup
    _ = ingestor[0]

    # Measure zero-copy retrieval
    start_zc = time.perf_counter()
    for i in range(20):
        frame = ingestor[i]
        _ = frame[0, 0, 0] # access memory to ensure it is valid
    end_zc = time.perf_counter()
    time_zc = end_zc - start_zc

    # Measure asnumpy() retrieval (copying)
    start_copy = time.perf_counter()
    for i in range(20):
        # We simulate what normal decord does when converting to numpy with copy
        decord_frame = ingestor._vr[i]
        np_copy = decord_frame.asnumpy()
        _ = np_copy[0, 0, 0]
    end_copy = time.perf_counter()
    time_copy = end_copy - start_copy

    print(f"\n[Performance Benchmark] Zero-copy retrieval: {time_zc:.6f}s")
    print(f"[Performance Benchmark] Copying (.asnumpy()) retrieval: {time_copy:.6f}s")
    # Verify that zero-copy is fast (usually it should be significantly faster,
    # but in a small mock video the overhead might vary; we print the results).
