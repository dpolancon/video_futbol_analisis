import os
import gc
import sys
import time
import subprocess
import threading
import numpy as np
import decord
from src.ingestion.video_reader import DroneVideoIngestor, DecordFrameArray

def get_memory_usage_bytes() -> int:
    try:
        pid = os.getpid()
        out = subprocess.check_output(f"powershell -NoProfile -Command (Get-Process -Id {pid}).WorkingSet", shell=True)
        return int(out.strip())
    except Exception as e:
        print(f"Failed to get memory usage: {e}")
        return 0

def run_performance_verification(video_path: str):
    print("\n--- 1. PERFORMANCE VERIFICATION ---")
    
    # Instantiate ingestor
    ingestor = DroneVideoIngestor(video_path)
    vr = ingestor._vr
    
    # A. Benchmark isolated conversion (pointer cast vs copying)
    print("Pre-fetching 100 frames to isolate conversion from file/decoding overhead...")
    decord_frames = [vr[i] for i in range(100)]
    
    # Time zero-copy conversion
    start_zc = time.perf_counter()
    zc_arrays = [ingestor._to_numpy_zerocopy(df) for df in decord_frames]
    # Ensure they are valid and access memory
    for arr in zc_arrays:
        _ = arr[0, 0, 0]
    time_zc = time.perf_counter() - start_zc
    
    # Time copying (.asnumpy())
    start_copy = time.perf_counter()
    copy_arrays = [df.asnumpy() for df in decord_frames]
    for arr in copy_arrays:
        _ = arr[0, 0, 0]
    time_copy = time.perf_counter() - start_copy
    
    conversion_speedup = time_copy / time_zc if time_zc > 0 else 0
    print(f"Isolated 100 frames conversion:")
    print(f"  - Zero-copy Pointer Casting:  {time_zc * 1000:.4f} ms")
    print(f"  - Decord Native .asnumpy():   {time_copy * 1000:.4f} ms")
    print(f"  - Isolated Speedup:            {conversion_speedup:.2f}x")
    
    # B. Benchmark end-to-end fetching (which includes decoding)
    print("\nBenchmarking end-to-end retrieval of 100 frames...")
    
    # Time end-to-end zero-copy
    start_e2e_zc = time.perf_counter()
    for i in range(100):
        frame = ingestor[i]
        _ = frame[0, 0, 0]
    time_e2e_zc = time.perf_counter() - start_e2e_zc
    
    # Time end-to-end decord asnumpy()
    start_e2e_copy = time.perf_counter()
    for i in range(100):
        decord_frame = vr[i]
        np_arr = decord_frame.asnumpy()
        _ = np_arr[0, 0, 0]
    time_e2e_copy = time.perf_counter() - start_e2e_copy
    
    e2e_speedup = time_e2e_copy / time_e2e_zc if time_e2e_zc > 0 else 0
    print(f"End-to-end 100 frames retrieval:")
    print(f"  - DroneVideoIngestor (Zero-Copy): {time_e2e_zc:.4f} s")
    print(f"  - Decord + .asnumpy() (Copy):      {time_e2e_copy:.4f} s")
    print(f"  - End-to-end Speedup:              {e2e_speedup:.2f}x")
    
    return {
        "time_zc_ms": time_zc * 1000,
        "time_copy_ms": time_copy * 1000,
        "conversion_speedup": conversion_speedup,
        "time_e2e_zc": time_e2e_zc,
        "time_e2e_copy": time_e2e_copy,
        "e2e_speedup": e2e_speedup
    }

def run_lifetime_safety_verification(video_path: str):
    print("\n--- 2. LIFETIME SAFETY VERIFICATION ---")
    
    # Open ingestor
    ingestor = DroneVideoIngestor(video_path)
    
    # Fetch 100 frames
    print("Fetching 100 frames...")
    frames = [ingestor[i] for i in range(100)]
    
    # Take views / slices of each frame
    print("Creating sliced views of all frames...")
    views = [f[10:110, 10:110, :].view() for f in frames]
    
    # Save statistics for later verification
    expected_sums = [f.sum() for f in frames]
    expected_view_sums = [v.sum() for v in views]
    
    # Delete the ingestor
    print("Deleting ingestor reference and running GC loop...")
    del ingestor
    
    # Spin up threads that will continuously access the frame views
    stop_event = threading.Event()
    thread_errors = []
    
    def access_worker():
        try:
            while not stop_event.is_set():
                for idx, (f, v) in enumerate(zip(frames, views)):
                    # Compute stats to ensure memory access is correct and data is valid
                    s = f.sum()
                    assert s == expected_sums[idx], f"Frame {idx} sum changed! Expected {expected_sums[idx]}, got {s}"
                    
                    vs = v.sum()
                    assert vs == expected_view_sums[idx], f"View {idx} sum changed! Expected {expected_view_sums[idx]}, got {vs}"
                    
                    # Read random pixels
                    _ = f[50, 50, 0]
                    _ = v[20, 20, 0]
        except Exception as e:
            thread_errors.append(e)
            
    # Start threads
    threads = []
    for t_idx in range(4):
        t = threading.Thread(target=access_worker, name=f"AccessThread-{t_idx}")
        threads.append(t)
        t.start()
        
    # Run gc.collect in a loop on main thread
    print("Running GC collect loop on main thread while threads access frame data...")
    for _ in range(15):
        gc.collect()
        time.sleep(0.05)
        
    # Stop threads and join
    stop_event.set()
    for t in threads:
        t.join()
        
    assert len(thread_errors) == 0, f"Thread errors encountered: {thread_errors}"
    print("No Access Violations or data corruptions detected under thread & GC stress.")
    
    # B. Memory Leak stress test (100 iterations of create, fetch, delete, gc)
    print("\nRunning memory leak stress test (100 iterations)...")
    gc.collect()
    start_mem = get_memory_usage_bytes()
    print(f"  - Start Memory: {start_mem / (1024*1024):.2f} MB")
    
    for i in range(100):
        ing = DroneVideoIngestor(video_path)
        # Fetch frames and slices
        f_list = [ing[idx] for idx in range(0, 10, 2)]
        slices = [f[500:1500, 500:1500] for f in f_list]
        
        # Access and compute
        for s in slices:
            _ = s.sum()
            
        del f_list
        del slices
        del ing
        if i % 10 == 0:
            gc.collect()
            
    gc.collect()
    end_mem = get_memory_usage_bytes()
    diff_mem = end_mem - start_mem
    print(f"  - End Memory:   {end_mem / (1024*1024):.2f} MB")
    print(f"  - Difference:   {diff_mem / (1024*1024):.2f} MB")
    
    leak_detected = diff_mem > 10 * 1024 * 1024  # >10MB leak threshold
    if leak_detected:
        print("  - WARNING: Potential memory leak detected!")
    else:
        print("  - Memory is stable. No memory leaks detected.")
        
    return {
        "start_mem_mb": start_mem / (1024*1024),
        "end_mem_mb": end_mem / (1024*1024),
        "diff_mem_mb": diff_mem / (1024*1024),
        "leak_detected": leak_detected
    }

