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
SKILL_DESCRIPTIONS = OVERRIDES / "skill-descriptions.json"
EDITION_SKILLS = REPOSITORY / "edition-skills"
SYNC_MANIFEST = "sync-manifest.json"

# v0.1.15 moves the aquarium-dev channel out of the skill tree into a
# bundled CLI + MCP package. ZCode loads plugin MCP servers from a root
# `.mcp.json` that `write_mcp_manifest` derives, so the package ships like
# any other upstream directory.
COPIED_DIRECTORIES = ("skills", "references", "assets", "hooks", "tools")
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
    # `$create-podway-procedure` is the separately installed maintainer
    # authoring skill; user-scoped skills carry no plugin namespace here.
    ("$create-", "/create-"),
    ("$lore-commits", "/lore-commits"),
    ("$lore-query", "/lore-query"),
    ("$orca-cli", "/orca-cli"),
    ("$interview", "/interview"),
    ("$deslop", "/deslop"),
    ("$seed", "/seed"),
    ("$pm", "/pm"),
    ("$qa", "/qa"),
    # v0.1.14 routes repository prose guidance through the Humanizer pair.
    # The Korean form is listed first only to keep the family readable; the
    # two literals share no prefix boundary, so order cannot cross-match.
    ("$humanize-korean", "/humanize-korean"),
    ("$humanizer", "/humanizer"),
    # v0.1.14 pins roadmap commit identities to task-scoped shell variables.
    # They are environment overrides in a `git -c` command, not skill sigils,
    # so they take the uppercase spelling that style implies; uppercase names
    # are also deliberately outside the lowercase sigil scan.
    ("aquarium_commit_name", "AQUARIUM_COMMIT_NAME"),
    ("aquarium_commit_email", "AQUARIUM_COMMIT_EMAIL"),
    ("`request_user_input`", "`AskUserQuestion`"),
    # ZCode tracks work through its todo list, so the Codex goal maps onto it.
    ("Codex goal", "ZCode todo list"),
    # v0.1.15's Podway integration reference tracks completion against "the
    # Codex objective" — the goal object's user-facing name on the upstream
    # host. It maps onto the same todo-list surface here, as does the
    # contract of the tool that owns it.
    ("Codex objective", "ZCode todo-list objective"),
    (
        "follow the current Codex tool contract",
        "follow the current host todo-list contract",
    ),
    # v0.1.15's bundle skill prepares Ouroboros once per discovered Codex
    # home. This host has one integration surface, so the preparation unit
    # is that single surface.
    (
        "one CLI upgrade and one integration update per distinct discovered "
        "Codex home, not one installation per repository",
        "one CLI upgrade and one single-surface ZCode integration update, not "
        "one installation per repository",
    ),
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
    # v0.1.14 rewrites the shared review contract around Dolgorae captures and
    # six source scopes. independent-review keeps running on the host's own
    # Agent tool here, so its half of the contract is restated for that
    # backend: four inspector-backed scopes, blob-bound targets, and no
    # capture machinery. The Orca half of the contract stays accurate as
    # written. `workspace` and `dirty` need an immutable capture that neither
    # backend provides on this host, so they are unsupported for both.
    (
        "| Dolgorae capture | Unsupported |",
        "| Unsupported | Unsupported |",
    ),
    (
        "reviewed through `git diff --cached`. | Dolgorae capture |",
        "reviewed through `git diff --cached`. | Live index read |",
    ),
    (
        "| Dolgorae capture | Current registered worktree Git reads |",
        "| Resolved commit blobs | Current registered worktree Git reads |",
    ),
    (
        "Independent Review uses Dolgorae's checked immutable capture as target authority. "
        "Its complete candidate, capture, manifest, path-safety, lifecycle, settlement, and "
        "recovery rules are defined by [dolgorae-review-contract.md](dolgorae-review-contract.md).",
        "Independent Review binds each reviewer to the target inspector's dispatch-time "
        "digest and, for committed scopes, to resolved commit blobs rather than later "
        "working-tree copies; that binding is its target authority. `workspace` and `dirty` "
        "require an immutable capture this backend does not provide, so they stay "
        "unsupported here; [dolgorae-review-contract.md](dolgorae-review-contract.md) "
        "documents the upstream backend this edition does not use.",
    ),
    (
        "`independent-review` uses one guarded Dolgorae `specialist.review` v2 operation "
        "to capture the target and run one fresh Codex Reviewer. It creates and accepts no "
        "Orca Run, Task, Dispatch, worker, terminal, context, or worktree. Missing or "
        "invalid Dolgorae state fails closed without Orca fallback.",
        "`independent-review` dispatches fresh reviewer subagents through the host's own "
        "Agent tool against the selected Git target. It creates and accepts no Orca Run, "
        "Task, Dispatch, worker, terminal, context, or worktree. A missing, failed, or "
        "otherwise unusable subagent dispatch fails closed without provider fallback.",
    ),
    # v0.1.15 rewords settlement around same-release `$use-dolgorae`
    # delegation. The Agent-tool backend here has no provider lifecycle to
    # delegate to, so the restated half keeps dispatch/review separation
    # and the explicit-user-request boundary for waiting or re-dispatch.
    (
        "Independent Review delegates settlement and recovery to the "
        "same-release `/use-dolgorae` skill and Dolgorae's checked contract. "
        "Orca Review follows its live Orca guides and "
        "[orca-supervision.md](orca-supervision.md), including authoritative "
        "observation on deadline exhaustion.",
        "Independent Review keeps technical review status separate from dispatch "
        "status, never retries an active or unknown reviewer automatically, and "
        "treats further waiting or a re-dispatch as an explicit user request. "
        "Orca Review follows its live Orca guides and "
        "[orca-supervision.md](orca-supervision.md), including authoritative "
        "observation on deadline exhaustion.",
    ),
    (
        "Independent Review additionally returns its target digest, capture, manifest, "
        "source-mutation observation, target-integrity result, and Dolgorae settlement "
        "evidence.",
        "Independent Review additionally returns its target digest, the dispatch-time index "
        "observation for a `staged` target, any later source-mutation observation, and "
        "separate dispatch and reviewer status.",
    ),
    (
        "`workspace` and `dirty` remain outside this workflow. Use "
        "`/aquarium:independent-review` when one of those scopes is required.",
        "`workspace` and `dirty` remain outside this workflow; they require an immutable "
        "capture no backend here provides.",
    ),
    # The aquarium-dev channel is upstream-ecosystem tooling, but its setup
    # prohibitions name the host, and the host here is ZCode. Its plugin
    # artifacts are equally never installed into this host's plugin cache,
    # so that boundary broadens past the upstream Codex home.
    ("configure Codex", "configure ZCode"),
    ("Codex configuration", "ZCode configuration"),
    (
        "are never installed into a Codex home by this workflow",
        "are never installed into any host's plugin home by this workflow",
    ),
    # v0.1.15 moves the aquarium-dev channel into `tools/aquarium-dev` and a
    # shared development contract reference. Its restart sentence and its
    # launcher/manager boundary clauses name the host, and the host here is
    # ZCode.
    ("Restart Codex after installation or update.", "Restart ZCode after installation or update."),
    (
        "has no Codex-home configuration, authentication, plugin installation, "
        "or MCP configuration operation",
        "has no host configuration, authentication, plugin installation, or "
        "MCP configuration operation",
    ),
    (
        "The launcher does not read or mutate Codex authentication, plugins, "
        "skills, apps, or MCP configuration.",
        "The launcher does not read or mutate the host's authentication, "
        "plugins, skills, or MCP configuration.",
    ),
    # The shared disposition contract's re-review sentence describes both
    # capture-owning backends; Independent Review here rebinds a fresh
    # dispatch instead, so the sentence must not claim a native capture.
    (
        "Independent Review and Mulgae create fresh native captures.",
        "Independent Review rebinds a fresh reviewer dispatch to the "
        "corrected target; Mulgae creates a fresh native capture.",
    ),
    # The upstream Dolgorae consumer contract ships as documentation of the
    # backend this edition does not use; its opening must say so instead of
    # asserting a binding every shipped workflow here denies. v0.1.15 raises
    # the documented floor to v0.1.2, so the needle tracks it.
    (
        "This contract binds Aquarium review workflows to official stable "
        "Dolgorae releases from v0.1.2 through v0.1.x on Apple Silicon.",
        "This contract documents the upstream backend this edition does not "
        "use: no review workflow shipped here runs Dolgorae. Upstream binds "
        "its Aquarium review workflows to official stable Dolgorae releases "
        "from v0.1.2 through v0.1.x on Apple Silicon.",
    ),
    # v0.1.15 routes explicitly requested reviews and External Specialist
    # Engagements through the paired `$use-dolgorae` skill. This edition
    # dispatches those through the host's own `Agent`-tool subagents, so the
    # guidance bullet keeps the third-party skill only for Dolgorae-native
    # lifecycle operations the backend cannot serve.
    (
        "- Use `/use-dolgorae` for explicitly requested workspace, global "
        "Profile, review, External Specialist Engagement, and recovery "
        "operations. Keep execution and lifecycle rules in the paired skill.",
        "- Route explicitly requested reviews and External Specialist "
        "Engagements through fresh reviewer subagents dispatched with the "
        "host's own `Agent` tool. Use `/use-dolgorae` only for an explicitly "
        "requested Dolgorae-native workspace, global Profile, or recovery "
        "operation, and keep its execution and lifecycle rules in that paired "
        "skill.",
    ),
    # v0.1.15 restates Ouroboros readiness around per-Codex-home rows. This
    # host has one integration surface — the user-global config registration
    # and the ZCode skill root — so the reference's readiness sentence is
    # restated for that shape (the global inspector reports it under
    # `integration`; see the `inspect_ouroboros` surgery).
    (
        "Use the global v2 inspector's `current_home_readiness`, not "
        "`all_discovered_homes_readiness`. Require rules and skills in the "
        "current Codex home, the matching MCP package, and a `home_binding` "
        "to that same home; shared `~/.agents/skills` copies do not satisfy "
        "readiness.",
        "Use the global inspector's single `integration` result: the "
        "user-global `mcp.servers` registration in `~/.zcode/cli/config.json`, "
        "its runtime configuration, the matching MCP package, and the "
        "installed user-scoped skills. On this host the shared "
        "`~/.agents/skills` root is the canonical skill target, not a legacy "
        "location, so copies there count toward readiness.",
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
        try:
            candidates.append(Path(codex_home).expanduser().joinpath("skills"))
        except (OSError, ValueError, RuntimeError):
            pass
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
    # v0.1.15 adds a `trusted_global_skills` presence map inside `inspect()`
    # that still resolves `humanize-korean` through the Codex home — the same
    # upstream bug the `inspect_im_not_ai` surgery already corrects (upstream
    # fixed its own copy after v0.1.15, unreleased). The map entry is pinned
    # to the shared `~/.agents/skills` root, and the deletion of
    # `effective_codex_skill_root` below would otherwise leave a dangling
    # reference here.
    (
        '            "humanize-korean": effective_codex_skill_root() / "humanize-korean",',
        '            "humanize-korean": Path.home() / ".agents/skills/humanize-korean",',
    ),
    # The aquarium-dev MCP runtime reads the plugin's own manifest to bind
    # its source identity. In the generated tree that manifest is the ZCode
    # one, so the literal path moves with it.
    (
        '    manifest = directory.parent.parent / ".codex-plugin/plugin.json"',
        '    manifest = directory.parent.parent / ".zcode-plugin/plugin.json"',
    ),
    # `tools/aquarium-dev/mcp_server.py` states its own tool boundary in the
    # instructions every MCP client shows; the host it must not configure is
    # the one running this plugin.
    ("configures Codex", "configures ZCode"),
    # The restated global Ouroboros inspector keeps upstream's module
    # docstring shape, but its per-Codex-home wording describes machinery
    # the surgery below removes, so the docstring moves with it.
    (
        '"""Read-only Ouroboros package and per-Codex-home inspection."""',
        '"""Read-only Ouroboros package and single-surface ZCode inspection."""',
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
            "ouroboros_isolated_launcher_matches": r'''ZCODE_OUROBOROS_RUNTIME_VALUES = ("zcode", "codex")


def ouroboros_isolated_launcher_matches(transport: Any) -> bool:
    # The isolated `uvx` launcher shape is host-neutral; the runtime selectors
    # are not. On this host the selectors must name one coherent runtime —
    # `zcode`, the runtime this artifact proposes, or `codex`, valid when that
    # CLI is the configured Ouroboros backend — through the environment keys
    # or the exact command suffix. Upstream's copy of this matcher accepts the
    # codex value only, because it classifies registrations for the upstream
    # host.
    if not isinstance(transport, dict) or transport.get("type") != "stdio":
        return False
    resolved_command = resolved_executable(transport.get("command"))
    selected_uvx = shutil.which("uvx")
    if not resolved_command or not selected_uvx:
        return False
    if resolved_command != Path(selected_uvx).resolve():
        return False

    args = transport.get("args")
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        return False
    normalized_args = list(args)
    if len(normalized_args) < 5:
        return False
    package_match = OUROBOROS_MCP_PACKAGE.fullmatch(normalized_args[4])
    if not package_match:
        return False
    pinned_version = package_match.group(1)
    if pinned_version and not supported_ouroboros_version(pinned_version):
        return False
    normalized_args[4] = "ouroboros-ai[mcp]"

    env = transport.get("env", {})
    if not isinstance(env, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in env.items()
    ):
        return False
    if "_OUROBOROS_NESTED" in env:
        return False
    if set(env) - OUROBOROS_RUNTIME_SELECTOR_KEYS:
        return False
    env_selected = {
        env.get(key)
        for key in OUROBOROS_RUNTIME_SELECTOR_KEYS
        if env.get(key) is not None
    }
    if len(env_selected) > 1:
        return False
    env_runtime = next(iter(env_selected)) if env_selected else None
    if env_runtime is not None and env_runtime not in ZCODE_OUROBOROS_RUNTIME_VALUES:
        return False

    normalized = tuple(normalized_args)
    if normalized == OUROBOROS_UVX_MCP_ARGS:
        return (
            env.get("OUROBOROS_AGENT_RUNTIME") is not None
            and env.get("OUROBOROS_LLM_BACKEND") is not None
            and env_runtime in ZCODE_OUROBOROS_RUNTIME_VALUES
        )
    for runtime_value in ZCODE_OUROBOROS_RUNTIME_VALUES:
        if env_runtime is not None and runtime_value != env_runtime:
            continue
        suffix = ("--runtime", runtime_value, "--llm-backend", runtime_value)
        if normalized == (*OUROBOROS_UVX_MCP_ARGS, *suffix):
            return True
    return False
''',
            "inspect_ouroboros": r'''def ouroboros_mcp_registration(
    repository: Path, ouroboros_executable: str | None
) -> dict[str, Any]:
    # ZCode has no `mcp get` CLI probe; registrations live in
    # `~/.zcode/cli/config.json` (user level) and `.zcode/config.json`
    # (project level, which overrides the user entry on a name collision),
    # under the `mcp.servers` object. Classification follows the launcher
    # contract: the entry must be stdio and match either the direct
    # `ooo mcp serve` form or the canonical isolated `uvx` launcher with one
    # coherent runtime selector value.
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
    if not isinstance(entry, dict) or entry.get("type", "stdio") != "stdio":
        return {
            "status": "degraded",
            "probe": probe,
            "scope": scope,
            "reason": "registration_not_stdio",
        }
    if entry.get("enabled") is False:
        return {
            "status": "degraded",
            "probe": probe,
            "scope": scope,
            "reason": "registration_disabled",
        }
    if ouroboros_direct_launcher_matches(entry, ouroboros_executable):
        return {
            "status": "configured",
            "probe": probe,
            "scope": scope,
            "launcher": "direct",
        }
    if ouroboros_isolated_launcher_matches(entry):
        # The pinned package version is reported for the runtime-package
        # axis upstream derives from the registration transport; the
        # matcher has already validated its shape, so only the pin is
        # re-read here.
        pin = None
        args = entry.get("args")
        if isinstance(args, list) and len(args) > 4 and isinstance(args[4], str):
            package_match = OUROBOROS_MCP_PACKAGE.fullmatch(args[4])
            pin = package_match.group(1) if package_match else None
        return {
            "status": "configured",
            "probe": probe,
            "scope": scope,
            "launcher": "isolated",
            "pinned_version": pin,
        }
    return {
        "status": "degraded",
        "probe": probe,
        "scope": scope,
        "reason": "registration_mismatch",
    }


def inspect_ouroboros(
    repository: Path,
    timeout_seconds: float,
    *,
    codex_home: Path | None = None,
    cli_observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # ZCode has no Codex-home model: Ouroboros' integration surface here is
    # the user-global `mcp.servers` entry of `~/.zcode/cli/config.json`
    # plus the `~/.ouroboros/config.yaml` runtime config `ooo setup
    # --runtime zcode` manages. `codex_home` is accepted for signature
    # compatibility with upstream's per-home callers and never specializes
    # the result; `cli_observation` reuses a caller's CLI probe exactly as
    # upstream's form does.
    tool = (
        dict(cli_observation)
        if cli_observation is not None
        else inspect_ouroboros_cli(repository, timeout_seconds)
    )
    tool["supported_range"] = ">=0.51.1,<0.54.0"
    tool["mcp_registration"] = ouroboros_mcp_registration(
        repository, tool["executable"]
    )
    launcher = tool["mcp_registration"].get("launcher")
    # Ouroboros registers its skills with the host agent, so the component
    # whose health this integration adds on this host is the config
    # registration resolved above.
    tool["host_integration"] = {
        "status": tool["mcp_registration"]["status"],
        "probe": tool["mcp_registration"]["probe"],
    }
    # The runtime-package axis mirrors upstream's: an isolated launcher pins
    # the MCP package version it runs, a direct launcher selects the
    # installed CLI, and any other shape leaves the package unverifiable.
    tool["runtime_package"] = {"status": "unverifiable", "version": None}
    if launcher == "isolated":
        pinned = tool["mcp_registration"].get("pinned_version")
        if pinned:
            tool["runtime_package"] = {
                "status": "pinned" if pinned == tool.get("version") else "different",
                "version": pinned,
            }
    elif launcher == "direct":
        tool["runtime_package"] = {
            "status": "selected_cli",
            "version": tool.get("version"),
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

    launcher = tool["mcp_registration"].get("launcher")
    if launcher == "isolated":
        # The canonical isolated launcher runs the MCP 2 server in its own
        # package environment; the base CLI's doctor would inspect an
        # unrelated environment, so the launcher contract itself establishes
        # runtime configuration.
        tool["mcp_runtime"] = {
            "status": "configured",
            "reason": "isolated_launcher_contract",
            "probe": skipped_probe("isolated_environment_not_probed"),
        }
    elif launcher == "direct":
        mcp_doctor = json_probe(
            [tool["executable"], "mcp", "doctor", "--json"],
            repository,
            timeout_seconds,
        )
        # The MCP 2 server registered in config launches as a separate process
        # while the CLI environment keeps MCP 1.x, so the doctor's
        # `mcp_import` check — and the exit code with it — fails on a
        # correctly configured machine. The remaining checks carry runtime
        # health here; the server's own health is the registration component.
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
    else:
        # Without a matching launcher there is no package environment whose
        # health would be this server's runtime configuration; probing the
        # base CLI would inspect an unrelated environment.
        reason = tool["mcp_registration"].get("reason", "registration_not_found")
        tool["mcp_runtime"] = {
            "status": "missing" if reason == "registration_not_found" else "unverifiable",
            "reason": reason,
            "probe": skipped_probe(reason),
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
            # v0.1.14 adds im-not-ai inspection against upstream's
            # `effective_codex_skill_root()`, which resolves the writing-skill
            # target through the Codex home. ZCode reads the shared
            # `~/.agents/skills` root natively and knows no equivalent config
            # environment, so the target is that shared root and the deleted
            # Codex-home resolver is replaced by a ZCode-named helper bundled
            # ahead of the inspector that uses it.
            "inspect_im_not_ai": r'''def effective_writing_skill_root() -> Path:
    # The Humanizer pair installs user-scoped, and the shared
    # `~/.agents/skills` root is the cross-agent root ZCode reads natively,
    # so it is the canonical writing-skill target on this host.
    return Path.home() / ".agents" / "skills"


def inspect_im_not_ai() -> dict[str, Any]:
    return inspect_writing_skill(
        skill_name="humanize-korean",
        expected_files=HUMANIZE_KOREAN_SKILL_FILES,
        expected_target=effective_writing_skill_root() / "humanize-korean",
        supported_release=IM_NOT_AI_SUPPORTED_RELEASE,
        require_version=False,
    )
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
            "effective_codex_skill_root",
        ],
    },
    # v0.1.15 adds a user-global diagnosis skill that reuses the project
    # inspector across file boundaries. Its global MCP view calls the
    # codex-CLI probe functions the plan above deletes from that inspector,
    # so it is restated on the config-file scopes the inspector exposes.
    "skills/dev-setup-global/scripts/inspect_global_tools.py": {
        "replace": {
            "inspect_global_mcp": r'''def inspect_global_mcp(
    inspector: Any,
    name: str,
    executable: str | None,
    root: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    # ZCode has no `mcp` CLI to probe; the user-global registration is the
    # `mcp.servers` entry of `~/.zcode/cli/config.json`, which the project
    # inspector reads directly. Reading from the filesystem-root cwd keeps
    # any repository `.zcode/config.json` out of the global view, mirroring
    # the neutral-cwd probe upstream runs through its host CLI.
    neutral_cwd = Path(root.anchor)
    reading = inspector.zcode_mcp_entries(name, neutral_cwd)
    if reading["invalid_config"]:
        return {
            "status": "degraded",
            "reason": f"{reading['invalid_config']}_config_invalid_json",
        }
    return inspector.zcode_mcp_scope_status(reading["scopes"]["user"], executable)
''',
        },
    },
    # v0.1.15 inspects Ouroboros per Codex home: discover `~/.codex*` homes,
    # probe each through the codex CLI, and bind registrations to a home.
    # This host has one integration surface — the user-global config
    # registration and the ZCode skill root — so the home machinery is
    # restated as a single integration row, and `legacy_skills` becomes the
    # shared-root inventory: on this host `~/.agents/skills` is the
    # canonical Ouroboros skill target, not a legacy location.
    "skills/dev-setup-global/scripts/inspect_ouroboros.py": {
        "replace": {
            "inspect_ouroboros": r'''def inspect_ouroboros(
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
    # applicable rather than silently filtered.
    cli = inspector.inspect_ouroboros_cli(cwd, timeout)
    integration = inspector.inspect_ouroboros(cwd, timeout)
    assets = packaged_assets(inspector, cli, cwd, timeout)
    freshness = (
        release_freshness(inspector, cli, timeout)
        if verify_release
        else {"status": "not_checked", "source": PYPI_URL}
    )
    return {
        "status": "missing" if not cli["installed"] else integration["status"],
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
        "freshness": freshness,
        "shared_root_skills": legacy_skills(assets),
    }
''',
        },
        "delete": [
            "discover_homes",
            "inspect_home",
            "unavailable_home",
            "inspect_artifacts",
            "artifact_targets",
            "artifact_paths",
            "directory_entries",
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
    ("skills/dev-setup/scripts/inspect_tools.py", "ZCODE_OUROBOROS_RUNTIME_VALUES"),
    ("skills/dev-setup/scripts/inspect_tools.py", "registration_mismatch"),
    ("skills/dev-setup/scripts/inspect_tools.py", "isolated_launcher_contract"),
    ("skills/dev-setup/scripts/inspect_tools.py", '"host_integration"'),
    ("skills/dev-setup/scripts/inspect_tools.py", "doctor_checks_failed"),
    ("skills/dev-setup/scripts/inspect_tools.py", "effective_writing_skill_root"),
    ("skills/dev-setup/scripts/inspect_tools.py", '"runtime_package"'),
    ("skills/dev-setup/scripts/inspect_tools.py", '"pinned_version"'),
    # The test-setup inspector ships host-neutral from upstream; this marker
    # guards that it arrives whole rather than transformed away.
    (
        "skills/test-setup/scripts/inspect_testing.py",
        "aquarium-test-setup-inspection.v1",
    ),
    # The v0.1.12 rewrites and the newer host-neutral inspectors also ship
    # host-neutral from upstream; the same marker guard applies to each.
    (
        "skills/docs-setup/scripts/inspect_docs.py",
        "aquarium-docs-inspection/v2",
    ),
    (
        "skills/release-handler/scripts/inspect_publication_state.py",
        "aquarium-release-publication-state/v4",
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
        "skills/release-qa/scripts/manage_release_qa.py",
        "aquarium-release-qa-full-pass/v1",
    ),
    # v0.1.14 adds the Dolgorae release verifier; v0.1.15 moves it beside
    # the new global inspector. Each ships host-neutral from upstream, so
    # the same arrival guard applies.
    (
        "skills/dev-setup-global/scripts/verify_dolgorae_release.py",
        "aquarium-dolgorae-release-verification.v1",
    ),
    # v0.1.15 replaces the aquarium-dev skill with a bundled CLI + MCP
    # package under `tools/aquarium-dev`; the channel scripts ship
    # host-neutral from upstream, so the arrival guards move with them.
    (
        "tools/aquarium-dev/aquarium_dev.py",
        "aquarium-dev-manager-result/v1",
    ),
    (
        "tools/aquarium-dev/aquarium_dev_launcher.py",
        "aquarium-dev-artifact-manifest/v2",
    ),
    (
        "tools/aquarium-dev/build_aquarium_artifact.py",
        "aquarium-dev-producer-description/v1",
    ),
    (
        "tools/aquarium-dev/dev_contract.py",
        "aquarium-dev-producer-description/v1",
    ),
    (
        "tools/aquarium-dev/dev_manager.py",
        "aquarium-dev-enrollment/v1",
    ),
    (
        "tools/aquarium-dev/runtime_entry.py",
        "aquarium-dev-runtime/v1",
    ),
    # The runtime entry binds the bundled package to the plugin's own
    # manifest, which is the ZCode one in the generated tree; this marker
    # guards the substitution that retargets it.
    (
        "tools/aquarium-dev/runtime_entry.py",
        '".zcode-plugin/plugin.json"',
    ),
    (
        "tools/aquarium-dev/install.py",
        "aquarium-dev-runtime-inspection/v1",
    ),
    (
        "tools/aquarium-dev/mcp_server.py",
        "Manage the Aquarium development channel",
    ),
    # v0.1.15's user-global inspector ships one host-neutral entrypoint and
    # the two restated ZCode views the surgery plans above produce.
    (
        "skills/dev-setup-global/scripts/inspect_global_tools.py",
        "aquarium-dev-setup-global-inspection.v3",
    ),
    (
        "skills/dev-setup-global/scripts/inspect_global_tools.py",
        "zcode_mcp_entries",
    ),
    (
        "skills/dev-setup-global/scripts/inspect_ouroboros.py",
        "no_per_home_integration_on_zcode",
    ),
    ("hooks/task_commit_gate.py", "/aquarium:task-commit"),
    ("hooks/hooks.json", "${ZCODE_PLUGIN_ROOT}"),
    # v0.1.15 registers the aquarium-dev MCP server through a root
    # `.mcp.json`; `write_mcp_manifest` derives the ZCode form, and these
    # markers guard the schema conversion and the template rooting.
    (".mcp.json", '"mcpServers"'),
    (".mcp.json", "${ZCODE_PLUGIN_ROOT}/tools/aquarium-dev/mcp-launcher"),
    (".mcp.json", '"timeoutMs": 3600000'),
)

# Strings that must not survive into the generated tree, scanned across the
# whole generated plugin. Each entry pairs a needle with the remedy, so a
# failure names its own fix.
FORBIDDEN: tuple[tuple[str, str], ...] = (
    ("$aquarium:", "add a substitution rule"),
    ("$use-", "add a substitution rule"),
    ("$create-", "add a substitution rule"),
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


def copy_edition_skills(destination: Path) -> list[str]:
    """Carry this edition's own skills into the generated tree.

    Edition skills have no upstream counterpart: they are authored here and
    shipped through the plugin. Placing one straight into
    `plugins/aquarium/` would lose it, because regeneration replaces that
    tree wholesale. Like an override, an edition skill is hand-authored
    final content and runs after the substitutions; unlike an override it
    adds a directory rather than replacing a file. A name collision with an
    upstream skill stops the run: upstream would otherwise silently win or
    lose by copy order, and either outcome hides a decision.
    """
    if not EDITION_SKILLS.is_dir():
        raise SyncError(
            f"{EDITION_SKILLS} is missing; this edition owns at least the "
            "`upgrade` skill"
        )
    skills = destination / "skills"
    copied: list[str] = []
    for entry in sorted(EDITION_SKILLS.iterdir()):
        if not entry.is_dir():
            raise SyncError(
                f"edition-skills holds the non-directory entry `{entry.name}`; "
                "an edition skill is a directory with a SKILL.md"
            )
        if not (entry / "SKILL.md").is_file():
            raise SyncError(f"edition skill `{entry.name}` has no SKILL.md")
        target = skills / entry.name
        if target.exists():
            raise SyncError(
                f"edition skill `{entry.name}` collides with an upstream skill "
                "of the same name; rename the edition skill"
            )
        shutil.copytree(entry, target)
        copied.append(entry.name)
    return copied


def tune_skill_descriptions(destination: Path) -> list[str]:
    """Apply the tuned trigger surface to every generated skill.

    The frontmatter description is the only skill surface the host exposes
    to the model, so this edition tunes it for that surface: the purpose
    sentence first, the `/aquarium:<name>` invocation present, a kept
    `Use when` trigger, and a shorter whole. Each entry records the SHA-256
    of the pre-tuning description — the value upstream plus substitutions
    and overrides produced — so an upstream or override change to any
    description stops the run until the tuning is re-derived, exactly like a
    file override. A skill without an entry also stops the run: partial
    tuning would leave inconsistent trigger conventions.
    """
    if not SKILL_DESCRIPTIONS.is_file():
        raise SyncError(
            f"{SKILL_DESCRIPTIONS} is missing; record one entry per skill"
        )
    recorded = json.loads(SKILL_DESCRIPTIONS.read_text(encoding="utf-8"))
    tuned: list[str] = []
    skills = destination / "skills"
    for skill in sorted(path for path in skills.iterdir() if path.is_dir()):
        name = skill.name
        entry = recorded.get(name)
        if not isinstance(entry, dict) or set(entry) != {
            "source_digest",
            "description",
        }:
            raise SyncError(
                f"skill `{name}` has no tuning entry carrying `source_digest` "
                "and `description`; re-derive overrides/skill-descriptions.json"
            )
        path = skill / "SKILL.md"
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        description_lines = [
            (index, line)
            for index, line in enumerate(lines)
            if line.startswith("description:")
        ]
        if len(description_lines) != 1:
            raise SyncError(
                f"skill `{name}` frontmatter has no single description line"
            )
        index, line = description_lines[0]
        current = line[len("description:") :].strip()
        if digest_text(current) != entry["source_digest"]:
            raise SyncError(
                f"tuned description stale: `{name}` changed upstream or in an "
                "override; re-derive overrides/skill-descriptions.json"
            )
        replacement = entry["description"]
        if f"/aquarium:{name}" not in replacement or "Use when" not in replacement:
            raise SyncError(
                f"tuned description for `{name}` must keep the invocation name "
                "and a `Use when` trigger"
            )
        lines[index] = f'description: "{replacement}"\n'
        path.write_text("".join(lines), encoding="utf-8")
        tuned.append(name)
    extra = sorted(set(recorded) - set(tuned))
    if extra:
        raise SyncError(
            "overrides/skill-descriptions.json names skills the tree does not "
            "generate: " + ", ".join(extra)
        )
    return tuned


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
    in the root `marketplace.json` entry instead. Upstream v0.1.15 also
    points its manifest at the MCP file through a `mcpServers` path; that
    key is deliberately absent here because ZCode auto-loads a root
    `.mcp.json` directly, and its documented manifest forms are a directory,
    an array, or inline objects — not a file path. `write_mcp_manifest`
    owns the derived file.
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


def write_mcp_manifest(destination: Path) -> None:
    """Derive the ZCode plugin MCP manifest from the upstream Codex one.

    Upstream v0.1.15 registers the bundled `aquarium-dev` MCP server in a
    root `.mcp.json` using the Codex host's field names. ZCode auto-loads
    the same filename from the plugin root but reads a different schema —
    a top-level `mcpServers` object with stdio `command`/`args`/`cwd`/
    `env`/`timeoutMs` — and drops a server outright when it carries an
    unknown key, so the fields are converted rather than copied. Plugin
    MCP is also the one scope where ZCode expands `${...}` templates, and
    `${ZCODE_PLUGIN_ROOT}` is the same anchor the hooks contract uses, so
    the launcher command and cwd are rooted there instead of a relative
    path the host may not resolve.
    """
    source = UPSTREAM_PLUGIN / ".mcp.json"
    if not source.is_file():
        raise SyncError(
            "upstream no longer ships a root .mcp.json; re-derive the ZCode "
            "MCP manifest conversion"
        )
    payload = json.loads(source.read_text(encoding="utf-8"))
    servers = payload.get("mcp_servers")
    if not isinstance(servers, dict) or not servers:
        raise SyncError(
            "upstream .mcp.json carries no `mcp_servers` object; re-derive "
            "the ZCode MCP manifest conversion"
        )
    converted: dict[str, Any] = {}
    for name, entry in sorted(servers.items()):
        if not isinstance(entry, dict):
            raise SyncError(f"upstream .mcp.json server `{name}` is not an object")
        unknown = sorted(set(entry) - {"command", "args", "cwd", "tool_timeout_sec"})
        if unknown:
            raise SyncError(
                f"upstream .mcp.json server `{name}` carries fields this "
                "conversion does not handle: " + ", ".join(unknown)
            )
        command = entry["command"]
        if not isinstance(command, str) or not command.startswith("./"):
            raise SyncError(
                f"upstream .mcp.json server `{name}` command is not a "
                "plugin-relative `./` path; re-derive the conversion"
            )
        zcode_entry: dict[str, Any] = {
            "type": "stdio",
            "command": "${ZCODE_PLUGIN_ROOT}/" + command[2:],
            "args": entry.get("args", []),
        }
        if "cwd" in entry:
            zcode_entry["cwd"] = "${ZCODE_PLUGIN_ROOT}"
        if "tool_timeout_sec" in entry:
            zcode_entry["timeoutMs"] = entry["tool_timeout_sec"] * 1000
        converted[name] = zcode_entry
    (destination / ".mcp.json").write_text(
        json.dumps({"mcpServers": converted}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
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


def generate(staged_root: Path) -> tuple[str, list[str], list[str]]:
    commit = upstream_commit()
    codex_exemptions = load_codex_exemptions()
    plugin = staged_root / "plugins" / "aquarium"
    plugin.mkdir(parents=True)
    copy_tree(plugin)
    transform_text(plugin)
    # Overrides replace whole files, so they run after the substitutions: an
    # override is hand-authored final content, not text to rewrite. Edition
    # skills are final content too, but additive: they land after the
    # overrides and before the description tuning, so the tuning layer owns
    # the final description surface for every skill, edition or upstream.
    overrides = apply_overrides(plugin)
    edition_skills = copy_edition_skills(plugin)
    tune_skill_descriptions(plugin)
    transform_skills(plugin)
    write_plugin_manifest(plugin)
    write_mcp_manifest(plugin)
    validated_exemptions = validate_codex_exemptions(plugin, codex_exemptions)
    check_forbidden(plugin, validated_exemptions)
    check_sigils(plugin)
    check_required(plugin)
    write_sync_manifest(plugin, upstream_manifest()["repository"], commit, overrides)
    return commit, overrides, edition_skills


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
            commit, overrides, edition_skills = generate(staged)

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
    print(f"  {len(edition_skills)} edition skills applied: " + ", ".join(edition_skills))
    return 0


if __name__ == "__main__":
    sys.exit(main())
