"""Live end-to-end audit verification script for Gideon backend."""
import subprocess
import time
import sys
import uuid
import httpx

PORT = 8009
BASE_URL = f"http://127.0.0.1:{PORT}"

def run_live_audit():
    print(f"[1/6] Launching Gideon backend on port {PORT}...")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait for server to start
        ready = False
        for _ in range(30):
            try:
                resp = httpx.get(f"{BASE_URL}/health", timeout=1.0)
                if resp.status_code == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(0.3)

        if not ready:
            print("ERROR: Server failed to start within timeout.")
            return False

        print(f"[2/6] Backend health confirmed: {resp.json()}")

        # 1. Exercise Agent Task Creation & Planning
        task_payload = {
            "title": "Live Audit Directive",
            "user_request": "Review workspace architecture and prepare project overview",
            "assigned_agent_id": "agent_coding"
        }
        res_create = httpx.post(f"{BASE_URL}/api/v1/agents/tasks", json=task_payload, timeout=5.0)
        assert res_create.status_code == 201, f"Task create failed: {res_create.text}"
        task_data = res_create.json()
        task_id = task_data["id"]
        print(f"[3/6] Task created & planned. ID: {task_id}, Steps: {len(task_data['steps'])}")

        # 2. Progress Check
        res_prog = httpx.get(f"{BASE_URL}/api/v1/agents/tasks/{task_id}/progress", timeout=5.0)
        assert res_prog.status_code == 200
        print(f"[4/6] Progress retrieved: {res_prog.json()['status']}, steps: {res_prog.json()['total_steps_count']}")

        # 3. Test Cancellation
        res_cancel = httpx.post(f"{BASE_URL}/api/v1/agents/tasks/{task_id}/cancel", timeout=5.0)
        assert res_cancel.status_code == 200
        assert res_cancel.json()["status"] == "cancelled"
        print(f"[5/6] Task cancellation confirmed: status={res_cancel.json()['status']}")

        # 4. Generate Daily Summary
        res_summary = httpx.post(f"{BASE_URL}/api/v1/agents/summaries/generate", json={"force_regenerate": True}, timeout=10.0)
        assert res_summary.status_code == 200
        print(f"[6/6] Daily Business Summary generated: Date={res_summary.json()['summary_date']}, Status={res_summary.json()['delivery_status']}")

        return task_id
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("Backend server stopped.")


def verify_restart_persistence(task_id: str):
    print(f"\n[Restart Test] Restarting Gideon backend on port {PORT}...")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # Wait for server
        for _ in range(30):
            try:
                resp = httpx.get(f"{BASE_URL}/health", timeout=1.0)
                if resp.status_code == 200:
                    break
            except Exception:
                time.sleep(0.3)

        # Query task history from the new server instance
        res_get = httpx.get(f"{BASE_URL}/api/v1/agents/tasks/{task_id}", timeout=5.0)
        assert res_get.status_code == 200, f"Failed to retrieve task after restart: {res_get.text}"
        recovered_task = res_get.json()
        assert recovered_task["id"] == task_id
        assert recovered_task["status"] == "cancelled"
        print(f"PASS: Task {task_id} successfully retrieved from database after restart with status '{recovered_task['status']}'.")
        return True
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("Backend restart test completed.")


if __name__ == "__main__":
    t_id = run_live_audit()
    if t_id:
        verify_restart_persistence(t_id)
        print("\nALL LIVE E2E AUDIT CHECKS PASSED.")
    else:
        sys.exit(1)

