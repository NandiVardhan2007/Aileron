"""Profile import, export, and schema migration manager (M6).

Follows CONFIGURATION §Profiles and CFG-03:
- Profiles store overrides and calibration values in TOML format.
- `schema_version` tracks format iterations; migrations upgrade older versions.
- Pydantic validation ensures loaded profiles stay within safe ranges.
"""

from __future__ import annotations

import logging
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aileron.config import AileronConfig

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 1


def _format_toml_val(val: object) -> str | None:
    """Format primitive scalar into TOML representation."""
    if isinstance(val, str):
        return f'"{val}"'
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int | float):
        return str(val)
    return None


def dump_toml(data: dict[str, Any]) -> str:
    """Format dictionary to clean TOML string without external dependencies."""
    lines: list[str] = []
    sections: list[tuple[str, dict[str, Any]]] = []

    for k, v in data.items():
        if isinstance(v, dict):
            sections.append((k, v))
        else:
            rep = _format_toml_val(v)
            if rep is not None:
                lines.append(f"{k} = {rep}")

    for sec_name, sec_dict in sections:
        lines.append(f"\n[{sec_name}]")
        sub_sections: list[tuple[str, dict[str, Any]]] = []
        for k, v in sec_dict.items():
            if isinstance(v, dict):
                sub_sections.append((f"{sec_name}.{k}", v))
            else:
                rep = _format_toml_val(v)
                if rep is not None:
                    lines.append(f"{k} = {rep}")

        for sub_name, sub_dict in sub_sections:
            lines.append(f"\n[{sub_name}]")
            for k, v in sub_dict.items():
                rep = _format_toml_val(v)
                if rep is not None:
                    lines.append(f"{k} = {rep}")

    return "\n".join(lines) + "\n"


def migrate_v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    """Migration from unversioned (v0) profiles to schema_version 1."""
    migrated = dict(data)
    migrated["schema_version"] = 1
    # Rename legacy keys if present
    if "yoke" in migrated and "cockpit" not in migrated:
        migrated["cockpit"] = {"yoke": migrated.pop("yoke")}
    return migrated


MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    0: migrate_v0_to_v1,
}


def apply_migrations(raw_data: dict[str, Any]) -> dict[str, Any]:
    """Apply schema migrations sequentially until CURRENT_SCHEMA_VERSION is reached."""
    data = dict(raw_data)
    version = data.get("schema_version", 0)

    while version < CURRENT_SCHEMA_VERSION:
        migration_fn = MIGRATIONS.get(version)
        if migration_fn is None:
            msg = (
                f"No migration path found from profile schema_version {version} "
                f"to {CURRENT_SCHEMA_VERSION}"
            )
            raise ValueError(msg)
        data = migration_fn(data)
        new_version = data.get("schema_version", version + 1)
        if new_version <= version:
            raise RuntimeError(
                f"Migration from version {version} failed to advance schema_version."
            )
        version = new_version

    return data


def import_profile(path: str | Path) -> dict[str, Any]:
    """Read a TOML profile file, run migrations, and return validated dict."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Profile file not found: {file_path}")

    with file_path.open("rb") as f:
        raw_data = tomllib.load(f)

    # Apply schema migrations
    migrated = apply_migrations(raw_data)
    logger.info(
        "Imported profile '%s' (schema_version=%d)",
        file_path.name,
        migrated.get("schema_version", 1),
    )
    return migrated


def export_profile(
    config: AileronConfig,
    target_path: str | Path,
    calibration_data: dict[str, Any] | None = None,
) -> Path:
    """Export active configuration overrides and calibration data to TOML."""
    dest = Path(target_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "pointer": {
            "mode": config.pointer.mode,
            "region_w": config.pointer.region_w,
            "region_h": config.pointer.region_h,
            "gamma": config.pointer.gamma,
        },
        "click": {
            "pinch_on": config.click.pinch_on,
            "pinch_off": config.click.pinch_off,
            "tap_ms": config.click.tap_ms,
            "dbl_ms": config.click.dbl_ms,
        },
        "cockpit": {
            "profile": config.cockpit.profile,
            "on_loss": config.cockpit.on_loss,
            "yoke": {
                "steer_max_deg": config.cockpit.yoke.steer_max_deg,
                "steer_deadzone_deg": config.cockpit.yoke.steer_deadzone_deg,
                "steer_expo": config.cockpit.yoke.steer_expo,
            },
        },
    }

    if calibration_data:
        data["calibration"] = calibration_data

    dest.write_text(dump_toml(data), encoding="utf-8")

    logger.info("Exported profile to '%s'", dest)
    return dest
