#!/usr/bin/env python3
"""Generate the ZCode plugin from the pinned upstream Codex plugin.

The upstream repository at `upstream/` is the single source of truth. This
script performs a deterministic transformation into `plugins/aquarium/`,
committed so the plugin installs even when the submodule is absent.

Run `sync.py` to regenerate, or `sync.py --check` to fail on drift.
"""

from __future__ import annotations

import argparse
import ast
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
    # v0.1.11 moves review supervision into shared references. independent-review
    # runs on the host's own Agent tool here, so the Orca supervision reference
    # serves orca-review alone and its Codex dispatch clause does not apply.
    (
        "the current execution backend for Aquarium's independent review contracts",
        "the current execution backend for Aquarium's `/aquarium:orca-review` provider layer",
    ),
    (
        "For `/aquarium:independent-review`, start one fresh Codex with the live guide's "
        "supervised `worker-start --worktree current --agent codex` path. Do not reuse a "
        "terminal or create another Git worktree.",
        "Do not reuse a terminal or create another Git worktree.",
    ),
    # orca-review routes to external provider CLIs; the default review backend
    # here is the host's own reviewer subagent, so "non-Codex" names the wrong
    # default.
    ("a non-Codex independent review", "an external-provider independent review"),
    ("a removable non-Codex provider layer", "a removable external provider layer"),
    (" for Codex.", " for ZCode."),
    # Ouroboros registers its skills with the host agent, so the component whose
    # health `dev-setup` establishes is the ZCode one here. The bundle skill
    # names the same component in a list of Ouroboros setup mutations.
    ("Codex skill health", "ZCode skill health"),
    (
        "Ouroboros package, Codex and runtime components",
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
# bytes exactly. Only small, stable islands of host-specific text are handled
# here; whole functions whose ZCode form diverges semantically are reworked
# through `SCRIPT_SURGERY` below, which anchors on function names instead of
# exact upstream bytes.
SCRIPT_SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    # Skill discovery narrows to the ZCode roots: this artifact diagnoses one
    # host, and a copy sitting in another host's root is neither reachable
    # here nor a duplicate of anything. ZCode exposes no config-dir
    # environment variable, so the roots are literal. `~/.agents/skills` is a
    # ZCode root natively, so it stays.
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
    # The repository configuration inventories listed the Codex project
    # config file, which belongs to another host and is not the registration
    # location here. The MCP registration readers in `SCRIPT_SURGERY` report
    # the project `.zcode/config.json` scope instead.
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

# Whole-function rework for bundled scripts whose ZCode form diverges
# semantically from upstream. `inspect_tools.py` probes MCP registrations
# through the Codex CLI; this host has no such CLI, and registrations live in
# the `mcp.servers` object of `~/.zcode/cli/config.json` (user level), with a
# same-name entry in a project's `.zcode/config.json` overriding the user
# entry. A literal substitution cannot carry that rewrite — the probe code
# spans whole functions — so each rule names a top-level function to replace
# or delete. Anchoring on names instead of bytes keeps a rule working through
# upstream body edits, and the post-surgery checks stop generation when
# upstream renames a target or a deleted function is still referenced.
SCRIPT_SURGERY: dict[str, dict[str, Any]] = {
    "skills/dev-setup/scripts/inspect_tools.py": {
        "replace": {
            "inspect_mulgae_mcp": r'''def zcode_mcp_entries(server: str, repository: Path) -> dict[str, Any]:
    # ZCode has no `mcp get` CLI probe; registrations live under the
    # `mcp.servers` object of `~/.zcode/cli/config.json` (user level), and a
    # same-name entry in a project's `.zcode/config.json` overrides the user
    # entry for that project. Both scopes are read directly here.
    scopes: dict[str, Any] = {"user": None, "project": None}
    invalid_config: str | None = None
    for label, source in (
        ("user", Path.home().joinpath(".zcode/cli/config.json")),
        ("project", repository.joinpath(".zcode/config.json")),
    ):
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, json.JSONDecodeError):
            invalid_config = label
            break
        mcp = document.get("mcp") if isinstance(document, dict) else None
        servers = mcp.get("servers") if isinstance(mcp, dict) else None
        if isinstance(servers, dict) and server in servers:
            scopes[label] = servers[server]
    return {"scopes": scopes, "invalid_config": invalid_config}


def zcode_mcp_scope_status(
    entry: Any, selected_executable: str | None
) -> dict[str, Any]:
    # An entry resolving at all is the registration signal; a disabled or
    # non-stdio entry or an unresolvable command degrades rather than
    # disappears. ZCode defines no per-server timeout fields, so there is no
    # timeout surface to verify. A launcher entry such as uvx need not match
    # the selected binary byte-for-byte, so the binary match is reported as
    # evidence and never degrades the status by itself.
    if entry is None:
        return {"status": "missing", "reason": "registration_not_found"}
    registration: dict[str, Any] = {
        "status": "degraded",
        "stdio": None,
        "command_resolvable": None,
        "binary_matches_selected": None,
    }
    stdio = isinstance(entry, dict) and entry.get("type", "stdio") == "stdio"
    command = entry.get("command") if isinstance(entry, dict) else None
    resolved_command = resolve_mcp_command(command)
    binary_matches: bool | None = None
    if selected_executable is not None:
        binary_matches = bool(
            resolved_command
            and resolved_command == Path(selected_executable).resolve()
        )
    registration.update(
        {
            "stdio": stdio,
            "command_resolvable": resolved_command is not None,
            "binary_matches_selected": binary_matches,
        }
    )
    if isinstance(entry, dict) and entry.get("enabled") is False:
        registration["reason"] = "registration_disabled"
    elif not stdio:
        registration["reason"] = "registration_not_stdio"
    elif resolved_command is None:
        registration["reason"] = "command_unresolvable"
    else:
        registration["status"] = "configured"
    return registration


def zcode_mcp_scopes(
    server: str, repository: Path, selected_executable: str | None
) -> dict[str, Any]:
    # Registrations are user-global by default; a project `.zcode/config.json`
    # entry of the same name is an explicit local override that wins as the
    # effective scope. The three reported views mirror the upstream global,
    # isolated-local, and effective probes, read from config files instead of
    # a host CLI.
    reading = zcode_mcp_entries(server, repository)
    project_config_present, project_config_symlinked = safe_managed_file_state(
        repository / ".zcode" / "config.json", repository
    )
    registration: dict[str, Any] = {
        "status": "missing",
        "preferred_scope": "global",
        "effective_scope": "none",
        "local_confirmation_required": None,
    }
    if reading["invalid_config"]:
        registration.update(
            {
                "status": "degraded",
                "effective_scope": "unverifiable",
                "reason": f"{reading['invalid_config']}_config_invalid_json",
                "global": {"status": "degraded"},
                "local": {
                    "status": "degraded",
                    "project_config_present": project_config_present,
                    "project_config_symlinked": project_config_symlinked,
                },
            }
        )
        return registration
    global_registration = zcode_mcp_scope_status(
        reading["scopes"]["user"], selected_executable
    )
    if project_config_symlinked:
        registration.update(
            {
                "status": "unverifiable",
                "effective_scope": "unverifiable",
                "reason": "project_configuration_symlinked",
                "global": global_registration,
                "local": {
                    "status": "unverifiable",
                    "reason": "project_configuration_symlinked",
                    "project_config_present": project_config_present,
                    "project_config_symlinked": project_config_symlinked,
                },
                "recommendation": "resolve_symlinked_local_configuration",
            }
        )
        return registration
    local_registration = zcode_mcp_scope_status(
        reading["scopes"]["project"], selected_executable
    )
    local_registration.update(
        {
            "project_config_present": project_config_present,
            "project_config_symlinked": project_config_symlinked,
        }
    )
    if (
        local_registration["status"] == "missing"
        and not project_config_present
    ):
        local_registration["reason"] = "project_configuration_missing"
    if reading["scopes"]["project"] is not None:
        effective_scope = "local"
        effective_registration: dict[str, Any] | None = local_registration
    elif reading["scopes"]["user"] is not None:
        effective_scope = "global"
        effective_registration = global_registration
    else:
        effective_scope = "none"
        effective_registration = None
    local_confirmable = local_registration["status"] != "missing"
    registration.update(
        {
            "status": (
                effective_registration["status"]
                if effective_registration is not None
                else "missing"
            ),
            "effective_scope": effective_scope,
            "local_confirmation_required": local_confirmable,
            "global": global_registration,
            "local": local_registration,
            "recommendation": mcp_recommendation(
                global_registration["status"], bool(local_confirmable)
            ),
        }
    )
    if effective_registration is not None and effective_registration.get("reason"):
        registration["reason"] = effective_registration["reason"]
    return registration


def inspect_mulgae_mcp(
    repository: Path, mulgae_executable: str | None, timeout_seconds: float
) -> dict[str, Any]:
    # Registration is user-global in `~/.zcode/cli/config.json`; a project
    # `.zcode/config.json` entry of the same name is an explicit local
    # override. ZCode has no `mcp` CLI to probe, so both scopes and the
    # effective registration are read from those config files.
    return zcode_mcp_scopes("mulgae", repository, mulgae_executable)
''',
            "inspect_gaori_mcp": r'''def inspect_gaori_mcp(
    repository: Path, gaori_executable: str | None, timeout_seconds: float
) -> dict[str, Any]:
    # Registration is user-global in `~/.zcode/cli/config.json`; a project
    # `.zcode/config.json` entry of the same name is an explicit local
    # override. ZCode has no `mcp` CLI to probe, so both scopes and the
    # effective registration are read from those config files.
    return zcode_mcp_scopes("gaori", repository, gaori_executable)
''',
            "inspect_ouroboros": r'''def ouroboros_mcp_registration(repository: Path) -> dict[str, Any]:
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
    reading = zcode_mcp_entries("ouroboros", repository)
    if reading["invalid_config"]:
        probe["reason"] = "registration_invalid_json"
        return {"status": "degraded", "probe": probe}
    entry: Any = None
    scope: str | None = None
    if reading["scopes"]["project"] is not None:
        entry = reading["scopes"]["project"]
        scope = "project"
    elif reading["scopes"]["user"] is not None:
        entry = reading["scopes"]["user"]
        scope = "user"
    if entry is None:
        probe["reason"] = "registration_not_found"
        return {"status": "missing", "probe": probe}
    if isinstance(entry, dict) and entry.get("enabled") is False:
        probe["reason"] = "registration_disabled"
        return {"status": "degraded", "probe": probe, "scope": scope}
    return {"status": "configured", "probe": probe, "scope": scope}


def inspect_ouroboros(repository: Path, timeout_seconds: float) -> dict[str, Any]:
    tool = base_tool("ooo")
    tool["supported_range"] = ">=0.51.1,<0.52.0"
    tool["mcp_registration"] = ouroboros_mcp_registration(repository)
    # Ouroboros registers its skills with the host agent, so the component
    # whose health this integration adds on this host is the config
    # registration resolved above.
    host_integration = {
        "status": tool["mcp_registration"]["status"],
        "probe": tool["mcp_registration"]["probe"],
    }

    if not tool["installed"]:
        tool["version_supported"] = False
        tool["probes"]["version"] = skipped_probe("executable_missing")
        tool["host_integration"] = {
            "status": "missing",
            "probe": skipped_probe("executable_missing"),
        }
        tool["mcp_runtime"] = {
            "status": "missing",
            "probe": skipped_probe("executable_missing"),
        }
        return tool

    version_raw = run_command(
        [tool["executable"], "--version"], repository, timeout_seconds
    )
    tool["version"] = ouroboros_version_from_output(
        f"{version_raw.get('stdout', '')}\n{version_raw.get('stderr', '')}"
    )
    tool["version_supported"] = version_raw["ok"] and supported_ouroboros_version(
        tool["version"]
    )
    tool["probes"]["version"] = {
        key: version_raw[key] for key in ("attempted", "ok", "exit_code", "timed_out")
    }

    # `ooo codex doctor` verifies another host's routing artifacts and the
    # `ooo zcode` group ships no doctor command. The config registration
    # resolved above is the host-integration signal here, so it is recorded
    # rather than reprobed.
    tool["host_integration"] = host_integration

    mcp_doctor = json_probe(
        [tool["executable"], "mcp", "doctor", "--json"],
        repository,
        timeout_seconds,
    )
    # The MCP 2 server registered in config launches as a separate process
    # while the CLI environment keeps MCP 1.x, so the doctor's `mcp_import`
    # check — and the exit code with it — fails on a correctly configured
    # machine. The remaining checks carry runtime health here; the server's
    # own health is the registration component.
    doctor_checks = mcp_doctor.get("result")
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

    components_ready = (
        tool["version_supported"]
        and tool["host_integration"]["status"] == "configured"
        and tool["mcp_runtime"]["status"] == "configured"
        and tool["mcp_registration"]["status"] == "configured"
    )
    tool["status"] = "configured" if components_ready else "degraded"
    return tool
''',
        },
        "delete": [
            "mcp_registration_probe",
            "classify_mulgae_mcp_scope",
            "classify_gaori_mcp_scope",
            "classify_ouroboros_registration",
            "effective_mcp_registration",
            "named_mcp_server_missing",
            "missing_mcp_scope",
            "failed_mcp_scope",
            "codex_version_from_output",
        ],
    },
}


def apply_script_surgery(relative: str, source: str, plan: dict[str, Any]) -> str:
    """Replace or delete whole top-level functions in a bundled script.

    Literal substitutions anchor on exact upstream bytes, so an upstream
    reformat can silently stop them matching. Surgery anchors on function
    names, which upstream renames loudly, and the post-surgery checks reject
    dangling references to deleted functions and any syntax error.
    """
    lines = source.splitlines(keepends=True)
    # `ast` carries exact line spans, so multi-line signatures — whose
    # closing parenthesis sits at column zero and defeats a naive
    # column-0 boundary scan — delimit functions correctly.
    spans: dict[str, tuple[int, int, int]] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        starts = [node.lineno] + [
            decorator.lineno for decorator in node.decorator_list
        ]
        start = min(starts) - 1
        content_end = node.end_lineno
        # A deletion also swallows the blank lines that separated the
        # function from the next top-level construct, so the surviving
        # neighbors keep exactly one blank-line gap.
        block_end = content_end
        while block_end < len(lines) and lines[block_end].strip() == "":
            block_end += 1
        spans[node.name] = (start, content_end, block_end)

    replacements = plan.get("replace", {})
    deletions = plan.get("delete", [])
    unknown = sorted((set(replacements) | set(deletions)) - set(spans))
    if unknown:
        raise SyncError(
            f"script surgery on `{relative}` names functions upstream no "
            "longer defines: " + ", ".join(unknown) + "; re-derive the plan"
        )
    for name, text in replacements.items():
        # A replacement may bundle helpers ahead of its namesake; requiring
        # the definition anywhere still catches a rule that drops it.
        if f"def {name}(" not in text:
            raise SyncError(
                f"script surgery replacement for `{name}` must define "
                f"`{name}`"
            )

    operations: list[tuple[int, int, list[str] | None]] = []
    for name in deletions:
        start, _, block_end = spans[name]
        operations.append((start, block_end, None))
    for name, text in replacements.items():
        start, content_end, _ = spans[name]
        replacement_lines = text.splitlines(keepends=True)
        if not replacement_lines or not replacement_lines[-1].endswith("\n"):
            replacement_lines.append("\n")
        operations.append((start, content_end, replacement_lines))
    # Apply bottom-up so earlier spans keep their line numbers.
    operations.sort(key=lambda operation: operation[0], reverse=True)
    for start, end, replacement in operations:
        lines[start:end] = replacement if replacement is not None else []

    result = "".join(lines)
    try:
        compile(result, relative, "exec")
    except SyntaxError as error:
        raise SyncError(
            f"script surgery on `{relative}` produced invalid syntax: {error}"
        ) from error
    for name in deletions:
        if re.search(rf"\b{re.escape(name)}\b", result):
            raise SyncError(
                f"script surgery deleted `{name}` from `{relative}` but a "
                "reference to it survived; extend the surgery plan"
            )
    return result


# Substitutions for JSON data files. ZCode auto-loads `hooks/hooks.json` from
# the plugin root and expands `${ZCODE_PLUGIN_ROOT}` in hook commands, so the
# Codex spelling must move. With the Codex spelling the shell expands the
# variable to nothing, `python3 /hooks/task_commit_gate.py` exits 2, and a
# PreToolUse exit 2 is an unconditional deny of every Bash call.
DATA_SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("${PLUGIN_ROOT}", "${ZCODE_PLUGIN_ROOT}"),
)

