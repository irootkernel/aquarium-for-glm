# Changelog

This file records concise shipped outcomes of the Aquarium for GLM edition. Releases before v0.1.14 are recorded in this repository's GitHub releases; upstream outcomes live in the [Aquarium changelog](https://github.com/irootkernel/aquarium/blob/main/CHANGELOG.md).

## v0.1.15 - Unreleased

## v0.1.14 - 2026-09-05

### Added

- Add the edition-local `/aquarium:upgrade` skill that walks one full upstream Aquarium release cycle for this repository: pin the submodule to a released tag, resolve every sync abort in order, re-derive overrides and description tunings, validate, and prepare the reviewed release and the local ZCode installation.
- Teach the generation to carry `edition-skills/` into the generated plugin: edition-owned skills ship through the plugin, stop on name collisions with upstream skills, and pass the same frontmatter, tuning, and needle checks as upstream skills.
- Ship the new `/aquarium:aquarium-dev` skill — the explicit Aquarium development channel for supported producer checkouts, with enrollment, immutable generations under `~/.aquarium-dev`, and the `~/.local/bin/aquarium-dev` launcher — as upstream wrote it; its setup prohibitions name ZCode, its plugin-artifact installation boundary broadens from a Codex home to any host's plugin home, and its references to the upstream Codex plugin artifact and Codex homes carry reviewed exemptions because they describe the producer ecosystem this channel builds.
- Add official Dolgorae v0.1.1 support to `/aquarium:dev-setup` and its catalog: bounded release-metadata verification, checksum-pinned installation, and the `verify_dolgorae_release.py` verifier, all host-neutral and carried from upstream.
- Add exact-upstream Humanizer (`v2.11.1`) and im-not-ai (`v2.3.2`) installation to `/aquarium:dev-setup`, including the `/humanizer` and `/humanize-korean` prose-guidance routing rules; im-not-ai's installer payload is materialized against an isolated temporary `CODEX_HOME` exactly as upstream requires and installed at the ZCode-readable `~/.agents/skills/humanize-korean` target.
- Apply the shared finding-disposition contract to Independent Review, so Medium-or-higher findings require correction and re-review and Low findings require an explicit disposition.

### Changed

- Restate the shared review contract for this edition's reviewer backend: Independent Review keeps dispatching fresh subagents through the host's own `Agent` tool instead of upstream's Dolgorae captures, adopts the stricter adjudication (preserved reported severity, effective priority, validity, disposition) and the no-staging consent rule, and leaves `workspace` and `dirty` scopes unsupported on both review backends because neither provides an immutable capture.
- Raise the minimum supported Podway version to v0.2.8 with named runtime modes and `podway.daemon-status-result/v3`, keep managed-Procedure removal and runtime-mode moves as explicit `/use-podway` handoffs, and update the three managed procedure sources from upstream.
- Pin roadmap commit identities to task-scoped `AQUARIUM_COMMIT_NAME`/`AQUARIUM_COMMIT_EMAIL` environment overrides, and extend the commit gate to require a repository-local or worktree Git identity before a roadmap commit.
- Port the reworked Orca Review, which reads staged, `HEAD`, commit, and range targets directly in the registered worktree with the requested native reviewer; its provider-terminal helper and repository-state snapshot scripts were removed upstream and their arrival markers retired with them.
- Extend the Ouroboros MCP surgery by one rule: the writing-skill target resolver now pins `humanize-korean` to the shared `~/.agents/skills` root instead of a Codex home.
- Require execution dossiers only for epics with at least three member tasks or three requirement-bearing canonical documents, moving dossier lifecycle policy to the new shared Epic Execution SOT reference; docs-setup structural discovery correspondingly widens to every tracked and untracked Markdown file and reports declared dossier and outcome references instead of enforcing a mandatory dossier lifecycle.

### Fixed

- Nothing beyond the upstream fixes carried by the sync (roadmap commit identity pinning and Orca Review staged-change inspection are recorded under Changed above).
