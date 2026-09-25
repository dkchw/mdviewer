import urllib.request
import json
import time

BASE_URL = "http://127.0.0.1:2026"

def post_json(path, data):
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get_json(path):
    with urllib.request.urlopen(f"{BASE_URL}{path}") as resp:
        return json.loads(resp.read().decode("utf-8"))

def test_multi_batch():
    print("Testing Multi-Batch Concurrency Backend API...")

    # Create test cards for File A and File B
    cards_a = [
        {
            "cardIdx": i,
            "file_path": "DaF_Kompakt_Neu/test_file_a.md",
            "slug": f"heading-a-{i}",
            "level": 2,
            "text": f"Card A {i}",
            "breadcrumb": "Test A",
            "prompt_id": "detailed",
            "prompt_name": "Detailed",
            "system_prompt": "You are a tutor. Answer briefly.",
            "user_message": f"Explain Term A {i}",
            "raw_front": f"Term A {i}",
            "raw_back": f"Definition A {i}"
        }
        for i in range(10)
    ]

    cards_b = [
        {
            "cardIdx": i,
            "file_path": "DaF_Kompakt_Neu/test_file_b.md",
            "slug": f"heading-b-{i}",
            "level": 2,
            "text": f"Card B {i}",
            "breadcrumb": "Test B",
            "prompt_id": "detailed",
            "prompt_name": "Detailed",
            "system_prompt": "You are a tutor. Answer briefly.",
            "user_message": f"Explain Term B {i}",
            "raw_front": f"Term B {i}",
            "raw_back": f"Definition B {i}"
        }
        for i in range(10)
    ]

    # 1. Start Batch A
    res_a = post_json("/api/ai/batch/start", {
        "cards": cards_a,
        "file_path": "DaF_Kompakt_Neu/test_file_a.md",
        "concurrency": 5,
        "mode": "overwrite",
        "skip_existing": False
    })
    print("Batch A started:", res_a)
    assert res_a["status"] == "ok"
    batch_id_a = res_a["batch_id"]

    # 2. Immediately start Batch B for a DIFFERENT file
    res_b = post_json("/api/ai/batch/start", {
        "cards": cards_b,
        "file_path": "DaF_Kompakt_Neu/test_file_b.md",
        "concurrency": 5,
        "mode": "overwrite",
        "skip_existing": False
    })
    print("Batch B started:", res_b)
    assert res_b["status"] == "ok"
    batch_id_b = res_b["batch_id"]
    assert batch_id_a != batch_id_b

    # 3. Check /api/ai/batch/list to confirm BOTH batches are active concurrently
    batches_list = get_json("/api/ai/batch/list")
    print("Active batches summary:", batches_list)
    b_ids = [b["batch_id"] for b in batches_list["active_batches"]]
    assert batch_id_a in b_ids, f"Batch A {batch_id_a} should be in active batches"
    assert batch_id_b in b_ids, f"Batch B {batch_id_b} should be in active batches"
    print("✓ Confirmed: Both Batch A and Batch B are registered and running concurrently!")

    # 4. Check status of each batch independently
    status_a = get_json(f"/api/ai/batch/status?batch_id={batch_id_a}")
    status_b = get_json(f"/api/ai/batch/status?batch_id={batch_id_b}")
    print(f"Status A ({batch_id_a}): status={status_a['status']}, file={status_a['file_path']}")
    print(f"Status B ({batch_id_b}): status={status_b['status']}, file={status_b['file_path']}")
    assert status_a["file_path"] == "DaF_Kompakt_Neu/test_file_a.md"
    assert status_b["file_path"] == "DaF_Kompakt_Neu/test_file_b.md"

    # 5. Test Pause only Batch A
    pause_res = post_json("/api/ai/batch/pause", {"batch_id": batch_id_a})
    print("Paused Batch A:", pause_res)
    time.sleep(0.3)
    status_a_after = get_json(f"/api/ai/batch/status?batch_id={batch_id_a}")
    status_b_after = get_json(f"/api/ai/batch/status?batch_id={batch_id_b}")
    print(f"After pause A: status_a={status_a_after['status']}, status_b={status_b_after['status']}")
    assert status_a_after["status"] == "paused", "Batch A should be paused"
    assert status_b_after["status"] in ("running", "completed"), "Batch B should still be running or completed, not paused"
    print("✓ Confirmed: Pausing Batch A did not pause Batch B!")

    # 6. Resume Batch A
    resume_res = post_json("/api/ai/batch/resume", {"batch_id": batch_id_a})
    print("Resumed Batch A:", resume_res)

    # 7. Stop all batches
    stop_res = post_json("/api/ai/batch/stop", {"batch_id": "all"})
    print("Stopped all batches:", stop_res)
    time.sleep(0.5)

    status_a_stop = get_json(f"/api/ai/batch/status?batch_id={batch_id_a}")
    status_b_stop = get_json(f"/api/ai/batch/status?batch_id={batch_id_b}")
    print(f"Final status A: {status_a_stop['status']}, B: {status_b_stop['status']}")
    assert status_a_stop["status"] in ("stopped", "completed")
    assert status_b_stop["status"] in ("stopped", "completed")
    print("🎉 Multi-Batch Backend API Test passed completely!")

if __name__ == "__main__":
    test_multi_batch()
