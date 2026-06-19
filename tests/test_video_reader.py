import os
import gc
import pytest
import numpy as np
from src.ingestion.video_reader import DroneVideoIngestor, DecordFrameArray

def test_video_reader_len(mock_video_factory):
    """Verify that the DroneVideoIngestor returns the correct total frame count."""
    video_path = mock_video_factory(name="test_len.mp4", num_frames=8)
    ingestor = DroneVideoIngestor(video_path)
    assert len(ingestor) == 8

def test_video_reader_single_frame(mock_video_factory):
    """Verify single frame retrieval shape, type, and zero-copy flag."""
    video_path = mock_video_factory(name="test_single.mp4", num_frames=5, width=640, height=360)
    ingestor = DroneVideoIngestor(video_path)
    
    frame = ingestor[0]
    assert isinstance(frame, np.ndarray)
    assert isinstance(frame, DecordFrameArray)
    assert frame.shape == (360, 640, 3)
    assert frame.dtype == np.uint8
    assert frame.flags.owndata is False
    
    # Negative indexing
    frame_neg = ingestor[-1]
    assert isinstance(frame_neg, DecordFrameArray)
    assert frame_neg.shape == (360, 640, 3)
    assert frame_neg.flags.owndata is False

def test_video_reader_batch_slice(mock_video_factory):
    """Verify batch retrieval shape, type, and zero-copy flags for slices."""
    video_path = mock_video_factory(name="test_slice.mp4", num_frames=10, width=640, height=360)
    ingestor = DroneVideoIngestor(video_path)
    
    # Slice e.g. ingestor[0:5]
    batch = ingestor[0:5]
    assert isinstance(batch, DecordFrameArray)
    assert batch.shape == (5, 360, 640, 3)
    assert batch.flags.owndata is False
    
    # Slice with step
    batch_step = ingestor[1:8:2]
    assert isinstance(batch_step, DecordFrameArray)
    assert batch_step.shape == (4, 360, 640, 3)
    assert batch_step.flags.owndata is False
    
    # Empty slice
    batch_empty = ingestor[5:2]
    assert isinstance(batch_empty, np.ndarray)
    assert batch_empty.shape == (0, 360, 640, 3)

def test_video_reader_batch_list(mock_video_factory):
    """Verify batch retrieval shape, type, and zero-copy flags for list/sequence indices."""
    video_path = mock_video_factory(name="test_list.mp4", num_frames=10, width=640, height=360)
    ingestor = DroneVideoIngestor(video_path)
    
    # List of indices
    batch = ingestor[[0, 2, 4]]
    assert isinstance(batch, DecordFrameArray)
    assert batch.shape == (3, 360, 640, 3)
    assert batch.flags.owndata is False
    
    # Tuple of indices
    batch_tuple = ingestor[(1, 3, 5)]
    assert isinstance(batch_tuple, DecordFrameArray)
    assert batch_tuple.shape == (3, 360, 640, 3)
    assert batch_tuple.flags.owndata is False
    
    # Range of indices
    batch_range = ingestor[range(2, 6)]
    assert isinstance(batch_range, DecordFrameArray)
    assert batch_range.shape == (4, 360, 640, 3)
    assert batch_range.flags.owndata is False

def test_video_reader_bounds_checking(mock_video_factory):
    """Verify bounds checking (raising IndexError for invalid indices)."""
    video_path = mock_video_factory(name="test_bounds.mp4", num_frames=5)
    ingestor = DroneVideoIngestor(video_path)
    
    # Out of bounds positive
    with pytest.raises(IndexError):
        _ = ingestor[5]
        
    # Out of bounds negative
    with pytest.raises(IndexError):
        _ = ingestor[-6]
        
    # In list of indices, one is out of bounds
    with pytest.raises(IndexError):
        _ = ingestor[[0, 1, 5]]

def test_video_reader_lifetime_safety(mock_video_factory):
    """
    Verify that the frame remains accessible and is not corrupted after deleting
    the ingestor and forcing garbage collection.
    """
    video_path = mock_video_factory(name="test_lifetime.mp4", num_frames=5, width=640, height=360)
    ingestor = DroneVideoIngestor(video_path)
    
    # Fetch frame
    frame = ingestor[0]
    expected_sum = frame.sum()
    expected_mean = frame.mean()
    
    # Delete ingestor
    del ingestor
    
    # Force garbage collection
    gc.collect()
    gc.collect()
    
    # Check that data is accessible, not corrupted, and does not segfault
    assert frame.sum() == expected_sum
    assert frame.mean() == expected_mean
    assert frame[0, 0, 0] is not None
