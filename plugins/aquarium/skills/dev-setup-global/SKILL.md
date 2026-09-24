---
name: dev-setup-global
description: "Diagnose, install, and update supported user-global development tools and integrations, excluding the Aquarium plugin itself. Use when the user invokes /aquarium:dev-setup-global or a workflow reports a missing global CLI, paired skill, MCP registration, service, or Ouroboros component. Repository-local configuration belongs to /aquarium:dev-setup."
---

# Global Development Setup

Own installation, exact-upstream freshness, upgrades, services, and global ZCode integration for the supported components listed below without inspecting or changing repository configuration.

## Check Request Scope Before Loading References

Aquarium plugin installation and updates belong to the host's plugin-management flow. A request to install or update only the Aquarium plugin, including a specific version, does not select this skill. If this skill was selected for that request, return to the host's plugin-management flow before reading the tool catalog or running any diagnostic. Do not infer a global tool setup request from plugin installation.

Use this skill for an explicit global development setup request or a workflow continuation naming a global component that needs attention. The upstream-bundled `aquarium-dev` development channel and `aquarium-status` production-status reporter are not shipped in this edition, and their machine-global state has exactly one owner — the upstream Codex edition — so an install, update, or repair request for either runtime belongs there, not here; installing or updating the Aquarium plugin alone does not request either runtime either.

Read the selected sections of [the shared tool catalog](../../references/tool-catalog.md). Do not read repository-local `.podway`, `.mulgae`, `.gaori`, `.sorage`, `.zcode`, AGENTS.md, or CLAUDE.md as global setup evidence.

## Diagnose Automatically

1. On a direct invocation without a component list, select every supported global component. On a scoped continuation, select only the named components and their direct prerequisites.
2. A direct invocation authorizes bounded read-only official metadata and raw-file freshness requests for all selected components. A scoped continuation authorizes only its selected sources. Disclose the official endpoints before contact.
3. Resolve this skill's directory and run `python3 <skill-directory>/scripts/inspect_global_tools.py` on a direct unscoped invocation. For a scoped continuation, add one `--component <name>` argument for each selected component in catalog order and run no unselected component probe.

   When Ouroboros is selected, also add `--verify-ouroboros-release`. This host has one Ouroboros integration surface, so the inspector reports it as a single `integration` result; any explicitly supplied extra home through `--codex-home <path>` names another host's layout and is reported as not applicable.

   Outside Plan Mode, disclose the Sorage open-and-migrate diagnostic side effect, then add `--include-sorage-initialization` when Sorage is selected. The same disclosure applies to a scoped Sorage continuation.
4. Treat `--repository <existing-directory>` only as a compatibility input. Validate that it is an existing directory, but never use it as command or configuration scope, so diagnosis also works outside a Git worktree.
5. Diagnose local installation, supported version, canonical target, exact-upstream tree, duplicate and symlink state, paired-skill compatibility, services, global MCP, and Ouroboros integration independently.
6. Do not ask the user to choose install, diagnose, or skip. Report current components without a question and propose actions only for missing, incompatible, unsafe, duplicated, or stale components.

If a freshness lookup, download, validation, or comparison fails, report `freshness_unverifiable`, clean ephemeral payloads, and do not propose installation or replacement from that payload.

## Owned Components

- Sanho, Dolgorae, Mulgae, Gaori, Sorage, and Podway user-global CLIs.
- `use-sanho`, `use-dolgorae`, `use-mulgae`, `use-gaori`, `use-gaori-status`, `use-sorage`, and `use-podway` under `~/.agents/skills`.
- Mulgae and Gaori user-global MCP registrations in the `mcp.servers` object of `~/.zcode/cli/config.json`.
- Podway's per-user production daemon and Sorage's minimal user-global initialization.
- Lora's `lore-commits` and `lore-query`, upstream Deslop, Humanizer, and im-not-ai's `humanize-korean` skill.
- Ouroboros package version, user-scoped skills under the ZCode skill root, MCP runtime, effective user-global registration, and live exposure when safely observable.
- The upstream `aquarium-dev` and `aquarium-status` runtimes are not bundled with this edition. Their machine-global state — `~/.aquarium-dev/`, the `~/.aquarium` ledger and its reporter — has one owner, the upstream Codex edition, so this skill neither diagnoses nor installs either runtime and redirects requests for them there.
- Aquarium production-binary readiness requires supported global Podway, Mulgae, and Gaori executables and fails closed when any is missing. Dolgorae and Sanho remain optional and are excluded from this baseline.

