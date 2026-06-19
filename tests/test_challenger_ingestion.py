import os
import gc
import time
import pytest
import numpy as np
import decord
import threading
import subprocess
import ctypes
from src.ingestion.video_reader import DroneVideoIngestor, DecordFrameArray

def get_process_memory_usage() -> int:
    pid = os.getpid()
    try:
        output = subprocess.check_output(f'tasklist /FI "PID eq {pid}" /NH', shell=True).decode('utf-8', errors='ignore')
        parts = output.strip().split()
        for part in reversed(parts):
            clean_part = part.replace(',', '').replace('.', '')
            if clean_part.isdigit():
                return int(clean_part) * 1024
    except Exception:
        pass
    return 0

def test_performance_verification(mock_video_factory):
    # Benchmark fetching 100 frames from a video using DroneVideoIngestor and compare it to using decord's standard asnumpy()
    video_path = mock_video_factory(name="test_perf_100.mp4", num_frames=100, width=1920, height=1080)
    
    # Warmup and instantiation
    ingestor = DroneVideoIngestor(video_path)
    vr = decord.VideoReader(video_path, ctx=decord.cpu(0), num_threads=0)
    
    # Pre-warm
    _ = vr[0].asnumpy()
    _ = ingestor[0]
    
    # A. Benchmark full fetching loop (including decoding)
    start_time = time.perf_counter()
    for i in range(100):
        frame = ingestor[i]
        _ = frame[0, 0, 0]
    ingestor_fetch_time = time.perf_counter() - start_time
    
    start_time = time.perf_counter()
    for i in range(100):
        decord_frame = vr[i]
        frame = decord_frame.asnumpy()
        _ = frame[0, 0, 0]
    decord_fetch_time = time.perf_counter() - start_time
    
    # B. Benchmark pure conversion speed (excluding decoding)
    decord_frames = [vr[i] for i in range(100)]
    
    start_time = time.perf_counter()
    for f in decord_frames:
        frame = ingestor._to_numpy_zerocopy(f)
        _ = frame[0, 0, 0]
    zerocopy_conv_time = time.perf_counter() - start_time
    
    start_time = time.perf_counter()
    for f in decord_frames:
        frame = f.asnumpy()
        _ = frame[0, 0, 0]
    asnumpy_conv_time = time.perf_counter() - start_time
    
    fetch_speedup = decord_fetch_time / ingestor_fetch_time if ingestor_fetch_time > 0 else 0
    conv_speedup = asnumpy_conv_time / zerocopy_conv_time if zerocopy_conv_time > 0 else 0
    
    print(f"\n[BENCHMARK RESULTS] 100 frames (1920x1080)")
    print(f"DroneVideoIngestor fetch time: {ingestor_fetch_time:.6f}s")
    print(f"Decord native asnumpy fetch time: {decord_fetch_time:.6f}s")
    print(f"Fetch speedup (decoding included): {fetch_speedup:.2f}x")
    print(f"DroneVideoIngestor pure conversion time: {zerocopy_conv_time:.6f}s")
    print(f"Decord native asnumpy pure conversion time: {asnumpy_conv_time:.6f}s")
    print(f"Conversion speedup (decoding excluded): {conv_speedup:.2f}x")
    
    # Ensure speedup of conversion is significant (e.g. >50x)
    assert conv_speedup > 50, f"Expected conversion speedup >50x, got {conv_speedup:.2f}x"

def test_lifetime_safety_verification(mock_video_factory):
    # Fetch many frames, delete ingestor reference, run gc.collect() in a loop,
    # spin up threads accessing frame views, and verify there are no Access Violations or memory leaks.
    video_path = mock_video_factory(name="test_lifetime_stress.mp4", num_frames=50, width=1280, height=720)
    
    initial_mem = get_process_memory_usage()
    
    ingestor = DroneVideoIngestor(video_path)
    
    # Fetch many frames
    frames = [ingestor[i] for i in range(50)]
    
    # Obtain sliced views of all frames
    frame_views = []
    for f in frames:
        frame_views.append(f[::2, ::2, :])
        frame_views.append(f[100:200, 100:200, 1:2])
        frame_views.append(f.view(DecordFrameArray))
    
    # Delete the ingestor reference and original frames, only views/slices remain
    del ingestor
    del frames
    
    # Run gc.collect() in a loop
    for _ in range(5):
        gc.collect()
        
    errors = []
    
    # Thread target to access the frame views
    def access_views(tid):
        try:
            for _ in range(100):
                for view in frame_views:
                    val = view.sum()
                    assert val >= 0
                    p = view[0, 0, 0]
                    assert p is not None
        except Exception as e:
            errors.append(e)

    # Spin up threads accessing frame views
    threads = []
    for i in range(8):
        t = threading.Thread(target=access_views, args=(i,))
        threads.append(t)
        t.start()
        
    # Simultaneously run gc.collect() in a loop on the main thread
    for _ in range(20):
        gc.collect()
        time.sleep(0.01)
        
    for t in threads:
        t.join()
        
    # Force gc and measure memory leak
    for _ in range(5):
        gc.collect()
        
    final_mem = get_process_memory_usage()
    mem_diff = final_mem - initial_mem
    
    # Verify no exceptions occurred
    assert len(errors) == 0, f"Thread errors: {errors}"
    
    print(f"\n[LIFETIME SAFETY] Initial Memory: {initial_mem / (1024*1024):.2f} MB")
    print(f"[LIFETIME SAFETY] Final Memory: {final_mem / (1024*1024):.2f} MB")
    print(f"[LIFETIME SAFETY] Memory Difference: {mem_diff / (1024*1024):.2f} MB")
    
    # Assert no memory leak
    assert mem_diff < 50 * 1024 * 1024, f"Memory increased by too much: {mem_diff / (1024*1024):.2f} MB"

def test_edge_cases(mock_video_factory):
    video_path = mock_video_factory(name="test_edge_cases.mp4", num_frames=10, width=640, height=360)
    ingestor = DroneVideoIngestor(video_path)
    
    # 1. Retrieve empty slices
    empty_slice = ingestor[5:2]
    assert isinstance(empty_slice, np.ndarray)
    assert empty_slice.shape == (0, 360, 640, 3)
    
    # Out of bounds empty slice
    empty_slice_oob = ingestor[10:15]
    assert isinstance(empty_slice_oob, np.ndarray)
    assert empty_slice_oob.shape == (0, 360, 640, 3)
    
    # 2. Negative slices
    neg_slice = ingestor[-3:-1]
    assert isinstance(neg_slice, DecordFrameArray)
    assert neg_slice.shape == (2, 360, 640, 3)
    
    # 3. Stride slices
    stride_slice = ingestor[1:8:2]
    assert isinstance(stride_slice, DecordFrameArray)
    assert stride_slice.shape == (4, 360, 640, 3)
    
    # Negative stride slice (reversed)
    rev_slice = ingestor[8:2:-2]
    assert isinstance(rev_slice, DecordFrameArray)
    assert rev_slice.shape == (3, 360, 640, 3)
    
    # 4. Out-of-bound lists
    with pytest.raises(IndexError):
        _ = ingestor[[0, 1, 10]]
        
    with pytest.raises(IndexError):
        _ = ingestor[[0, 1, -11]]
        
    # 5. Empty lists
    empty_list = ingestor[[]]
    assert isinstance(empty_list, np.ndarray)
    assert empty_list.shape == (0, 360, 640, 3)
