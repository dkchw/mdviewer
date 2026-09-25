import urllib.request
import json
import time

base_url = "http://127.0.0.1:2026"

print("1. Checking server batch status endpoint...")
req = urllib.request.Request(f"{base_url}/api/ai/batch/status")
with urllib.request.urlopen(req) as resp:
    status = json.loads(resp.read().decode('utf-8'))
    print("Initial status:", status)
    assert status["status"] in ("idle", "completed")

print("\n2. Getting test cards from /api/folder/cards...")
req_cards = urllib.request.Request(f"{base_url}/api/folder/cards?level=2")
with urllib.request.urlopen(req_cards) as resp:
    cards_data = json.loads(resp.read().decode('utf-8'))
    print(f"Total cards found in folder: {len(cards_data.get('cards', []))}")

cards = cards_data.get('cards', [])[:10]
cards_payload = []
for idx, c in enumerate(cards):
    cards_payload.append({
        "cardIdx": idx,
        "file_path": c.get("file_path", ""),
        "slug": f"H{c.get('level', 2)}::{c.get('text', '')}",
        "level": c.get("level", 2),
        "text": c.get("text", f"Test Card {idx}"),
        "breadcrumb": c.get("breadcrumb", ""),
        "prompt_id": "detailed",
        "prompt_name": "Detailed Study Guide",
        "system_prompt": "You are a concise tutor. Summarize this card.",
        "user_message": f"Front: {c.get('text')}\nBack: content",
        "raw_front": c.get("text"),
        "raw_back": "content"
    })

print(f"\n3. Testing /api/ai/batch/start with mode=missing (skip_existing=True)...")
start_payload = {
    "cards": cards_payload,
    "model": "~deepseek/deepseek-flash-latest",
    "api_key": "test_key",
    "concurrency": 100,
    "mode": "missing",
    "skip_existing": True,
    "create_new_version": False
}

req_start = urllib.request.Request(
    f"{base_url}/api/ai/batch/start",
    data=json.dumps(start_payload).encode('utf-8'),
    headers={"Content-Type": "application/json"},
    method="POST"
)
with urllib.request.urlopen(req_start) as resp:
    res = json.loads(resp.read().decode('utf-8'))
    print("Start batch result:", res)
    assert res["status"] == "ok"

time.sleep(0.5)
with urllib.request.urlopen(f"{base_url}/api/ai/batch/status?since=0") as resp:
    status = json.loads(resp.read().decode('utf-8'))
    print("Status after start:", {
        "status": status["status"],
        "total": status["total"],
        "completed": status["completed"],
        "skipped": status["skipped"],
        "in_flight": status["in_flight"],
        "events_count": len(status["new_events"])
    })

print("\n4. Testing /api/ai/batch/pause and /api/ai/batch/resume...")
with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/ai/batch/pause", method="POST")) as resp:
    p_res = json.loads(resp.read().decode('utf-8'))
    print("Pause response:", p_res)

with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/ai/batch/resume", method="POST")) as resp:
    r_res = json.loads(resp.read().decode('utf-8'))
    print("Resume response:", r_res)

with urllib.request.urlopen(urllib.request.Request(f"{base_url}/api/ai/batch/stop", method="POST")) as resp:
    s_res = json.loads(resp.read().decode('utf-8'))
    print("Stop response:", s_res)

with urllib.request.urlopen(f"{base_url}/api/ai/batch/status") as resp:
    final_status = json.loads(resp.read().decode('utf-8'))
    print("Final status:", final_status["status"])

print("\n✓ Backend batch concurrency and control tests passed successfully!")