Do not install provider CLIs, authenticate, read credentials, contact providers, transmit repository source, initialize repository workspaces, change project MCP, edit repository guidance, start tests or reviews, or invoke Ouroboros workflows.

## Exact-Upstream and Update Policy

Use one exact supported release tag or disclosed full commit SHA according to the shared catalog. Verify downloaded archives, manifests, checksums, signatures, frontmatter, complete regular-file trees, and expected source provenance before proposing an action. Never install from a moving branch or execute unverified fetched content.

For each selected paired or third-party skill, compare the verified source with its canonical target. Treat missing or extra files, different bytes, invalid frontmatter, symlinks, and duplicate installations as independent gaps.

Apply this duplicate rule to shared-location skills. Resolve the target from the selected upstream release's default installation guidance: use `~/.zcode/skills`, this host's native root, when it names `$CODEX_HOME`, and `~/.agents/skills` when it names no default. Ouroboros uses the single-surface contract in the catalog: its skills install under the shared `~/.agents/skills` root, a native ZCode root this host loads directly, and its registration is the user-global `mcp.servers` entry. Other agent skill roots remain diagnostic evidence only. When another copy would be loaded beside the selected target, report the duplicate risk and never create a known duplicate. Do not propose installation at the canonical target until the user separately approves removal or migration of the conflicting copy.

`dev-setup` trusting an existing canonical path is not freshness evidence.

Ouroboros update diagnosis reports installed, latest stable, and latest supported versions. Its CLI is user-global; on this host its skills install under the shared `~/.agents/skills` root and its MCP registration is the user-global `mcp.servers` entry in `~/.zcode/cli/config.json`. Upstream's per-home rows and shared-root prohibition target the Codex home model — here the shared root is native, stays canonical, and one installation must never be duplicated under both roots; a shared-root directory whose bytes match no selected package payload is a conflict to report and inspect, never a removal order. Keep integration readiness, package freshness, and live runtime evidence separate. Never install below the minimum supported version.

im-not-ai's `humanize-korean` skill also belongs to the running host's default root. Use `~/.zcode/skills/humanize-korean`. Do not install it in `~/.agents/skills`; a shared-root copy is a duplicate to report and resolve separately.

## Respect Host Mode and Approval Boundaries

In Plan Mode, perform local and network read-only diagnosis and return exact proposals without mutation. Defer Sorage doctor or initialization checks that may update its database or journal to execution mode.

Outside Plan Mode, disclose any selected Sorage diagnostic side effect before running it. Keep release lookup, archive download, executable installation, skill installation or replacement, daemon changes, Sorage initialization, global MCP changes, Ouroboros package changes, and Ouroboros setup or refresh as distinct actions.

Before every persistent action:

1. Show the exact command, endpoints, targets, changed paths, expected side effects, and verification.
2. Establish the shared backup policy before the first overwrite or removal.
3. Obtain action-specific approval. For Ouroboros, one exact proposal and approval may cover the CLI upgrade, the skill-root update, and MCP adjustments. Do not repeat approval for covered actions.
4. Re-read the target and invalidate approval if its snapshot changed.
5. Execute only the approved action and verify through the owning CLI and exact tree comparison.

## Apply the Shared Backup Policy

Use `Choose a Backup Policy for Existing State` in the shared tool catalog for every overwrite or removal. The shared policy owns the request-scoped choice, loss and recovery disclosure, restoration evidence, and the rule that preparing an incoming payload is not a backup.

Never use `sudo`, `--force`, unapproved removal, provider invocation, source transmission, staging, committing, or pushing. Tell the user when ZCode must restart.

## Bundle Intake

Accept a bounded `dev-setup-bundle` handoff containing the manifest digest and union of selected global components. This edition adds no bundle infrastructure runtime: prepare each selected global component at most once. For Ouroboros, prepare the CLI once and its single ZCode integration once. Preserve all per-action approvals and return independent results for the bundle's target processing. Never read the manifest or infer repositories.

## Report

Report every selected component as current, missing, incompatible, different, duplicated, unsafe, or freshness-unverifiable; include resolved versions and sources, exact canonical targets, actions and exit status, backup and restoration evidence, cleanup, restart requirements, and remaining gaps. State explicitly that no repository configuration, staging, commit, or publication was performed.
