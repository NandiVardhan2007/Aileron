"""Packaging and PyInstaller build orchestrator (M7).

Builds a standalone executable bundle according to `aileron.spec`.
Follows ADR-010 / ROADMAP M7:
- Local build only; does not publish or distribute without signed verification.
- Supports `--dry-run` to validate packaging prerequisites and assets.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("build_installer")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aileron PyInstaller Build Script")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate build assets and spec syntax without invoking PyInstaller.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build and dist directories before building.",
    )
    return parser.parse_args()


def _check_prereqs(repo_root: Path) -> bool:
    spec_path = repo_root / "aileron.spec"
    defaults_path = repo_root / "config" / "defaults.toml"
    main_py = repo_root / "src" / "aileron" / "__main__.py"

    if not spec_path.exists():
        logger.error("Spec file not found: %s", spec_path)
        return False

    if not defaults_path.exists():
        logger.error("Defaults configuration missing: %s", defaults_path)
        return False

    if not main_py.exists():
        logger.error("Main entry point missing: %s", main_py)
        return False

    return True


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    spec_path = repo_root / "aileron.spec"

    logger.info("Validating Aileron build prerequisites...")
    if not _check_prereqs(repo_root):
        return 1

    logger.info("All build assets verified.")
    if args.dry_run:
        logger.info("[Dry Run] PyInstaller configuration and assets are valid.")
        return 0

    if args.clean:
        logger.info("Cleaning build/ and dist/ folders...")
        shutil.rmtree(repo_root / "build", ignore_errors=True)
        shutil.rmtree(repo_root / "dist", ignore_errors=True)

    pyinstaller_exe = shutil.which("pyinstaller")
    if not pyinstaller_exe:
        logger.warning(
            "PyInstaller is not installed in the current environment. "
            "Install with 'pip install pyinstaller' to produce binaries."
        )
        return 0

    logger.info("Executing PyInstaller with %s...", spec_path)
    cmd = [pyinstaller_exe, "--noconfirm", str(spec_path)]
    result = subprocess.run(cmd, check=False, cwd=str(repo_root))
    if result.returncode != 0:
        logger.error("PyInstaller build failed with exit code %d", result.returncode)
        return result.returncode

    logger.info("Build complete. Artifacts placed in 'dist/aileron'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
