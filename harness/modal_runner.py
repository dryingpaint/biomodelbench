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

APP_NAME = "biomodelbench"
VOL_NAME = "biomodelbench-tasks"
VOL_MOUNT = Path("/vol")
REPO_ROOT = Path(__file__).resolve().parent.parent

# Shared container image. Kept inline so Modal doesn't have to ship the
# harness package to workers — the image spec is one flat file.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "curl", "git", "nodejs", "npm", "ripgrep", "jq", "ca-certificates",
        "tabix", "bcftools", "wget",
    )
    .pip_install(
        "torch==2.3.0",
        "transformers==4.41.2",
        "scikit-learn>=1.4",
        "pandas>=2",
        "pyarrow>=14",
        "numpy>=1.26",
        "peft>=0.11",
        "xgboost>=2.0",
        "lightgbm>=4.3",
        "tqdm",
        "requests",
        "matplotlib",
        "pyBigWig>=0.3",
        "pysam>=0.22",
        "biopython>=1.83",
    )
    .run_commands("npm install -g @anthropic-ai/claude-code")
)

app = modal.App(APP_NAME, image=image)
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

SNAPSHOT_INTERVAL_SECONDS = 300  # commit workdir → volume every 5 min


@app.function(
    gpu="A10G",
    timeout=36000,  # 10h container lifetime.
    memory=98304,  # 96 GB — headroom for loading multi-GB bigWigs + FMs in-process.
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
    import signal
    import threading

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
    runs_dst = VOL_MOUNT / "runs" / task / run_id
    runs_dst.mkdir(parents=True, exist_ok=True)

    def _snapshot_to_volume() -> int:
        """Copy workdir → runs_dst (skipping bundle inputs), commit. Return file count.

        We deliberately skip files that were part of the input bundle (train.parquet,
        test.parquet, prompt.md, etc.) so we don't recopy them into the runs dir.
        """
        bundle_relpaths = {str(p.relative_to(src)) for p in src.rglob("*") if p.is_file()}
        n = 0
        for path in sorted(workdir.rglob("*")):
            if not path.is_file():
                continue
            rel = str(path.relative_to(workdir))
            if rel in bundle_relpaths:
                continue
            target = runs_dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                data = path.read_bytes()
            except OSError:
                continue
            # Skip write if unchanged (avoids churn on the volume).
            if target.exists() and target.stat().st_size == len(data):
                try:
                    if target.read_bytes() == data:
                        n += 1
                        continue
                except OSError:
                    pass
            target.write_bytes(data)
            n += 1
        volume.commit()
        return n

    stop_snapshot = threading.Event()

    def _snapshot_loop():
        while not stop_snapshot.wait(SNAPSHOT_INTERVAL_SECONDS):
            try:
                n = _snapshot_to_volume()
                print(f"[snapshot] {n} files committed to volume at t={time.time() - t0:.0f}s", flush=True)
            except Exception as e:
                print(f"[snapshot] failed: {e}", flush=True)

    # Emergency commit on SIGTERM (Modal sends this on cancellation).
    def _handle_sigterm(signum, frame):
        print(f"[signal] received SIGTERM, snapshotting before shutdown", flush=True)
        try:
            _snapshot_to_volume()
        except Exception as e:
            print(f"[signal] snapshot failed: {e}", flush=True)

    try:
        signal.signal(signal.SIGTERM, _handle_sigterm)
    except (ValueError, OSError):
        # SIGTERM handler only settable on the main thread. If we're not,
        # skip — the periodic snapshot loop is still active.
        pass

    t0 = time.time()
    snapshot_thread = threading.Thread(target=_snapshot_loop, daemon=True)
    snapshot_thread.start()

    # We loop claude sessions until the wall clock is close to expiring. If
    # the agent exits early, we relaunch with a continuation prompt urging it
    # to keep iterating. Quick consecutive exits (< 2 min) signal the agent
    # genuinely has nothing more to do — we stop after a few of those.
    MIN_REMAINING_FOR_RELAUNCH = 900  # 15 min buffer for final artifact commit / grade
    QUICK_EXIT_THRESHOLD = 120  # <2 min = "nothing left to do"
    MAX_CONSECUTIVE_QUICK_EXITS = 3

    session_num = 0
    consecutive_quick_exits = 0
    exit_reason = "completed"
    last_returncode = 0
    while True:
        elapsed = time.time() - t0
        remaining = wall_clock_seconds - elapsed
        if remaining < MIN_REMAINING_FOR_RELAUNCH:
            print(f"[loop] {remaining:.0f}s remaining < {MIN_REMAINING_FOR_RELAUNCH}s buffer; stopping loop", flush=True)
            exit_reason = "wall_clock"
            break
        if consecutive_quick_exits >= MAX_CONSECUTIVE_QUICK_EXITS:
            print(f"[loop] {consecutive_quick_exits} consecutive quick exits; agent appears done", flush=True)
            exit_reason = "agent_done"
            break

        session_num += 1
        if session_num == 1:
            cmd = agent_command
        else:
            answer_present = (workdir / "answer.parquet").exists()
            method_present = (workdir / "method.md").exists()
            remain_min = int(remaining / 60)
            continuation = (
                f"Continue improving your BioModelBench submission. This is a "
                f"long-horizon run: you have approximately {remain_min} minutes "
                f"remaining out of a {int(wall_clock_seconds/60)} minute total "
                f"budget. Do NOT stop early.\n\n"
                f"Current state of /task:\n"
                f"- answer.parquet: {'present' if answer_present else 'MISSING — first priority'}\n"
                f"- method.md: {'present' if method_present else 'missing'}\n"
                f"- Any scripts / logs / features files you wrote in the previous "
                f"session are still on disk. Read method.md and training_manifest.json "
                f"to understand what you already did.\n\n"
                f"Directives:\n"
                f"1. If answer.parquet is missing, produce it before anything else.\n"
                f"2. If it exists, keep iterating: try feature families you haven't "
                f"used yet, train a complementary model type (e.g. add LightGBM if you "
                f"only have logistic regression, or vice versa), ensemble with rank "
                f"averaging, or diagnose which variants are most uncertain and target "
                f"them. Overwrite answer.parquet, method.md, and training_manifest.json "
                f"as you improve.\n"
                f"3. Do not stop until you have genuinely exhausted useful directions. "
                f"Use the full remaining time.\n"
                f"4. The blacklist and anti-leak rules from the original prompt still "
                f"apply. Re-read /task/prompt.md if unsure."
            )
            # Pass the continuation through a file to avoid shell-quoting hazards.
            cont_path = workdir / f".continuation_{session_num}.md"
            cont_path.write_text(continuation)
            cmd = (
                'claude --dangerously-skip-permissions --print '
                '--output-format stream-json --verbose '
                f'"$(cat {cont_path.name})"'
            )
            print(f"[loop] session {session_num} — continuation prompt written to {cont_path.name}", flush=True)

        # Cap this session's wait so we can still relaunch within remaining budget.
        session_wait = max(60, min(int(remaining), wall_clock_seconds))
        s0 = time.time()
        print(f"[loop] session {session_num} launching (remaining={remaining:.0f}s)", flush=True)
        with open(log_path, "ab") as log_f, open(stderr_path, "ab") as err_f:
            proc = subprocess.Popen(
                cmd, shell=True, cwd=str(workdir), stdout=log_f, stderr=err_f,
            )
            try:
                proc.wait(timeout=session_wait)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
        session_dur = time.time() - s0
        last_returncode = proc.returncode
        print(f"[loop] session {session_num} exited rc={last_returncode} in {session_dur:.0f}s", flush=True)

        if session_dur < QUICK_EXIT_THRESHOLD:
            consecutive_quick_exits += 1
            print(f"[loop] quick exit #{consecutive_quick_exits}/{MAX_CONSECUTIVE_QUICK_EXITS}", flush=True)
        else:
            consecutive_quick_exits = 0

        # Give any background jobs the agent kicked off (e.g., long-running
        # feature-extraction scripts) a chance to finish before we relaunch.
        # If answer.parquet has grown or been created in the last 60s, wait
        # a bit more before starting a new session.
        answer_p = workdir / "answer.parquet"
        wait_grace = 0
        while wait_grace < 300:
            if answer_p.exists():
                age = time.time() - answer_p.stat().st_mtime
                if age < 60:
                    time.sleep(30)
                    wait_grace += 30
                    continue
            break

    duration = time.time() - t0
    stop_snapshot.set()
    snapshot_thread.join(timeout=10)

    # Final full snapshot at end. Uses the same helper.
    artifacts_count = _snapshot_to_volume()
    artifacts: dict[str, bytes] = {}
    for path in sorted(runs_dst.rglob("*")):
        if path.is_file():
            try:
                artifacts[str(path.relative_to(runs_dst))] = path.read_bytes()
            except OSError:
                continue

    def _tail(p: Path, n: int = 4000) -> str:
        try:
            b = p.read_bytes()
        except OSError:
            return ""
        return b[-n:].decode("utf-8", errors="replace")

    # Parse the agent log's final `result` event for cost / turns / model.
    meta: dict = {}
    try:
        import json as _json
        for line in reversed(log_path.read_bytes().decode("utf-8", errors="replace").splitlines()):
            if not line.strip():
                continue
            try:
                evt = _json.loads(line)
            except Exception:
                continue
            if evt.get("type") == "result":
                usage_by_model = evt.get("modelUsage") or {}
                primary_model = None
                if usage_by_model:
                    # Pick the model with the most output tokens as the primary
                    primary_model = max(
                        usage_by_model.items(),
                        key=lambda kv: kv[1].get("outputTokens", 0),
                    )[0]
                meta = {
                    "primary_model": primary_model,
                    "models_used": sorted(usage_by_model.keys()),
                    "total_cost_usd": evt.get("total_cost_usd"),
                    "num_turns": evt.get("num_turns"),
                    "duration_ms": evt.get("duration_ms"),
                    "duration_api_ms": evt.get("duration_api_ms"),
                    "terminal_reason": evt.get("terminal_reason"),
                    "session_id": evt.get("session_id"),
                }
                break
    except Exception:
        pass
    if meta:
        (runs_dst / "run_meta.json").write_text(json.dumps(meta, indent=2))
        (workdir / "run_meta.json").write_text(json.dumps(meta, indent=2))
        volume.commit()

    return {
        "returncode": last_returncode,
        "duration_seconds": round(duration, 2),
        "sessions": session_num,
        "exit_reason": exit_reason,
        "n_artifacts": len(artifacts),
        "stdout_tail": _tail(log_path),
        "stderr_tail": _tail(stderr_path),
        "runs_path": str(runs_dst),
        "meta": meta,
    }


def _run_grade(task: str, out_dir: Path, task_dir: Path, answer_filename: str) -> None:
    grade_script = task_dir / "grade.py"
    answer = out_dir / answer_filename
    if not answer.exists():
        print(f"[{task}] no {answer_filename} in {out_dir}; skipping grade")
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


def _download_and_write(task: str, run_id: str, task_dir: Path) -> Path:
    """Pull run artifacts from the volume into the local runs/<run_id>/ dir."""
    files = _download_impl.remote(task, run_id)
    out_dir = task_dir / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    for rel, blob in files.items():
        p = out_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)
    print(f"[{task}] wrote {len(files)} artifacts to {out_dir}")
    return out_dir


