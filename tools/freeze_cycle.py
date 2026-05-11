import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "backend" / "experiments" / "outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def run_command(command: list[str]) -> None:
    print(f"> {' '.join(command)}")
    subprocess.run(command, cwd=ROOT, check=True)


def get_command_output(command: list[str]) -> str:
    return subprocess.check_output(command, cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()


def main() -> None:
    run_command(["docker", "compose", "up", "-d"])
    run_command(["docker", "compose", "exec", "backend", "alembic", "upgrade", "head"])
    run_command(["docker", "compose", "exec", "backend", "python", "-m", "scripts.ingest_openchargemap"])
    run_command(["docker", "compose", "exec", "backend", "pytest", "-q"])
    run_command(["docker", "compose", "exec", "backend", "python", "-m", "experiments.run_experiments"])
    run_command(["docker", "compose", "exec", "backend", "python", "-m", "experiments.analyse_results"])

    git_sha = "unknown"
    git_short_sha = "unknown"
    git_branch = "unknown"
    git_dirty = "unknown"
    try:
        git_sha = get_command_output(["git", "rev-parse", "HEAD"])
        git_short_sha = get_command_output(["git", "rev-parse", "--short", "HEAD"])
        git_branch = get_command_output(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        git_dirty = "dirty" if get_command_output(["git", "status", "--porcelain"]) else "clean"
    except Exception:
        pass

    metadata = {
        "run_timestamp_utc": datetime.now(UTC).isoformat(),
        "git_commit": git_sha,
        "git_commit_short": git_short_sha,
        "git_branch": git_branch,
        "git_worktree_state": git_dirty,
        "host_platform": platform.platform(),
        "python_version": platform.python_version(),
        "dataset_source": "cached_openchargemap_sample",
        "random_seed": 42,
        "experiment_trials_per_scenario": 100,
        "steps": [
            "docker compose up -d",
            "alembic upgrade head",
            "python -m scripts.ingest_openchargemap",
            "pytest -q",
            "python -m experiments.run_experiments",
            "python -m experiments.analyse_results",
        ],
    }
    (OUT_DIR / "freeze_run_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Saved metadata: {OUT_DIR / 'freeze_run_metadata.json'}")


if __name__ == "__main__":
    main()
