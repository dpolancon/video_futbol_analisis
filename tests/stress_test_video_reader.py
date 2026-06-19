import os
import gc
import time
import ctypes
import tempfile
import cv2
import numpy as np
import decord
from ctypes import wintypes
from src.ingestion.video_reader import DroneVideoIngestor, DecordFrameArray

import subprocess
import re

def get_memory_usage_bytes() -> int:
    try:
        pid = os.getpid()
        cmd = ["wmic", "process", "where", f"processid={pid}", "get", "WorkingSetSize"]
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
        lines = [line.strip() for line in output.split('\n') if line.strip()]
        if len(lines) >= 2:
            return int(lines[1])
    except Exception:
        pass
    try:
        cmd = ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"]
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
        parts = output.strip().split(',')
        if len(parts) >= 5:
            digits = re.findall(r'\d+', parts[4])
            if digits:
                return int("".join(digits)) * 1024
    except Exception:
        pass
    return 0

def create_mock_video(path, num_frames=100, width=1280, height=720, color=(40, 150, 40)):
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(path, fourcc, 30.0, (width, height))
    for _ in range(num_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = color
        cv2.circle(frame, (width // 2, height // 2), 100, (255, 255, 255), 3)
        out.write(frame)
    out.release()

def run_performance_benchmarks(video_path):
    print("=== RUNNING PERFORMANCE BENCHMARKS ===")
    ingestor = DroneVideoIngestor(video_path)
    n_frames = len(ingestor)
    
    # 1. Benchmark Single Frame ctypes casting (DroneVideoIngestor.get_frame)
    start_time = time.perf_counter()
    for i in range(n_frames):
        frame = ingestor.get_frame(i)
        _ = frame[0, 0, 0] # access data
    ctypes_single_time = time.perf_counter() - start_time
    
    # 2. Benchmark Single Frame decord .asnumpy()
    start_time = time.perf_counter()
    for i in range(n_frames):
        decord_frame = ingestor._vr[i]
        np_arr = decord_frame.asnumpy()
        _ = np_arr[0, 0, 0] # access data
    decord_single_time = time.perf_counter() - start_time
    
    print(f"Single Frame - Ctypes Pointer Casting: {ctypes_single_time:.4f}s")
    print(f"Single Frame - Decord Native .asnumpy(): {decord_single_time:.4f}s")
    single_speedup = decord_single_time / ctypes_single_time if ctypes_single_time > 0 else 0
    print(f"Single Frame Speedup: {single_speedup:.2f}x")
    
    # 3. Benchmark Batch Frame ctypes casting (DroneVideoIngestor.get_batch)
    batch_size = 10
    n_batches = n_frames // batch_size
    start_time = time.perf_counter()
    for b in range(n_batches):
        indices = list(range(b * batch_size, (b + 1) * batch_size))
        batch = ingestor.get_batch(indices)
        _ = batch[0, 0, 0, 0]
    ctypes_batch_time = time.perf_counter() - start_time
    
    # 4. Benchmark Batch Frame decord .asnumpy()
    start_time = time.perf_counter()
    for b in range(n_batches):
        indices = list(range(b * batch_size, (b + 1) * batch_size))
        decord_batch = ingestor._vr.get_batch(indices)
        np_arr = decord_batch.asnumpy()
        _ = np_arr[0, 0, 0, 0]
    decord_batch_time = time.perf_counter() - start_time
    
    print(f"Batch (size {batch_size}) - Ctypes Pointer Casting: {ctypes_batch_time:.4f}s")
    print(f"Batch (size {batch_size}) - Decord Native .asnumpy(): {decord_batch_time:.4f}s")
    batch_speedup = decord_batch_time / ctypes_batch_time if ctypes_batch_time > 0 else 0
    print(f"Batch Speedup: {batch_speedup:.2f}x")
    
    return {
        "ctypes_single_time": ctypes_single_time,
        "decord_single_time": decord_single_time,
        "single_speedup": single_speedup,
        "ctypes_batch_time": ctypes_batch_time,
        "decord_batch_time": decord_batch_time,
        "batch_speedup": batch_speedup
    }

def run_memory_leak_test(video_path):
    print("\n=== RUNNING MEMORY LEAK TEST ===")
    gc.collect()
    initial_mem = get_memory_usage_bytes()
    print(f"Initial process memory: {initial_mem / (1024*1024):.2f} MB")
    
    n_loops = 50
    for loop in range(n_loops):
        ingestor = DroneVideoIngestor(video_path)
        # Load all frames
        for i in range(len(ingestor)):
            frame = ingestor[i]
            _ = frame.sum()
        # Load batches
        for b in range(len(ingestor) // 10):
            batch = ingestor[b*10:(b+1)*10]
            _ = batch.sum()
            
        del ingestor
        gc.collect()
        
    final_mem = get_memory_usage_bytes()
    diff_mem = final_mem - initial_mem
    print(f"Final process memory (after {n_loops} loops): {final_mem / (1024*1024):.2f} MB")
    print(f"Difference: {diff_mem / (1024*1024):.2f} MB")
    
    # Check if difference is positive and substantial
    is_leak = diff_mem > 15 * 1024 * 1024  # > 15 MB increase
    if is_leak:
        print("WARNING: Potential memory leak detected!")
    else:
        print("Memory footprint is stable. No major memory leaks detected.")
        
    return {
        "initial_mem_mb": initial_mem / (1024*1024),
        "final_mem_mb": final_mem / (1024*1024),
        "diff_mem_mb": diff_mem / (1024*1024),
        "potential_leak": is_leak
    }

def run_memory_safety_checks(video_path):
    print("\n=== RUNNING MEMORY SAFETY CHECKS ===")
    
    # Test case 1: Ingestor deletion with strong reference to frame
    ingestor = DroneVideoIngestor(video_path)
    frame = ingestor[0]
    expected_sum = frame.sum()
    expected_mean = frame.mean()
    expected_shape = frame.shape
    
    # Delete the ingestor
    del ingestor
    gc.collect()
    gc.collect()
    
    # Access frame data
    try:
        current_sum = frame.sum()
        current_mean = frame.mean()
        assert current_sum == expected_sum, f"Data mismatch! Expected sum {expected_sum}, got {current_sum}"
        assert current_mean == expected_mean, f"Data mismatch! Expected mean {expected_mean}, got {current_mean}"
        assert frame.shape == expected_shape
        print("Test 1 (Ingestor deleted, frame used): PASSED (data is valid, no segfault)")
    except Exception as e:
        print(f"Test 1 FAILED: {e}")
        
    # Test case 2: Sliced view of frame after ingestor and original frame deletion
    ingestor = DroneVideoIngestor(video_path)
    frame = ingestor[0]
    frame_slice = frame[10:20, 10:20].view()
    expected_slice_sum = frame_slice.sum()
    
    del ingestor
    del frame
    gc.collect()
    gc.collect()
    
    try:
        current_slice_sum = frame_slice.sum()
        assert current_slice_sum == expected_slice_sum, "Sliced frame data corrupted after deleting base frame/ingestor!"
        print("Test 2 (Frame view remains valid after deleting base frame/ingestor): PASSED")
    except Exception as e:
        print(f"Test 2 FAILED: {e}")

def run_boundary_and_corner_cases(video_path):
    print("\n=== RUNNING BOUNDARY AND CORNER CASES ===")
    ingestor = DroneVideoIngestor(video_path)
    n_frames = len(ingestor)
    
    passed_cases = 0
    total_cases = 0
    
    # Case 1: Negative index bounds
    total_cases += 1
    try:
        f = ingestor[-n_frames]
        assert f is not None
        passed_cases += 1
        print("Case 1 (Limit negative index -n_frames): PASSED")
    except Exception as e:
        print(f"Case 1 FAILED: {e}")
        
    # Case 2: Out of bounds negative index
    total_cases += 1
    try:
        _ = ingestor[-n_frames - 1]
        print("Case 2 FAILED: did not raise IndexError for out-of-bounds negative index")
    except IndexError:
        passed_cases += 1
        print("Case 2 (Out of bounds negative index): PASSED (raised IndexError)")
    except Exception as e:
        print(f"Case 2 FAILED: raised wrong exception {type(e).__name__}: {e}")
        
    # Case 3: Out of bounds positive index
    total_cases += 1
    try:
        _ = ingestor[n_frames]
        print("Case 3 FAILED: did not raise IndexError for out-of-bounds positive index")
    except IndexError:
        passed_cases += 1
        print("Case 3 (Out of bounds positive index): PASSED (raised IndexError)")
    except Exception as e:
        print(f"Case 3 FAILED: raised wrong exception {type(e).__name__}: {e}")

    # Case 4: Empty slices
    total_cases += 1
    try:
        slice_empty = ingestor[5:2]
        assert isinstance(slice_empty, np.ndarray)
        assert len(slice_empty) == 0
        assert slice_empty.shape == (0, 720, 1280, 3)
        passed_cases += 1
        print("Case 4 (Empty slice 5:2): PASSED")
    except Exception as e:
        print(f"Case 4 FAILED: {e}")
        
    # Case 5: Empty slice beyond bounds
    total_cases += 1
    try:
        slice_empty = ingestor[n_frames:n_frames+5]
        assert len(slice_empty) == 0
        assert slice_empty.shape == (0, 720, 1280, 3)
        passed_cases += 1
        print("Case 5 (Empty slice out of bounds): PASSED")
    except Exception as e:
        print(f"Case 5 FAILED: {e}")
        
    # Case 6: Empty index list
    total_cases += 1
    try:
        batch_empty = ingestor[[]]
        assert len(batch_empty) == 0
        assert batch_empty.shape == (0, 720, 1280, 3)
        passed_cases += 1
        print("Case 6 (Empty list index): PASSED")
    except Exception as e:
        print(f"Case 6 FAILED: {e}")
        
    # Case 7: Sequence containing out of bounds index
    total_cases += 1
    try:
        _ = ingestor[[0, 1, n_frames]]
        print("Case 7 FAILED: did not raise IndexError for sequence containing out-of-bounds index")
    except IndexError:
        passed_cases += 1
        print("Case 7 (Sequence with out of bounds index): PASSED (raised IndexError)")
    except Exception as e:
        print(f"Case 7 FAILED: raised wrong exception {type(e).__name__}: {e}")
        
    # Case 8: Sequence containing negative out of bounds index
    total_cases += 1
    try:
        _ = ingestor[[0, 1, -n_frames-1]]
        print("Case 8 FAILED: did not raise IndexError for sequence containing negative out-of-bounds index")
    except IndexError:
        passed_cases += 1
        print("Case 8 (Sequence with negative out of bounds index): PASSED (raised IndexError)")
    except Exception as e:
        print(f"Case 8 FAILED: raised wrong exception {type(e).__name__}: {e}")
        
    # Case 9: Invalid index type
    total_cases += 1
    try:
        _ = ingestor[3.5]
        print("Case 9 FAILED: did not raise TypeError for float index")
    except TypeError:
        passed_cases += 1
        print("Case 9 (Invalid index type - float): PASSED (raised TypeError)")
    except Exception as e:
        print(f"Case 9 FAILED: raised wrong exception {type(e).__name__}: {e}")
        
    # Case 10: Non-existent file
    total_cases += 1
    try:
        _ = DroneVideoIngestor("non_existent_file.mp4")
        print("Case 10 FAILED: did not raise FileNotFoundError")
    except FileNotFoundError:
        passed_cases += 1
        print("Case 10 (Non-existent file): PASSED (raised FileNotFoundError)")
    except Exception as e:
        print(f"Case 10 FAILED: raised wrong exception {type(e).__name__}: {e}")
        
    print(f"Boundary and Corner cases result: {passed_cases}/{total_cases} passed.")
    return passed_cases, total_cases

if __name__ == "__main__":
    temp_dir = tempfile.mkdtemp()
    video_path = os.path.join(temp_dir, "stress_test.mp4")
    try:
        print("Creating mock video...")
        create_mock_video(video_path, num_frames=100, width=1280, height=720)
        print("Mock video created successfully.")
        
        perf_metrics = run_performance_benchmarks(video_path)
        mem_metrics = run_memory_leak_test(video_path)
        run_memory_safety_checks(video_path)
        passed_cases, total_cases = run_boundary_and_corner_cases(video_path)
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)
        os.rmdir(temp_dir)