@app.local_entrypoint()
def launch(
    task: str,
    run_id: str = "",
    agent_command: str = AGENT_COMMAND_DEFAULT,
    wall_clock_seconds: int = 35600,
    skip_grade: bool = False,
    answer_filename: str = "answer.parquet",
):
    """Run one agent attempt, sync artifacts, invoke the task's grade.py.

    Resilient to Modal client-side ConnectionError: even if the .remote()
    poll drops, the run keeps going on Modal thanks to periodic mid-run
    snapshots inside _run_one. Once the run finishes (or is cancelled), the
    `retrieve` entrypoint can pull whatever's on the volume.
    """
    task_dir = _task_dir(task)
    _task_bundle(task)  # sanity check: bundle exists

    if not run_id:
        run_id = time.strftime("%Y%m%dT%H%M%S")
    print(f"[{task}] launching run_id={run_id} (wall_clock ≤ {wall_clock_seconds}s)")

    result: dict = {}
    try:
        result = _run_one.remote(task, run_id, agent_command, wall_clock_seconds)
        print(
            f"[{task}] rc={result.get('returncode')} "
            f"duration={result.get('duration_seconds')}s artifacts={result.get('n_artifacts')}"
        )
    except Exception as exc:
        # Modal client can raise ConnectionError, InternalFailure, or
        # RemoteError on cancellation. The remote run may or may not have
        # completed; either way, try to salvage whatever's on the volume.
        print(f"[{task}] .remote() raised {type(exc).__name__}: {exc}")
        print(f"[{task}] falling through to volume retrieval for run_id={run_id}")

    try:
        out_dir = _download_and_write(task, run_id, task_dir)
    except Exception as exc:
        print(f"[{task}] volume retrieval failed: {exc}")
        print(f"[{task}] you can retry with:")
        print(f"  uv run modal run harness/modal_runner.py::retrieve --task {task} --run-id {run_id}")
        return

    (out_dir / "run_summary.json").write_text(json.dumps({
        "task": task,
        "run_id": run_id,
        "returncode": result.get("returncode"),
        "duration_seconds": result.get("duration_seconds"),
        "stdout_tail": result.get("stdout_tail"),
        "stderr_tail": result.get("stderr_tail"),
        "n_artifacts": result.get("n_artifacts"),
    }, indent=2))

    if not skip_grade:
        _run_grade(task, out_dir, task_dir, answer_filename)


@app.local_entrypoint()
def retrieve(
    task: str,
    run_id: str,
    skip_grade: bool = False,
    answer_filename: str = "answer.parquet",
):
    """Pull a specific run's artifacts from the volume and optionally re-grade.

    Use this if launch()'s in-band retrieval failed but the run itself may
    have completed (or snapshotted mid-run) — the periodic snapshot loop in
    _run_one commits every 5 minutes, so a killed run usually has salvageable
    artifacts on the volume.
    """
    task_dir = _task_dir(task)
    out_dir = _download_and_write(task, run_id, task_dir)
    if not skip_grade:
        _run_grade(task, out_dir, task_dir, answer_filename)