def run_edge_case_verification(video_path: str):
    print("\n--- 3. EDGE CASE VERIFICATION ---")
    ingestor = DroneVideoIngestor(video_path)
    n_frames = len(ingestor)
    h, w, c = ingestor._frame_shape
    
    passed_cases = 0
    total_cases = 0
    
    # Case 1: Empty slice (start > stop)
    total_cases += 1
    try:
        arr = ingestor[5:2]
        assert isinstance(arr, np.ndarray)
        assert arr.shape == (0, h, w, c)
        passed_cases += 1
        print("  - Empty slice (5:2): PASSED")
    except Exception as e:
        print(f"  - Empty slice (5:2) FAILED: {e}")
        
    # Case 2: Negative slices
    total_cases += 1
    try:
        arr = ingestor[-5:-1]
        assert isinstance(arr, DecordFrameArray)
        assert arr.shape == (4, h, w, c)
        passed_cases += 1
        print("  - Negative slice (-5:-1): PASSED")
    except Exception as e:
        print(f"  - Negative slice (-5:-1) FAILED: {e}")
        
    # Case 3: Stride slices (step > 1)
    total_cases += 1
    try:
        arr = ingestor[0:20:5]
        assert isinstance(arr, DecordFrameArray)
        assert arr.shape == (4, h, w, c)
        passed_cases += 1
        print("  - Stride slice (0:20:5): PASSED")
    except Exception as e:
        print(f"  - Stride slice (0:20:5) FAILED: {e}")
        
    # Case 4: Reverse slice step (negative step)
    total_cases += 1
    try:
        # Note: reverse slices are resolved to indices in reverse order.
        arr = ingestor[9::-1]
        assert isinstance(arr, DecordFrameArray)
        assert arr.shape == (10, h, w, c)
        passed_cases += 1
        print("  - Reverse slice (9::-1): PASSED")
    except Exception as e:
        print(f"  - Reverse slice (9::-1) FAILED: {e}")

    # Case 5: Out of bounds list of indices
    total_cases += 1
    try:
        _ = ingestor[[0, 1, n_frames]]
        print("  - Out of bounds list FAILED: did not raise IndexError")
    except IndexError:
        passed_cases += 1
        print("  - Out of bounds list: PASSED (raised IndexError)")
    except Exception as e:
        print(f"  - Out of bounds list FAILED: wrong exception {type(e).__name__}: {e}")

    # Case 6: Empty list of indices
    total_cases += 1
    try:
        arr = ingestor[[]]
        assert isinstance(arr, np.ndarray)
        assert arr.shape == (0, h, w, c)
        passed_cases += 1
        print("  - Empty list: PASSED")
    except Exception as e:
        print(f"  - Empty list FAILED: {e}")

    # Case 7: Invalid type (float)
    total_cases += 1
    try:
        _ = ingestor[2.5]
        print("  - Invalid float index FAILED: did not raise TypeError")
    except TypeError:
        passed_cases += 1
        print("  - Invalid float index: PASSED (raised TypeError)")
    except Exception as e:
        print(f"  - Invalid float index FAILED: wrong exception {type(e).__name__}: {e}")
        
    print(f"Edge case verification: {passed_cases}/{total_cases} passed.")
    return passed_cases == total_cases

if __name__ == "__main__":
    video_path = "inputs/fecha06_1era.mp4"
    if not os.path.exists(video_path):
        print(f"Error: {video_path} not found.")
        sys.exit(1)
        
    perf = run_performance_verification(video_path)
    safety = run_lifetime_safety_verification(video_path)
    edge = run_edge_case_verification(video_path)
    
    print("\nVerification Complete.")