# Text that must exist after transformation, relative to the generated plugin.
# A substitution or surgery rule that quietly stopped matching would otherwise
# ship a script searching only Codex paths, and the Markdown forbidden-check
# cannot see it.
REQUIRED_TEXT: tuple[tuple[str, str], ...] = (
    ("skills/dev-setup/scripts/inspect_tools.py", '".zcode/skills"'),
    ("skills/dev-setup/scripts/inspect_tools.py", '".agents/skills"'),
    ("skills/dev-setup/scripts/inspect_tools.py", '".zcode/cli/config.json"'),
    ("skills/dev-setup/scripts/inspect_tools.py", "ouroboros_mcp_registration"),
    ("skills/dev-setup/scripts/inspect_tools.py", "zcode_mcp_scopes"),
    ("skills/dev-setup/scripts/inspect_tools.py", '"host_integration"'),
    ("skills/dev-setup/scripts/inspect_tools.py", "doctor_checks_failed"),
    # The test-setup inspector ships host-neutral from upstream; this marker
    # guards that it arrives whole rather than transformed away.
    (
        "skills/test-setup/scripts/inspect_testing.py",
        "aquarium-test-setup-inspection.v1",
    ),
    # The v0.1.11 inspectors and the provider-terminal helper also ship
    # host-neutral from upstream; the same marker guard applies to each.
    (
        "skills/docs-setup/scripts/inspect_docs.py",
        "aquarium-docs-inspection/v1",
    ),
    (
        "skills/release-handler/scripts/inspect_publication_state.py",
        "aquarium-release-publication-state/v1",
    ),
    (
        "skills/release-handler/scripts/inspect_release_notes.py",
        "aquarium-release-notes-inspection/v1",
    ),
    (
        "skills/independent-review/scripts/inspect_review_target.py",
        "aquarium-independent-review-target/v1",
    ),
    (
        "skills/orca-review/scripts/create_provider_terminal.py",
        "aquarium-orca-provider-terminal-request/v1",
    ),
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


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
        relative = path.relative_to(destination).as_posix()
        if relative in SCRIPT_SURGERY:
            replaced = apply_script_surgery(relative, replaced, SCRIPT_SURGERY[relative])
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


def load_codex_exemptions() -> dict[str, list[str]]:
    """Return reviewed `Codex` mention digests keyed by generated path."""
    if not CODEX_EXEMPTIONS.is_file():
        return {}
    return json.loads(CODEX_EXEMPTIONS.read_text(encoding="utf-8"))


def validate_codex_exemptions(
    staged_root: Path, recorded_all: dict[str, list[str]]
) -> set[str]:
    """Check each exemption against the `Codex` mentions that survived generation.

    Some upstream text names the Codex CLI as a third-party tool rather than as
    the host running the skill — a Mulgae provider, a required CLI version. That
    text is correct in a ZCode artifact and cannot be renamed without making it
    false, but it still trips the `Codex` needle after an override is applied,
    because overrides do not exempt their own content.

    An exemption records the SHA-256 of every generated line that still names
    `Codex` after substitutions and overrides, so one review judgement covers
    exactly the mentions the artifact ships. Upstream edits that leave every
    exempted line byte-identical keep the exemption valid; any new, changed, or
    removed mention line stops the run instead of widening the exemption in
    silence.
    """
    validated: set[str] = set()
    for relative, recorded in sorted(recorded_all.items()):
        if not isinstance(recorded, list) or not all(
            isinstance(item, str) for item in recorded
        ):
            raise SyncError(
                f"`Codex` exemption for `{relative}` is not a list of per-line digests; "
                "re-record it against the generated file"
            )
        path = staged_root / relative
        if not path.is_file():
            raise SyncError(
                f"`Codex` exemption targets `{relative}`, which the transformation no "
                "longer generates; remove the exemption or retarget it"
            )
        mentions = [
            (digest_text(line), line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if "Codex" in line
        ]
        recorded_set = set(recorded)
        if sorted(key for key, _ in mentions) == sorted(recorded):
            validated.add(relative)
            continue
        unreviewed = [(key, line) for key, line in mentions if key not in recorded_set]
        vanished = sorted(recorded_set - {key for key, _ in mentions})
        detail = "".join(f"  {key}\n    {line.strip()}\n" for key, line in unreviewed)
        if vanished:
            detail += "  recorded mentions no longer present:\n" + "".join(
                f"    {key}\n" for key in vanished
            )
        raise SyncError(
            f"`Codex` exemption stale: `{relative}` has `Codex` mentions the recorded "
            f"review does not cover\n{detail}"
            "re-read every listed mention, confirm each still names the third-party "
            "CLI, then update overrides/codex-exemptions.json with these per-line "
            "digests"
        )
    return validated


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
    codex_exemptions = load_codex_exemptions()
    plugin = staged_root / "plugins" / "aquarium"
    plugin.mkdir(parents=True)
    copy_tree(plugin)
    transform_text(plugin)
    # Overrides replace whole files, so they run after the substitutions: an
    # override is hand-authored final content, not text to rewrite.
    overrides = apply_overrides(plugin)
    transform_skills(plugin)
    write_plugin_manifest(plugin)
    validated_exemptions = validate_codex_exemptions(plugin, codex_exemptions)
    check_forbidden(plugin, validated_exemptions)
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
