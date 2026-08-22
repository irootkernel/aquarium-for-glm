#!/usr/bin/env python3
"""Generate the ZCode plugin from the pinned upstream Codex plugin.

The upstream repository at `upstream/` is the single source of truth. This
script performs a deterministic transformation into `plugins/aquarium/`,
committed so the plugin installs even when the submodule is absent.

Run `sync.py` to regenerate, or `sync.py --check` to fail on drift.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
UPSTREAM = REPOSITORY / "upstream"
UPSTREAM_PLUGIN = UPSTREAM / "plugins" / "aquarium"
OUTPUT = REPOSITORY / "plugins" / "aquarium"
OVERRIDES = REPOSITORY / "overrides"
OVERRIDE_MANIFEST = OVERRIDES / "manifest.json"
CODEX_EXEMPTIONS = OVERRIDES / "codex-exemptions.json"
SYNC_MANIFEST = "sync-manifest.json"

COPIED_DIRECTORIES = ("skills", "references", "assets", "hooks")
TEXT_SUFFIXES = (".md",)
SCRIPT_SUFFIXES = (".py",)
DATA_SUFFIXES = (".json",)
# Everything copied that host-specific text could hide in. `.yaml` is scanned but
# never rewritten: the Podway procedure IDs are load-bearing identifiers, and the
# integration contract requires the installed copies to match these bytes.
SCANNED_SUFFIXES = TEXT_SUFFIXES + SCRIPT_SUFFIXES + DATA_SUFFIXES + (".yaml",)

# Ordered literal substitutions applied to copied Markdown. Order matters: a
# later rule must never rewrite text that an earlier rule already produced.
#
# ZCode resolves skills through the Skill tool by qualified name
# `aquarium:<name>` (the short name is accepted as an alias), so prose names
# the `/aquarium:<name>` form. Ouroboros and Deslop install user-scoped under
# skill roots ZCode reads natively, where `~/.agents/skills` is one of them,
# so their invocations stay bare.
#
# `AGENTS.md` is deliberately absent: it is ZCode's native instruction file,
# and upstream wording about it stays correct here. `~/.agents/skills` is
# absent for the same reason.
SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("$aquarium:", "/aquarium:"),
    # `$use-podway`, `$use-sanho`, `$use-mulgae`, `$use-gaori`. A prefix rule
    # covers the family and any later sibling; `/use-` cannot re-match it.
    ("$use-", "/use-"),
    ("$lore-commits", "/lore-commits"),
    ("$lore-query", "/lore-query"),
    ("$orca-cli", "/orca-cli"),
    ("$interview", "/interview"),
    ("$deslop", "/deslop"),
    ("$seed", "/seed"),
    ("$pm", "/pm"),
    ("$qa", "/qa"),
    ("`request_user_input`", "`AskUserQuestion`"),
    # ZCode tracks work through its todo list, so the Codex goal maps onto it.
    ("Codex goal", "ZCode todo list"),
    ("a fresh Codex reviewer", "a fresh independent reviewer"),
    ("one fresh Codex reviewer", "one fresh independent reviewer"),
    ("supervised Codex reviewer", "supervised independent reviewer"),
    ("a fresh Codex in the current", "a fresh independent reviewer in the current"),
    ("fresh Codex audit", "fresh from-scratch audit"),
    ("direct Codex audit", "direct from-scratch audit"),
    (" for Codex.", " for ZCode."),
    # Ouroboros registers its skills with the host agent, so the component whose
    # health `dev-setup` establishes is the ZCode one here. The bundle skill
    # names the same component in a list of Ouroboros setup mutations.
    ("Codex skill health", "ZCode skill health"),
    (
        "Ouroboros package, Codex, and runtime components",
        "Ouroboros package, host integration, and runtime components",
    ),
    # Lora installs per host, so the catalog's scope wording moves. The
    # instruction-file text it could collide with is handled by overrides.
    ("Configure it for Codex user-global scope.", "Configure it for the ZCode user-global scope."),
    ("the Codex user-global skill directory", "the ZCode user-global skill directory"),
    # Singular form covers the plural; upstream has both "another Codex skill
    # root" and "Codex skill roots".
    ("Codex skill root", "ZCode skill root"),
    ("a new Codex user-scoped", "a new user-scoped"),
    (
        "restart Codex so a new session loads the skill snapshot",
        "restart ZCode so a new session loads the skill snapshot",
    ),
    (
        "restart Codex if the skill does not appear in the active session",
        "restart ZCode if the skill does not appear in the active session",
    ),
    ("will not load until Codex restarts", "will not load until ZCode restarts"),
)

# Substitutions for bundled scripts, kept separate from Markdown because they
# rewrite executable behavior rather than prose. Multi-line blocks use raw
# triple-single-quoted literals so backslashes and quotes match the upstream
# bytes exactly. Skill discovery narrows to the ZCode roots: this artifact
# diagnoses one host, and a copy sitting in another host's root is neither
# reachable here nor a duplicate of anything. ZCode exposes no config-dir
# environment variable, so the roots are literal. `~/.agents/skills` is a
# ZCode root natively, so it stays.
SCRIPT_SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    (
        r'''    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        candidates.append(Path(codex_home).expanduser().joinpath("skills"))
    candidates.extend(
        [Path.home().joinpath(".codex/skills"), Path.home().joinpath(".agents/skills")]
    )
''',
        r'''    # Only ZCode skill roots count here. A skill installed in
    # another host's root is not reachable from this one, and counting it
    # would report a cross-host copy as a duplicate installation and
    # degrade a diagnosis that is about this host.
    candidates.extend(
        [Path.home().joinpath(".zcode/skills"), Path.home().joinpath(".agents/skills")]
    )
''',
    ),
    # Upstream classifies the Ouroboros registration from a `codex mcp get`
    # JSON probe. ZCode has no `mcp` CLI subcommand, so the whole classifier
    # is replaced with one that reads the host's config files:
    # `~/.zcode/cli/config.json` (user level) and `.zcode/config.json`
    # (project level, which overrides the user entry on a name collision).
    (
        r'''def classify_ouroboros_registration(
    raw_probe: dict[str, Any],
) -> dict[str, Any]:
    probe = {
        key: raw_probe[key] for key in ("attempted", "ok", "exit_code", "timed_out")
    }
    if raw_probe["timed_out"]:
        probe["reason"] = "registration_probe_timed_out"
        return {"status": "degraded", "probe": probe}
    if raw_probe.get("error_code"):
        probe["error_code"] = raw_probe["error_code"]
        probe["reason"] = "registration_probe_failed"
        return {"status": "degraded", "probe": probe}

    stderr = raw_probe.get("stderr", "").strip()
    if not raw_probe["ok"]:
        not_found = re.fullmatch(
            r"(?:Error:\s*)?No MCP server named ['\"]?ouroboros['\"]? found\.?",
            stderr,
        )
        probe["reason"] = (
            "registration_not_found" if not_found else "registration_probe_failed"
        )
        return {
            "status": "missing" if not_found else "degraded",
            "probe": probe,
        }

    parsed = parse_json_probe(raw_probe)
    if parsed.get("error_code") == "invalid_json":
        probe["error_code"] = "invalid_json"
        probe["reason"] = "registration_invalid_json"
        return {"status": "degraded", "probe": probe}
    result = parsed.get("result")
    if not isinstance(result, dict):
        probe["reason"] = "registration_result_invalid"
        return {"status": "degraded", "probe": probe}
    if result.get("enabled") is True:
        return {"status": "configured", "probe": probe}
    if result.get("enabled") is False:
        probe["reason"] = "registration_disabled"
    elif "enabled" not in result:
        probe["reason"] = "registration_enabled_missing"
    else:
        probe["reason"] = "registration_enabled_invalid"
    return {"status": "degraded", "probe": probe}
''',
        r'''def ouroboros_mcp_registration(repository: Path) -> dict[str, Any]:
    # ZCode has no `mcp get` CLI probe; registrations live in
    # `~/.zcode/cli/config.json` (user level) and `.zcode/config.json`
    # (project level, which overrides the user entry on a name collision),
    # under the `mcp.servers` object. The entry resolving at all is the
    # registration signal; a disabled entry degrades rather than disappears.
    probe: dict[str, Any] = {
        "attempted": True,
        "ok": True,
        "exit_code": 0,
        "timed_out": False,
    }
    sources = [
        Path.home().joinpath(".zcode/cli/config.json"),
        repository.joinpath(".zcode/config.json"),
    ]
    entry: Any = None
    found = False
    for source in sources:
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, json.JSONDecodeError):
            probe["reason"] = "registration_invalid_json"
            return {"status": "degraded", "probe": probe}
        mcp = document.get("mcp") if isinstance(document, dict) else None
        servers = mcp.get("servers") if isinstance(mcp, dict) else None
        if isinstance(servers, dict) and "ouroboros" in servers:
            entry = servers["ouroboros"]
            found = True
    if not found:
        probe["reason"] = "registration_not_found"
        return {"status": "missing", "probe": probe}
    if isinstance(entry, dict) and entry.get("enabled") is False:
        probe["reason"] = "registration_disabled"
        return {"status": "degraded", "probe": probe}
    return {"status": "configured", "probe": probe}
''',
    ),
    # The Codex probe of the Ouroboros MCP registration moves to the config
    # reader above. On this host the integration consists of that entry plus
    # the user-scoped Ouroboros skills under the ZCode skill roots, so the
    # registration doubles as the host-integration signal.
    (
        r'''    codex = shutil.which("codex")
    if codex:
        registration_raw = run_command(
            [
                str(Path(codex).resolve()),
                "mcp",
                "get",
                "ouroboros",
                "--json",
            ],
            repository,
            timeout_seconds,
        )
        tool["mcp_registration"] = classify_ouroboros_registration(
            registration_raw
        )
    else:
        tool["mcp_registration"] = {
            "status": "unverifiable",
            "probe": skipped_probe("codex_executable_missing"),
        }
''',
        r'''    tool["mcp_registration"] = ouroboros_mcp_registration(repository)
    host_integration = {
        "status": tool["mcp_registration"]["status"],
        "probe": tool["mcp_registration"]["probe"],
    }
''',
    ),
    # `ooo codex doctor` verifies the Codex CLI's routing artifacts, and the
    # `ooo zcode` group ships no doctor command. The config registration
    # resolved above is the host-integration signal here.
    (
        r'''    codex_doctor = run_command(
        [tool["executable"], "codex", "doctor"], repository, timeout_seconds
    )
    tool["codex_integration"] = {
        "status": "configured" if codex_doctor["ok"] else "degraded",
        "probe": {
            key: codex_doctor[key]
            for key in ("attempted", "ok", "exit_code", "timed_out")
        },
    }
''',
        r'''    # `ooo codex doctor` verifies another host's routing artifacts and the
    # `ooo zcode` group ships no doctor command. The config registration
    # resolved above is the host-integration signal here, so it is recorded
    # rather than reprobed.
    tool["host_integration"] = host_integration
''',
    ),
    # The reported component is the host's own integration here, not Codex's.
    (
        r'''        tool["codex_integration"] = {
            "status": "missing",
            "probe": skipped_probe("executable_missing"),
        }
''',
        r'''        tool["host_integration"] = {
            "status": "missing",
            "probe": skipped_probe("executable_missing"),
        }
''',
    ),
    # ...and the readiness rollup reads the renamed component.
    (
        r'''        and tool["codex_integration"]["status"] == "configured"
''',
        r'''        and tool["host_integration"]["status"] == "configured"
''',
    ),
    # Upstream reads this component from the doctor's exit code. The MCP 2
    # server registered in config launches as a separate process while the
    # CLI environment keeps MCP 1.x, so the doctor's `mcp_import` check — and
    # the exit code with it — fails on a correctly configured machine. The
    # remaining checks carry runtime health here; the server's own health is
    # the registration component.
    (
        r'''    tool["mcp_runtime"] = {
        "status": "configured" if mcp_doctor["ok"] else "degraded",
        "probe": normalized_probe(mcp_doctor),
    }
''',
        r'''    doctor_checks = mcp_doctor.get("result")
    runtime_probe = normalized_probe(mcp_doctor)
    if isinstance(doctor_checks, list):
        failed = sorted(
            str(check.get("name"))
            for check in doctor_checks
            if isinstance(check, dict)
            and check.get("status") == "fail"
            and check.get("name") != "mcp_import"
        )
        if failed:
            runtime_probe["reason"] = "doctor_checks_failed"
        tool["mcp_runtime"] = {
            "status": "degraded" if failed else "configured",
            "failed_checks": failed,
            "probe": runtime_probe,
        }
    else:
        tool["mcp_runtime"] = {
            "status": "degraded",
            "probe": runtime_probe,
        }
''',
    ),
    # Upstream probes the Mulgae and Gaori MCP registrations through the Codex
    # CLI and treats them as project-local, verifying repository binding,
    # timeouts, and `required` flags from `codex mcp get` JSON. ZCode has no
    # `mcp` CLI, registrations are user-global in `~/.zcode/cli/config.json`,
    # and the host defines no per-server timeout fields, so the deep Codex
    # classification has no meaning here. Both probes collapse into one
    # config-reading classifier; a project `.zcode/config.json` entry of the
    # same name still overrides the user entry and is reported as the
    # effective scope.
    (
        r'''def inspect_mulgae_mcp(
    repository: Path, mulgae_executable: str | None, timeout_seconds: float
) -> dict[str, Any]:
    registration: dict[str, Any] = {
        "status": "missing",
        "project_config_present": repository.joinpath(".codex/config.toml").is_file(),
        "enabled": None,
        "stdio": None,
        "repository_bound": None,
        "arguments_match": None,
        "cwd_bound": None,
        "required": None,
        "required_verification": "unverifiable",
        "required_output_capability": "unknown",
        "compatibility_reason": None,
        "codex_version": None,
        "command_resolvable": None,
        "binary_matches_selected": None,
        "startup_timeout_sec": None,
        "tool_timeout_sec": None,
    }
    codex_executable = shutil.which("codex")
    if not codex_executable:
        registration.update(
            {"status": "unavailable", "reason": "codex_executable_missing"}
        )
        return registration
    version_probe = run_command(
        [codex_executable, "--version"], repository, timeout_seconds
    )
    if version_probe["ok"]:
        registration["codex_version"] = codex_version_from_output(
            version_probe["stdout"]
        )
    probe = json_probe(
        [codex_executable, "mcp", "get", "mulgae", "--json"],
        repository,
        timeout_seconds,
    )
    if not probe["ok"]:
        if probe["exit_code"] == 1 and not probe["timed_out"]:
            return registration
        if probe["timed_out"] or probe.get("error_code"):
            registration.update(
                {"status": "degraded", "reason": "registration_probe_failed"}
            )
        return registration
    result = probe.get("result")
    transport = result.get("transport") if isinstance(result, dict) else None
    if not isinstance(result, dict) or not isinstance(transport, dict):
        registration.update(
            {"status": "degraded", "reason": "invalid_registration_result"}
        )
        return registration

    if "required" not in result:
        required = None
        required_verification = "unverifiable"
        required_output_capability = "not_reported"
        compatibility_reason = "required_unverifiable"
    elif isinstance(result["required"], bool):
        required = result["required"]
        required_verification = "verified" if required else "mismatch"
        required_output_capability = "reported"
        compatibility_reason = None
    else:
        registration.update(
            {
                "status": "degraded",
                "reason": "invalid_registration_result",
                "required_output_capability": "invalid",
            }
        )
        return registration

    command = transport.get("command")
    resolved_command: Path | None = None
    if isinstance(command, str) and command:
        candidate = Path(command).expanduser()
        if candidate.is_absolute() and candidate.is_file() and os.access(candidate, os.X_OK):
            resolved_command = candidate.resolve()
        elif not candidate.is_absolute():
            discovered = shutil.which(command)
            if discovered:
                resolved_command = Path(discovered).resolve()

    args = transport.get("args")
    repository_bound = False
    arguments_match = False
    if isinstance(args, list) and all(isinstance(argument, str) for argument in args):
        try:
            configured_root = Path(args[2]).expanduser().resolve()
            repository_bound = configured_root == repository
            arguments_match = (
                len(args) == 3
                and args[0] == "mcp"
                and args[1] == "--project-root"
                and repository_bound
            )
        except (IndexError, OSError):
            repository_bound = False

    raw_cwd = transport.get("cwd", result.get("cwd"))
    try:
        cwd_bound = isinstance(raw_cwd, str) and Path(raw_cwd).expanduser().resolve() == repository
    except OSError:
        cwd_bound = False
    startup_timeout = result.get("startup_timeout_sec")
    tool_timeout = result.get("tool_timeout_sec")
    startup_supported = (
        isinstance(startup_timeout, (int, float))
        and not isinstance(startup_timeout, bool)
        and startup_timeout >= 30
    )
    tool_supported = (
        isinstance(tool_timeout, (int, float))
        and not isinstance(tool_timeout, bool)
        and tool_timeout >= MULGAE_MCP_TOOL_TIMEOUT_SEC
    )
    binary_matches = bool(
        resolved_command
        and mulgae_executable
        and resolved_command == Path(mulgae_executable).resolve()
    )
    registration.update(
        {
            "enabled": result.get("enabled") is True,
            "stdio": transport.get("type") == "stdio",
            "repository_bound": repository_bound,
            "arguments_match": arguments_match,
            "cwd_bound": cwd_bound,
            "required": required,
            "required_verification": required_verification,
            "required_output_capability": required_output_capability,
            "compatibility_reason": compatibility_reason,
            "command_resolvable": resolved_command is not None,
            "binary_matches_selected": binary_matches,
            "startup_timeout_sec": startup_timeout,
            "tool_timeout_sec": tool_timeout,
        }
    )
    if (
        registration["project_config_present"]
        and registration["enabled"]
        and registration["stdio"]
        and arguments_match
        and cwd_bound
        and required_verification in {"verified", "unverifiable"}
        and binary_matches
        and startup_supported
        and tool_supported
    ):
        registration["status"] = "configured"
    else:
        registration.update(
            {"status": "degraded", "reason": "registration_mismatch"}
        )
    return registration
''',
        r'''def zcode_mcp_registration(
    server: str,
    repository: Path,
    selected_executable: str | None,
) -> dict[str, Any]:
    # ZCode has no `mcp get` CLI probe; registrations are user-global in the
    # `mcp.servers` object of `~/.zcode/cli/config.json`. A same-name entry
    # in a project's `.zcode/config.json` overrides the user entry, so the
    # project file is consulted last and its entry wins as the effective
    # scope. The entry resolving at all is the registration signal; the
    # command must resolve and match the selected binary, and a disabled or
    # non-stdio entry degrades rather than disappears. ZCode defines no
    # per-server timeout fields, so there is no timeout surface to verify.
    registration: dict[str, Any] = {
        "status": "missing",
        "scope": None,
        "stdio": None,
        "command_resolvable": None,
        "binary_matches_selected": None,
    }
    entry: Any = None
    scope: str | None = None
    for label, source in (
        ("user", Path.home().joinpath(".zcode/cli/config.json")),
        ("project", repository.joinpath(".zcode/config.json")),
    ):
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, json.JSONDecodeError):
            registration.update(
                {"status": "degraded", "reason": f"{label}_config_invalid_json"}
            )
            return registration
        mcp = document.get("mcp") if isinstance(document, dict) else None
        servers = mcp.get("servers") if isinstance(mcp, dict) else None
        if isinstance(servers, dict) and server in servers:
            entry = servers[server]
            scope = label
    if scope is None:
        registration["reason"] = "registration_not_found"
        return registration
    stdio = isinstance(entry, dict) and entry.get("type", "stdio") == "stdio"
    command = entry.get("command") if isinstance(entry, dict) else None
    resolved_command: Path | None = None
    if isinstance(command, str) and command:
        candidate = Path(command).expanduser()
        if candidate.is_absolute() and candidate.is_file() and os.access(candidate, os.X_OK):
            resolved_command = candidate.resolve()
        elif not candidate.is_absolute():
            discovered = shutil.which(command)
            if discovered:
                resolved_command = Path(discovered).resolve()
    binary_matches: bool | None = None
    if selected_executable is not None:
        binary_matches = bool(
            resolved_command
            and resolved_command == Path(selected_executable).resolve()
        )
    registration.update(
        {
            "scope": scope,
            "stdio": stdio,
            "command_resolvable": resolved_command is not None,
            "binary_matches_selected": binary_matches,
        }
    )
    if isinstance(entry, dict) and entry.get("enabled") is False:
        registration.update({"status": "degraded", "reason": "registration_disabled"})
    elif not stdio:
        registration.update({"status": "degraded", "reason": "registration_not_stdio"})
    elif resolved_command is None:
        registration.update({"status": "degraded", "reason": "command_unresolvable"})
    elif binary_matches is False:
        registration.update({"status": "degraded", "reason": "binary_mismatch"})
    else:
        registration["status"] = "configured"
    return registration


def inspect_mulgae_mcp(
    repository: Path, mulgae_executable: str | None, timeout_seconds: float
) -> dict[str, Any]:
    # Registration is user-global in `~/.zcode/cli/config.json`; a project
    # `.zcode/config.json` entry of the same name overrides it.
    return zcode_mcp_registration("mulgae", repository, mulgae_executable)
''',
    ),
    (
        r'''def inspect_gaori_mcp(
    repository: Path, gaori_executable: str | None, timeout_seconds: float
) -> dict[str, Any]:
    project_config = repository.joinpath(".codex/config.toml")
    project_config_present = project_config.is_file()
    registration: dict[str, Any] = {
        "status": "missing",
        "project_config_present": project_config_present,
        "enabled": None,
        "stdio": None,
        "repository_bound": None,
        "command_resolvable": None,
        "binary_matches_selected": None,
        "tool_timeout_sec": None,
    }
    codex_executable = shutil.which("codex")
    if not codex_executable:
        registration["status"] = "unavailable"
        registration["reason"] = "codex_executable_missing"
        return registration

    probe = json_probe(
        [codex_executable, "mcp", "get", "gaori", "--json"],
        repository,
        timeout_seconds,
    )
    if not probe["ok"]:
        if project_config_present:
            registration["status"] = "degraded"
            registration["reason"] = (
                "registration_probe_timed_out"
                if probe["timed_out"]
                else "project_registration_inactive_or_invalid"
            )
        return registration

    result = probe.get("result")
    if not isinstance(result, dict):
        registration.update(
            {"status": "degraded", "reason": "invalid_registration_result"}
        )
        return registration

    transport = result.get("transport")
    if not isinstance(transport, dict):
        registration.update(
            {"status": "degraded", "reason": "missing_registration_transport"}
        )
        return registration

    enabled = result.get("enabled") is True
    stdio = transport.get("type") == "stdio"
    command = transport.get("command")
    args = transport.get("args")
    resolved_command: Path | None = None
    if isinstance(command, str) and command:
        candidate = Path(command).expanduser()
        if (
            candidate.is_absolute()
            and candidate.is_file()
            and os.access(candidate, os.X_OK)
        ):
            resolved_command = candidate.resolve()
        elif not candidate.is_absolute():
            discovered = shutil.which(command)
            if discovered:
                resolved_command = Path(discovered).resolve()

    repository_bound = False
    server_mode = False
    if isinstance(args, list) and all(isinstance(argument, str) for argument in args):
        try:
            repo_index = args.index("--repo")
            configured_repository = Path(args[repo_index + 1]).expanduser().resolve()
            repository_bound = configured_repository == repository
        except (ValueError, IndexError, OSError):
            repository_bound = False
        server_mode = bool(args and args[-1] == "mcp")

    tool_timeout = result.get("tool_timeout_sec")
    timeout_supported = (
        isinstance(tool_timeout, (int, float))
        and not isinstance(tool_timeout, bool)
        and tool_timeout >= GAORI_MCP_TOOL_TIMEOUT_SEC
    )
    binary_matches = bool(
        resolved_command
        and gaori_executable
        and resolved_command == Path(gaori_executable).resolve()
    )
    registration.update(
        {
            "enabled": enabled,
            "stdio": stdio,
            "repository_bound": repository_bound,
            "command_resolvable": resolved_command is not None,
            "binary_matches_selected": binary_matches,
            "tool_timeout_sec": tool_timeout,
        }
    )
    if (
        project_config_present
        and enabled
        and stdio
        and repository_bound
        and server_mode
        and resolved_command is not None
        and timeout_supported
    ):
        registration["status"] = "configured"
    else:
        registration["status"] = "degraded"
        registration["reason"] = "registration_mismatch"
    return registration
''',
        r'''def inspect_gaori_mcp(
    repository: Path, gaori_executable: str | None, timeout_seconds: float
) -> dict[str, Any]:
    # Registration is user-global in `~/.zcode/cli/config.json`; a project
    # `.zcode/config.json` entry of the same name overrides it.
    return zcode_mcp_registration("gaori", repository, gaori_executable)
''',
    ),
    # The version helper parsed Codex CLI output for the probes above; with
    # those probes reading config files instead, it has no caller left.
    (
        r'''def codex_version_from_output(output: str) -> str | None:
    match = re.search(r"\bcodex(?:-cli)?\s+v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)\b", output)
    return match.group(1) if match else None


''',
        "",
    ),
    # The repository configuration inventories listed the Codex project
    # config file, which belongs to another host and is no longer the
    # registration location here.
    (
        r'''        mulgae_configuration_entry(repository, ".mulgaeignore", timeout_seconds),
        configuration_entry(repository, ".codex/config.toml", timeout_seconds),
    ]
''',
        r'''        mulgae_configuration_entry(repository, ".mulgaeignore", timeout_seconds),
    ]
''',
    ),
    (
        r'''        configuration_entry(repository, ".gaori/toolchain.yaml", timeout_seconds),
        configuration_entry(repository, ".codex/config.toml", timeout_seconds),
    ]
''',
        r'''        configuration_entry(repository, ".gaori/toolchain.yaml", timeout_seconds),
    ]
''',
    ),
    # `hooks/task_commit_gate.py` names the remediation skill in the text the
    # user sees when a commit is denied. Markdown rules do not reach `.py`.
    ("$aquarium:", "/aquarium:"),
)

# Substitutions for JSON data files. ZCode auto-loads `hooks/hooks.json` from
# the plugin root and expands `${ZCODE_PLUGIN_ROOT}` in hook commands, so the
# Codex spelling must move. With the Codex spelling the shell expands the
# variable to nothing, `python3 /hooks/task_commit_gate.py` exits 2, and a
# PreToolUse exit 2 is an unconditional deny of every Bash call.
DATA_SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("${PLUGIN_ROOT}", "${ZCODE_PLUGIN_ROOT}"),
)

# Text that must exist after transformation, relative to the generated plugin.
# A script substitution that quietly stops matching would otherwise ship a
# script searching only Codex paths, and the Markdown forbidden-check cannot
# see it. The Ouroboros blocks are multi-line matches, so a reformat upstream
# would stop them matching and silently restore the Codex-only inspection.
REQUIRED_TEXT: tuple[tuple[str, str], ...] = (
    ("skills/dev-setup/scripts/inspect_tools.py", '".zcode/skills"'),
    ("skills/dev-setup/scripts/inspect_tools.py", '".agents/skills"'),
    ("skills/dev-setup/scripts/inspect_tools.py", '".zcode/cli/config.json"'),
    ("skills/dev-setup/scripts/inspect_tools.py", "ouroboros_mcp_registration"),
    ("skills/dev-setup/scripts/inspect_tools.py", "zcode_mcp_registration"),
    ("skills/dev-setup/scripts/inspect_tools.py", '"host_integration"'),
    ("skills/dev-setup/scripts/inspect_tools.py", "doctor_checks_failed"),
    ("hooks/task_commit_gate.py", "/aquarium:task-commit"),
    ("hooks/hooks.json", "${ZCODE_PLUGIN_ROOT}"),
)

# Strings that must not survive into the generated tree, scanned across the
# whole generated plugin. Each entry pairs a needle with the remedy, so a
# failure names its own fix.
FORBIDDEN: tuple[tuple[str, str], ...] = (
    ("$aquarium:", "add a substitution rule"),
    ("$use-", "add a substitution rule"),
    ("$lore-", "add a substitution rule"),
    ("$orca-cli", "add a substitution rule"),
    ("request_user_input", "add a substitution rule or an override"),
    ("--agent codex", "add an override"),
    (".codex/skills", "ZCode loads ~/.zcode/skills and ~/.agents/skills; add a substitution rule"),
    (".codex/config", "ZCode registers MCP servers in ~/.zcode/cli/config.json; add a substitution rule"),
    ("${PLUGIN_ROOT}", "ZCode provides ${ZCODE_PLUGIN_ROOT}; fix the hook rewrite"),
    ("Codex", "add a substitution rule, an override, or a reviewed exemption"),
)

# Every lowercase `$name` in upstream Markdown is a Codex skill invocation.
# `FORBIDDEN` names one needle per sigil family that already exists, so a family
# upstream introduces later passes both the substitution table and the forbidden
# scan and ships Codex invocation syntax to a ZCode user in silence. Uppercase
# spellings are environment variables the generated tree still needs and
# deliberately do not match.
SIGIL = re.compile(r"\$[a-z][a-z0-9:_-]*")


class SyncError(RuntimeError):
    """A condition that must stop generation rather than produce partial output."""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def upstream_commit() -> str:
    result = subprocess.run(
        ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SyncError(
            "cannot resolve the upstream commit; run `git submodule update --init`"
        )
    return result.stdout.strip()


def require_upstream() -> None:
    """Refuse to generate from a missing or partially initialized submodule.

    Plugin installation treats a failed submodule clone as non-fatal, so an
    empty `upstream/` is a realistic state. Generating from it would silently
    delete the committed plugin.
    """
    marker = UPSTREAM_PLUGIN / ".codex-plugin" / "plugin.json"
    if not marker.is_file():
        raise SyncError(
            f"upstream plugin not found at {marker}; "
            "run `git submodule update --init --recursive` before syncing"
        )
    for name in ("skills", "hooks"):
        if not (UPSTREAM_PLUGIN / name).is_dir():
            raise SyncError(f"upstream is missing `{name}/`; refusing to generate")
    check_upstream_directories()


def check_upstream_directories() -> None:
    """Refuse to generate when upstream grows a directory nobody decided about.

    `COPIED_DIRECTORIES` is an allowlist with no counterpart check, so a new
    directory upstream would otherwise be dropped in silence. Whether it
    belongs in a ZCode artifact is a decision, and skipping it is not a safe
    default.
    """
    known = set(COPIED_DIRECTORIES) | {".codex-plugin"}
    unknown = sorted(
        path.name
        for path in UPSTREAM_PLUGIN.iterdir()
        if path.is_dir() and path.name not in known
    )
    if unknown:
        raise SyncError(
            "upstream has directories this transformation does not handle: "
            + ", ".join(unknown)
            + "; add them to COPIED_DIRECTORIES or exclude them deliberately"
        )


def apply_substitutions(text: str) -> str:
    for old, new in SUBSTITUTIONS:
        text = text.replace(old, new)
    return text


def copy_tree(destination: Path) -> None:
    for name in COPIED_DIRECTORIES:
        source = UPSTREAM_PLUGIN / name
        if source.is_dir():
            shutil.copytree(source, destination / name)


def transform_skills(destination: Path) -> None:
    """Validate each skill and drop the Codex sidecar directories.

    ZCode reads only `name` and `description` from the frontmatter and has no
    per-skill invocation gating — the upstream `agents/openai.yaml` policy has
    no equivalent to derive, and a `disable-model-invocation` key would be
    dead configuration implying a mechanism the host lacks. The sidecar's `$`
    prompts would also contradict the generated text, so it is dropped.
    """
    skills = destination / "skills"
    for skill in sorted(p for p in skills.iterdir() if p.is_dir()):
        if not (skill / "SKILL.md").is_file():
            raise SyncError(f"skill `{skill.name}` has no SKILL.md")
        content = (skill / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"\A---\n(.*?)\n---\n", content, re.DOTALL)
        if not match:
            raise SyncError(f"skill `{skill.name}` has no frontmatter block")
        keys = {line.split(":", 1)[0] for line in match.group(1).splitlines() if line}
        unexpected = sorted(keys - {"name", "description"})
        if unexpected:
            raise SyncError(
                f"skill `{skill.name}` frontmatter has keys ZCode does not read: "
                + ", ".join(unexpected)
            )
        shutil.rmtree(skill / "agents", ignore_errors=True)


def transform_text(destination: Path) -> None:
    for path in sorted(destination.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix in TEXT_SUFFIXES:
            rules = SUBSTITUTIONS
        elif path.suffix in SCRIPT_SUFFIXES:
            rules = SCRIPT_SUBSTITUTIONS
        elif path.suffix in DATA_SUFFIXES:
            rules = DATA_SUBSTITUTIONS
        else:
            continue
        original = path.read_text(encoding="utf-8")
        replaced = original
        for old, new in rules:
            replaced = replaced.replace(old, new)
        if replaced != original:
            path.write_text(replaced, encoding="utf-8")


def check_required(staged_root: Path) -> None:
    missing: list[str] = []
    for relative, needle in REQUIRED_TEXT:
        path = staged_root / relative
        if not path.is_file():
            missing.append(f"  {relative}: file not generated")
        elif needle not in path.read_text(encoding="utf-8"):
            missing.append(f"  {relative}: missing `{needle}` — a substitution stopped matching")
    if missing:
        raise SyncError("required text is absent from the generated tree:\n" + "\n".join(missing))


def upstream_manifest() -> dict[str, Any]:
    return json.loads(
        (UPSTREAM_PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )


def load_override_manifest() -> dict[str, str]:
    if not OVERRIDE_MANIFEST.is_file():
        return {}
    return json.loads(OVERRIDE_MANIFEST.read_text(encoding="utf-8"))


def check_codex_exemptions() -> set[str]:
    """Return the paths whose remaining `Codex` mentions were reviewed and kept.

    Some upstream text names the Codex CLI as a third-party tool rather than as
    the host running the skill — a Mulgae provider, a required CLI version. That
    text is correct in a ZCode artifact and cannot be renamed without making it
    false, but it still trips the `Codex` needle after an override is applied,
    because overrides do not exempt their own content.

    An exemption records that a human read every remaining mention in one file
    and confirmed each is third-party. That judgement holds only for the bytes it
    was made against, so an upstream edit stops the run instead of widening the
    exemption in silence.
    """
    if not CODEX_EXEMPTIONS.is_file():
        return set()
    recorded_all: dict[str, str] = json.loads(CODEX_EXEMPTIONS.read_text(encoding="utf-8"))
    for relative, recorded in sorted(recorded_all.items()):
        source = UPSTREAM_PLUGIN / relative
        if not source.is_file():
            raise SyncError(
                f"`Codex` exemption targets `{relative}`, which no longer exists "
                "upstream; remove the exemption or retarget it"
            )
        current = digest(source)
        if current != recorded:
            raise SyncError(
                f"`Codex` exemption stale: `{relative}` changed upstream\n"
                f"  recorded {recorded}\n"
                f"  current  {current}\n"
                "re-read every remaining `Codex` mention, confirm each still names "
                "the third-party CLI, then update overrides/codex-exemptions.json"
            )
    return set(recorded_all)


def apply_overrides(destination: Path) -> list[str]:
    """Replace files whose ZCode form diverges semantically from upstream.

    Every override records the SHA-256 of the upstream file it was derived
    from. When upstream changes that file the override is stale, and merging
    it silently would ship guidance that no longer matches the source. That is
    the one failure mode that quietly breaks a fork, so it stops the run.
    """
    manifest = load_override_manifest()
    applied: list[str] = []
    for relative, recorded in sorted(manifest.items()):
        source = UPSTREAM_PLUGIN / relative
        override = OVERRIDES / relative
        if not override.is_file():
            raise SyncError(f"override file missing: {override}")
        if not source.is_file():
            raise SyncError(
                f"override targets `{relative}`, which no longer exists upstream; "
                "remove the override or retarget it"
            )
        current = digest(source)
        if current != recorded:
            raise SyncError(
                f"override stale: `{relative}` changed upstream\n"
                f"  recorded {recorded}\n"
                f"  current  {current}\n"
                "re-derive the override from the new upstream content, then update "
                "overrides/manifest.json"
            )
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(override, target)
        applied.append(relative)
    return applied


def write_plugin_manifest(destination: Path) -> None:
    """Derive the ZCode manifest from the Codex one so versions cannot diverge.

    The manifest lives inside the generated tree at
    `.zcode-plugin/plugin.json`, the first name ZCode probes. Only fields
    ZCode documents are emitted; the Codex `interface` block and `repository`
    are dropped rather than reported as diagnostics — display metadata lives
    in the root `marketplace.json` entry instead.
    """
    codex = upstream_manifest()
    author = codex.get("author")
    manifest: dict[str, Any] = {
        "name": codex["name"],
        "version": codex["version"],
        "description": apply_substitutions(codex["description"]),
        "author": author.get("name") if isinstance(author, dict) else author,
        "homepage": codex["homepage"],
        "license": codex["license"],
        "keywords": codex["keywords"],
        "skills": "./skills/",
    }
    directory = destination / ".zcode-plugin"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "plugin.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def check_forbidden(staged_root: Path, codex_exemptions: set[str]) -> None:
    """Scan every generated text file for host-specific text.

    Scripts and YAML are included. Only the `Codex` needle is skipped, and
    only for reviewed exemptions; every other needle applies to every file.
    """
    failures: list[str] = []
    for path in sorted(staged_root.rglob("*")):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        relative = path.relative_to(staged_root)
        text = path.read_text(encoding="utf-8")
        for needle, remedy in FORBIDDEN:
            if needle == "Codex" and str(relative) in codex_exemptions:
                continue
            if needle in text:
                failures.append(f"  {relative}: contains `{needle}` — {remedy}")
    if failures:
        raise SyncError("host-specific text survived transformation:\n" + "\n".join(failures))


def check_sigils(staged_root: Path) -> None:
    """Fail on any Codex skill sigil that no substitution rule rewrote.

    This closes the class rather than the known instances: an unmapped sigil is
    a silent failure, because it is valid Markdown that simply names a command
    the reader's host does not have.
    """
    failures: list[str] = []
    for path in sorted(staged_root.rglob("*.md")):
        if not path.is_file():
            continue
        found = sorted(set(SIGIL.findall(path.read_text(encoding="utf-8"))))
        if found:
            failures.append(f"  {path.relative_to(staged_root)}: {', '.join(found)}")
    if failures:
        raise SyncError(
            "Codex skill sigils survived transformation:\n"
            + "\n".join(failures)
            + "\nadd a substitution rule naming each sigil's ZCode form"
        )


def write_sync_manifest(
    destination: Path, repository: str, commit: str, overrides: list[str]
) -> None:
    files = {
        str(path.relative_to(destination)): digest(path)
        for path in sorted(destination.rglob("*"))
        if path.is_file() and path.name != SYNC_MANIFEST
    }
    payload = {
        "upstream": {
            "repository": repository,
            "commit": commit,
        },
        "overrides": overrides,
        "files": files,
    }
    (destination / SYNC_MANIFEST).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def generate(staged_root: Path) -> tuple[str, list[str]]:
    commit = upstream_commit()
    codex_exemptions = check_codex_exemptions()
    plugin = staged_root / "plugins" / "aquarium"
    plugin.mkdir(parents=True)
    copy_tree(plugin)
    transform_text(plugin)
    # Overrides replace whole files, so they run after the substitutions: an
    # override is hand-authored final content, not text to rewrite.
    overrides = apply_overrides(plugin)
    transform_skills(plugin)
    write_plugin_manifest(plugin)
    check_forbidden(plugin, codex_exemptions)
    check_sigils(plugin)
    check_required(plugin)
    write_sync_manifest(plugin, upstream_manifest()["repository"], commit, overrides)
    return commit, overrides


def differences(left: Path, right: Path, prefix: Path = Path()) -> list[str]:
    comparison = filecmp.dircmp(str(left), str(right))
    found = [f"only in committed output: {prefix / name}" for name in sorted(comparison.left_only)]
    found += [f"only in regenerated output: {prefix / name}" for name in sorted(comparison.right_only)]
    found += [f"differs: {prefix / name}" for name in sorted(comparison.diff_files)]
    for name in sorted(comparison.common_dirs):
        found += differences(left / name, right / name, prefix / name)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed output matches a fresh regeneration",
    )
    arguments = parser.parse_args()

    try:
        require_upstream()
        with tempfile.TemporaryDirectory() as temporary:
            staged = Path(temporary) / "repository"
            staged.mkdir()
            commit, overrides = generate(staged)

            if arguments.check:
                if not OUTPUT.is_dir():
                    print(
                        "error: plugins/aquarium/ has not been generated",
                        file=sys.stderr,
                    )
                    return 1
                drift = differences(OUTPUT, staged / "plugins" / "aquarium", Path("plugins/aquarium"))
                if drift:
                    print("error: committed output is stale:", file=sys.stderr)
                    for entry in drift:
                        print(f"  {entry}", file=sys.stderr)
                    print("\nrun `python3 scripts/sync.py` and commit the result", file=sys.stderr)
                    return 1
                print(f"in sync with upstream {commit[:9]} ({len(overrides)} overrides)")
                return 0

            if OUTPUT.exists():
                shutil.rmtree(OUTPUT)
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(staged / "plugins" / "aquarium", OUTPUT)
    except SyncError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    skills = sorted(p.name for p in (OUTPUT / "skills").iterdir() if p.is_dir())
    print(f"generated {len(skills)} skills from upstream {commit[:9]}")
    print(f"  ZCode has no per-skill invocation gating; descriptions guide use")
    print(f"  {len(overrides)} overrides applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
