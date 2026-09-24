"""Read-only Ouroboros package and single-surface ZCode inspection."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import stat
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PYPI_URL = "https://pypi.org/pypi/ouroboros-ai/json"
SUPPORTED_RANGE = ">=0.51.1"

# Use the selected CLI's native asset resolver, not an Aquarium-owned skill list.
ASSET_PROBE = """
import hashlib, json
from importlib.metadata import version
from ouroboros.codex.artifacts import resolve_packaged_codex_assets, load_packaged_codex_rules
result = {"version": version("ouroboros-ai"), "artifacts": {}}
with resolve_packaged_codex_assets() as assets:
    for artifact in assets.managed_artifacts:
        source = artifact.source_path
        if source.is_symlink():
            raise ValueError("symlinked package asset")
        target = artifact.relative_install_path.as_posix()
        files = sorted(source.rglob("*")) if source.is_dir() else [source]
        for path in files:
            if path.is_symlink():
                raise ValueError("symlinked package asset")
            if path.is_file():
                relative = target + "/" + path.relative_to(source).as_posix() if source.is_dir() else target
                contents = load_packaged_codex_rules().encode("utf-8") if path == assets.rules_path else path.read_bytes()
                result["artifacts"][relative] = hashlib.sha256(contents).hexdigest()
print(json.dumps(result))
"""


class InvalidCodexHome(ValueError):
    """An explicitly supplied home cannot be used as an installation target."""


def release_freshness(
    inspector: Any, cli: dict[str, Any], timeout: float
) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "freshness_unverifiable", "source": PYPI_URL}
    try:
        with urllib.request.urlopen(PYPI_URL, timeout=timeout) as response:
            if response.geturl() != PYPI_URL:
                raise ValueError("unexpected metadata source")
            payload = response.read(8 * 1024 * 1024 + 1)
        if len(payload) > 8 * 1024 * 1024:
            raise ValueError("metadata too large")
        metadata = json.loads(payload)
        if metadata["info"]["name"] != "ouroboros-ai":
            raise ValueError("unexpected package")
        releases = [
            version
            for version, files in metadata["releases"].items()
            if re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version)
            and any(file.get("yanked") is False for file in files)
        ]
        key = lambda version: tuple(map(int, version.split(".")))
        latest = max(releases, key=key)
        supported = max(
            filter(inspector.supported_ouroboros_version, releases),
            key=key,
            default=None,
        )
        result.update(
            latest_stable=latest,
            latest_supported=supported,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
        installed = cli["version"]
        if not cli["installed"]:
            result["status"] = "missing"
        elif not cli["probes"]["version"]["ok"] or installed is None:
            result["reason"] = "cli_version_unverifiable"
        elif not inspector.supported_ouroboros_version(installed):
            result["status"] = "incompatible"
        elif supported is not None and key(installed) < key(supported):
            result["status"] = "update_available"
        else:
            result["status"] = "current" if installed in releases else "different"
    except (
        OSError,
        http.client.HTTPException,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ):
        result["reason"] = "release_metadata_unverifiable"
    return result


def packaged_assets(
    inspector: Any, cli: dict[str, Any], cwd: Path, timeout: float
) -> dict[str, str] | None:
    if not cli.get("installed") or not cli.get("version_supported"):
        return None
    # uv tool installations keep the package interpreter beside the CLI entrypoint.
    interpreter = Path(cli["executable"]).parent / "python"
    if not interpreter.is_file():
        return None
    probe = inspector.json_probe(
        [str(interpreter), "-I", "-c", ASSET_PROBE], cwd, timeout
    )
    result = probe.get("result")
    if (
        not probe["ok"]
        or not isinstance(result, dict)
        or result.get("version") != cli["version"]
    ):
        return None
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        return None
    for relative, digest in artifacts.items():
        if not isinstance(relative, str) or not isinstance(digest, str):
            return None
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or len(path.parts) < 2:
            return None
        if path.parts[0] not in {"rules", "skills"} or not path.parts[1].startswith(
            "ouroboros"
        ):
            return None
        if re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            return None
    if not all(
        any(name.startswith(kind + "/") for name in artifacts)
        for kind in ("rules", "skills")
    ):
        return None
    return artifacts


def legacy_skills(expected: dict[str, str] | None) -> list[str]:
    root = Path.home() / ".agents" / "skills"
    candidates: set[Path] = set()
    if expected:
        for relative, digest in expected.items():
            parts = Path(relative).parts
            if len(parts) == 3 and parts[0] == "skills" and parts[2] == "SKILL.md":
                prefixed = root / parts[1]
                if prefixed.exists() or prefixed.is_symlink():
                    candidates.add(prefixed)
                # Recognize unprefixed legacy copies only by exact upstream bytes.
                candidate = root / parts[1].removeprefix("ouroboros-")
                try:
                    if (
                        hashlib.sha256(
                            (candidate / "SKILL.md").read_bytes()
                        ).hexdigest()
                        == digest
                    ):
                        candidates.add(candidate)
                except OSError:
                    pass
    return sorted(str(path) for path in candidates)


def shared_skill_conflicts(
    inspector: Any, expected: dict[str, str] | None, legacy: list[str]
) -> list[str]:
    if expected is None:
        return []
    root = Path.home() / ".agents" / "skills"
    conflicts: set[str] = set()
    for relative in expected:
        parts = Path(relative).parts
        if len(parts) != 3 or parts[0] != "skills" or parts[2] != "SKILL.md":
            continue
        name = parts[1].removeprefix("ouroboros-")
        candidate = root / name
        if str(candidate) in legacy:
            continue
        try:
            skill = candidate / "SKILL.md"
            if (
                candidate.is_symlink()
                or skill.is_symlink()
                or (skill.is_file() and inspector.frontmatter_name(skill) == name)
            ):
                conflicts.add(str(candidate))
        except OSError:
            conflicts.add(str(candidate))
    return sorted(conflicts)


def inspect_ouroboros(
    inspector: Any,
    cwd: Path,
    timeout: float,
    explicit_homes: tuple[str, ...] = (),
    verify_release: bool = False,
) -> dict[str, Any]:
    # ZCode has one Ouroboros integration surface: the user-global
    # `mcp.servers` entry of `~/.zcode/cli/config.json` and the
    # `~/.ouroboros/config.yaml` runtime config `ooo setup --runtime zcode`
    # manages. Upstream's per-Codex-home rules and skills have no ZCode
    # equivalent, so the discovered-home rows collapse into the single
    # registration the project inspector resolves. Explicitly supplied
    # extra homes name that other host's layout; they are reported as not
    # applicable rather than silently filtered. Upstream v0.1.17 adds
    # `shared_skill_conflicts` — a shared-root directory whose frontmatter
    # names a packaged skill without matching its bytes. Upstream treats
    # every shared-root copy as legacy because Codex homes own the
    # integration there; on this host the shared root is the canonical
    # skill target, so byte-matching copies stay readiness evidence and
    # only the non-matching name conflicts degrade.
    cli = inspector.inspect_ouroboros_cli(cwd, timeout)
    integration = inspector.inspect_ouroboros(cwd, timeout)
    assets = packaged_assets(inspector, cli, cwd, timeout)
    shared_skills = legacy_skills(assets)
    shared_conflicts = shared_skill_conflicts(inspector, assets, shared_skills)
    status = "missing" if not cli["installed"] else integration["status"]
    reason = None
    if shared_conflicts and status == "configured":
        status = "degraded"
        reason = "shared_skill_conflict"
    result = {
        "status": status,
        "supported_range": SUPPORTED_RANGE,
        "cli": {
            **{
                key: cli[key]
                for key in ("installed", "executable", "version", "version_supported")
            },
            "status": "missing"
            if not cli["installed"]
            else "installed"
            if cli["version_supported"]
            else "degraded",
            "version_probe": cli["probes"]["version"],
        },
        "integration": {
            key: integration[key]
            for key in (
                "host_integration",
                "mcp_registration",
                "mcp_runtime",
                "runtime_package",
            )
        },
        "extra_homes": {
            "status": "not_applicable",
            "reason": "no_per_home_integration_on_zcode",
            "requested": list(explicit_homes),
        },
        "freshness": (
            release_freshness(inspector, cli, timeout)
            if verify_release
            else {"status": "not_checked", "source": PYPI_URL}
        ),
        "shared_root_skills": shared_skills,
        "shared_skill_conflicts": shared_conflicts,
    }
    if reason is not None:
        result["reason"] = reason
    return result
