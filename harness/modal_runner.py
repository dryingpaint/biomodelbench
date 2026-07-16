"""Generic Modal runner for any BioModelBench task.

Given a task_id, this finds the task at `tasks/<task_id>/` in the repo,
uploads its `bundle/` to a shared Modal Volume, runs one headless
`claude --print` attempt in a Modal A10G container mounted against that
volume, syncs artifacts back locally, and invokes the task's `grade.py`.

Usage
-----

    # 1. Build the task's bundle + hidden answer (one time, or after any
    #    change to the underlying data).
    python tasks/<task_id>/build.py

    # 2. Upload bundle to the shared Modal Volume.
    uv run modal run harness/modal_runner.py::volume_upload --task <task_id>

    # 3. Launch a single agent attempt.
    uv run modal run --detach harness/modal_runner.py::launch --task <task_id>

Directory conventions
---------------------

Every task must expose:

    tasks/<task_id>/
        prompt.md         agent-facing prompt
        task.yaml         metadata (yaml)
        build.py          builds bundle/ and hidden/
        grade.py          takes --submission and --out; writes grade.json
        bundle/           what ships to the agent (parquet, csv, whatever)
        hidden/           ground-truth answer file(s) — NEVER shipped
        runs/<run_id>/    per-run artifacts (this script writes here)

The agent-facing prompt.md is copied into `bundle/` before upload so it
appears alongside train.parquet / test.parquet inside the container.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import modal

from harness.image import build_image

APP_NAME = "biomodelbench"
VOL_NAME = "biomodelbench-tasks"
VOL_MOUNT = Path("/vol")
REPO_ROOT = Path(__file__).resolve().parent.parent

app = modal.App(APP_NAME, image=build_image())
volume = modal.Volume.from_name(VOL_NAME, create_if_missing=True)

AGENT_COMMAND_DEFAULT = (
    'claude --dangerously-skip-permissions --print --output-format stream-json --verbose '
    '"$(cat prompt.md)"'
)


def _task_dir(task_id: str) -> Path:
    p = REPO_ROOT / "tasks" / task_id
    if not p.exists():
        raise SystemExit(f"task not found: {p}")
    return p


def _task_bundle(task_id: str) -> Path:
    p = _task_dir(task_id) / "bundle"
    if not p.exists() or not any(p.iterdir()):
        raise SystemExit(
            f"bundle for {task_id} is missing or empty. "
            f"Run `python tasks/{task_id}/build.py` first."
        )
    return p


# ---------------------------------------------------------------------------
# Volume operations
# ---------------------------------------------------------------------------


@app.function(volumes={str(VOL_MOUNT): volume}, timeout=1800)
def _upload_impl(files: dict[str, bytes], remote_name: str) -> dict:
    dst = VOL_MOUNT / "tasks" / remote_name
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for rel, blob in files.items():
        p = dst / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)
    volume.commit()
    return {
        "remote_name": remote_name,
        "n_files": len(files),
        "total_bytes": sum(len(v) for v in files.values()),
        "path": str(dst),
    }


@app.local_entrypoint()
def volume_upload(task: str):
    """Upload tasks/<task>/bundle/ (plus the task's prompt.md) to the volume."""
    bundle = _task_bundle(task)
    prompt = _task_dir(task) / "prompt.md"
    files: dict[str, bytes] = {}
    for p in sorted(bundle.rglob("*")):
        if p.is_file():
            files[str(p.relative_to(bundle))] = p.read_bytes()
    if prompt.exists() and "prompt.md" not in files:
        files["prompt.md"] = prompt.read_bytes()
    total_mb = sum(len(v) for v in files.values()) / 1e6
    print(f"Uploading {len(files)} files ({total_mb:.1f} MB) → tasks/{task}/ on volume {VOL_NAME}")
    res = _upload_impl.remote(files, task)
    print(res)


@app.function(volumes={str(VOL_MOUNT): volume}, timeout=1800)
def _download_impl(task: str, run_id: str) -> dict[str, bytes]:
    src = VOL_MOUNT / "runs" / task / run_id
    out: dict[str, bytes] = {}
    if not src.exists():
        return out
    for p in sorted(src.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(src))] = p.read_bytes()
    return out


# ---------------------------------------------------------------------------
# Agent run
# ---------------------------------------------------------------------------


