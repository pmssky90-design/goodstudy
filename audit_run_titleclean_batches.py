from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "candidate_output_titleclean_recovery"
LIST_FILE = ROOT / "intermediate" / "titleclean-audit-file-list.txt"
HASH_FILE = ROOT / "intermediate" / "titleclean-audit-file-list.sha256"
STATE_FILE = ROOT / "intermediate" / "titleclean-audit-batch-state.json"
BATCH_DIR = ROOT / "audit" / "titleclean_batches"
BATCH_SCRIPT = ROOT / "audit_audit_titleclean_batch.py"
MERGE_SCRIPT = ROOT / "audit_merge_titleclean_audit.py"
BATCH_SIZE = 2000
RULE_VERSION = "titleclean-batch-v1"


def atomic_json(path: Path, value: object) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def current_paths() -> list[str]:
    return sorted((p.relative_to(TARGET).as_posix() for p in TARGET.rglob("index.html")))


def payload(paths: list[str]) -> tuple[str, str]:
    text = "".join(path + "\n" for path in paths)
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def valid_batch(index: int, expected: int, digest: str) -> bool:
    path = BATCH_DIR / f"batch-{index:04d}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return (
            value.get("status") == "complete"
            and value.get("processed_count") == expected
            and value.get("file_list_hash") == digest
            and value.get("rule_version") == RULE_VERSION
        )
    except Exception:
        return False


def main() -> int:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    paths = current_paths()
    text, digest = payload(paths)
    if LIST_FILE.exists() or HASH_FILE.exists():
        old_text = LIST_FILE.read_text(encoding="utf-8") if LIST_FILE.exists() else ""
        old_hash = HASH_FILE.read_text(encoding="ascii").strip() if HASH_FILE.exists() else ""
        if old_text != text or old_hash != digest:
            raise SystemExit("ERROR: target file list changed; existing batch results must not be reused")
    else:
        for path, data, encoding in ((LIST_FILE, text, "utf-8"), (HASH_FILE, digest + "\n", "ascii")):
            temp = path.with_suffix(path.suffix + ".tmp")
            with temp.open("w", encoding=encoding, newline="\n") as handle:
                handle.write(data); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, path)
    total_batches = math.ceil(len(paths) / BATCH_SIZE)
    state = {
        "total_files": len(paths), "batch_size": BATCH_SIZE, "total_batches": total_batches,
        "completed_batches": [], "failed_batches": [], "last_relative_path": "",
        "file_list_hash": digest, "rule_version": RULE_VERSION,
        "started_at": datetime.now().astimezone().isoformat(), "last_completed_at": None,
    }
    if STATE_FILE.exists():
        try:
            prior = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if prior.get("file_list_hash") == digest and prior.get("rule_version") == RULE_VERSION:
                state["started_at"] = prior.get("started_at") or state["started_at"]
        except Exception:
            pass
    for index in range(1, total_batches + 1):
        expected = min(BATCH_SIZE, len(paths) - (index - 1) * BATCH_SIZE)
        if valid_batch(index, expected, digest):
            state["completed_batches"].append(index)
            result = json.loads((BATCH_DIR / f"batch-{index:04d}.json").read_text(encoding="utf-8"))
            state["last_relative_path"] = result["last_relative_path"]
            atomic_json(STATE_FILE, state)
            continue
        name = f"batch-{index:04d}"
        success = False
        for attempt in (1, 2):
            with (BATCH_DIR / f"{name}.stdout.log").open("a", encoding="utf-8") as out, \
                 (BATCH_DIR / f"{name}.stderr.log").open("a", encoding="utf-8") as err:
                out.write(f"\nATTEMPT {attempt} {datetime.now().astimezone().isoformat()}\n"); out.flush()
                try:
                    run = subprocess.run(
                        [sys.executable, str(BATCH_SCRIPT), "--batch-index", str(index), "--batch-size", str(BATCH_SIZE)],
                        cwd=ROOT, stdout=out, stderr=err, timeout=900,
                    )
                    code = run.returncode
                except subprocess.TimeoutExpired:
                    code = -999
                    err.write("batch timeout after 900 seconds\n"); err.flush()
            if code == 0 and valid_batch(index, expected, digest):
                success = True
                break
        if not success:
            state["failed_batches"] = [index]
            state["last_exit_code"] = code
            atomic_json(STATE_FILE, state)
            return 1
        state["completed_batches"].append(index)
        result = json.loads((BATCH_DIR / f"{name}.json").read_text(encoding="utf-8"))
        state["last_relative_path"] = result["last_relative_path"]
        state["last_completed_at"] = datetime.now().astimezone().isoformat()
        atomic_json(STATE_FILE, state)
    merge = subprocess.run([sys.executable, str(MERGE_SCRIPT)], cwd=ROOT)
    return merge.returncode


if __name__ == "__main__":
    sys.exit(main())
