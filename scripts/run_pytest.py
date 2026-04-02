from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from _pytest import pathlib as pytest_pathlib


ROOT = Path(__file__).resolve().parents[1]


def _disable_dead_symlink_cleanup() -> None:
    pytest_pathlib.cleanup_dead_symlinks = lambda _root: None


def _configure_tempdir() -> None:
    temp_root = ROOT / ".codex-tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    os.environ["TMP"] = str(temp_root)
    os.environ["TEMP"] = str(temp_root)
    os.environ["TMPDIR"] = str(temp_root)


def main() -> int:
    _disable_dead_symlink_cleanup()
    _configure_tempdir()
    args = sys.argv[1:]
    if "cacheprovider" not in " ".join(args):
        args = ["-p", "no:cacheprovider", *args]
    return pytest.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