@app.function(
    gpu="A10G",
    timeout=14400,
    memory=32768,
    cpu=8,
    secrets=[modal.Secret.from_name("anthropic-api")],
    volumes={str(VOL_MOUNT): volume},
    max_containers=1,
)
def _run_one(
    task: str,
    run_id: str,
    agent_command: str,
    wall_clock_seconds: int,
) -> dict:
    src = VOL_MOUNT / "tasks" / task
    if not src.exists():
        return {"error": f"task not found on volume: {src}", "returncode": 127}

    workdir = Path("/task")
    workdir.mkdir(parents=True, exist_ok=True)
    for p in src.rglob("*"):
        if p.is_file():
            dst = workdir / p.relative_to(src)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(p.read_bytes())

    os.environ.setdefault("IS_SANDBOX", "1")
    os.environ.setdefault("CLAUDE_CODE_DANGEROUSLY_ALLOW_ROOT", "1")

    log_path = workdir / "agent_log.jsonl"
    stderr_path = workdir / "agent_stderr.txt"
    t0 = time.time()
    with open(log_path, "wb") as log_f, open(stderr_path, "wb") as err_f:
        proc = subprocess.Popen(
            agent_command, shell=True, cwd=str(workdir), stdout=log_f, stderr=err_f,
        )
        try:
            proc.wait(timeout=wall_clock_seconds)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
    duration = time.time() - t0

    runs_dst = VOL_MOUNT / "runs" / task / run_id
    runs_dst.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, bytes] = {}
    for path in sorted(workdir.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(workdir))
        try:
            data = path.read_bytes()
        except OSError:
            continue
        artifacts[rel] = data
        target = runs_dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    volume.commit()

    def _tail(p: Path, n: int = 4000) -> str:
        try:
            b = p.read_bytes()
        except OSError:
            return ""
        return b[-n:].decode("utf-8", errors="replace")

    return {
        "returncode": proc.returncode,
        "duration_seconds": round(duration, 2),
        "n_artifacts": len(artifacts),
        "stdout_tail": _tail(log_path),
        "stderr_tail": _tail(stderr_path),
        "runs_path": str(runs_dst),
    }


@app.local_entrypoint()
def launch(
    task: str,
    run_id: str = "",
    agent_command: str = AGENT_COMMAND_DEFAULT,
    wall_clock_seconds: int = 14000,
    skip_grade: bool = False,
    answer_filename: str = "answer.parquet",
):
    """Run one agent attempt, sync artifacts, invoke the task's grade.py."""
    task_dir = _task_dir(task)
    _task_bundle(task)  # sanity check: bundle exists

    if not run_id:
        run_id = time.strftime("%Y%m%dT%H%M%S")
    print(f"[{task}] launching run_id={run_id} (wall_clock ≤ {wall_clock_seconds}s)")
    result = _run_one.remote(task, run_id, agent_command, wall_clock_seconds)
    print(f"[{task}] rc={result.get('returncode')} duration={result.get('duration_seconds')}s artifacts={result.get('n_artifacts')}")

    files = _download_impl.remote(task, run_id)
    out_dir = task_dir / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    for rel, blob in files.items():
        p = out_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)
    (out_dir / "run_summary.json").write_text(json.dumps({
        "task": task,
        "run_id": run_id,
        "returncode": result.get("returncode"),
        "duration_seconds": result.get("duration_seconds"),
        "stdout_tail": result.get("stdout_tail"),
        "stderr_tail": result.get("stderr_tail"),
        "n_artifacts": len(files),
    }, indent=2))
    print(f"[{task}] wrote {len(files)} artifacts to {out_dir}")

    grade_script = task_dir / "grade.py"
    answer = out_dir / answer_filename
    if skip_grade:
        return
    if not answer.exists():
        print(f"[{task}] no {answer_filename} produced; skipping grade")
        return
    if not grade_script.exists():
        print(f"[{task}] no grade.py at {grade_script}; skipping grade")
        return
    grade_out = out_dir / "grade.json"
    try:
        subprocess.run(
            ["uv", "run", "--with", "pandas", "--with", "pyarrow", "--with", "scikit-learn",
             "python", str(grade_script), "--submission", str(answer), "--out", str(grade_out)],
            check=True,
        )
        print(f"[{task}] grade written to {grade_out}")
        print(grade_out.read_text())
    except subprocess.CalledProcessError as exc:
        print(f"[{task}] grader failed: {exc}")
