---
name: upgrade
description: "Upgrade this edition to a newly released upstream Aquarium version: pin the submodule, resolve every sync abort, re-derive overrides and description tunings, validate, and prepare the reviewed release and the local installation. Use when the user explicitly invokes /aquarium:upgrade with one released upstream version; do not use for unreleased upstream commits or unrelated repository work."
---

# Upgrade

Bring this generated edition from its pinned upstream Aquarium release to a newly released one through the repository's deterministic transformation, then release and install it behind explicit user review. The upstream submodule at `upstream/` is the source of truth and is never written to; every mutation stays in this repository.

## Establish the Request

1. Require one intended upstream release in tag form (`vX.Y.Z`). Refuse an unreleased branch or commit: upstream `main` regularly carries an open development cycle, and pinning it would ship an unstable state as a release.
2. Record the current state before touching anything: the checked-out branch and its cleanliness — a dirty tree stops the run — the pinned upstream commit from `upstream/`, the generated version in `plugins/aquarium/.zcode-plugin/plugin.json`, and the intended version.
3. Confirm the intended version is newer than the generated one. A downgrade or a re-release of the already pinned version needs an explicit user decision before continuing.
4. Create the `update/vX.Y.Z` branch from `main` when it does not already exist.

## Pin Upstream

1. Run `git -C upstream fetch --tags origin`, then `git -C upstream checkout vX.Y.Z`, and record the resolved commit hash. The tag, never a branch, is the pin.
2. Read the upstream changelog and release notes for the whole range being absorbed — one update may cross several upstream releases whose changes land at once.

## Resolve the Sync Loop

Run `python3 scripts/sync.py` repeatedly. Every abort names its own fix and stops generation rather than producing partial output; resolve one abort at a time and re-run until generation succeeds. Work the classes in this order, because earlier states gate later checks:

1. **Stale override** — an upstream file an override was derived from changed. Re-derive the override from the new upstream content, porting this edition's divergence into it; never merge or ignore the recorded digest. Update `overrides/manifest.json`.
2. **Stale description tuning** — a pre-tuning description changed upstream or inside an override. Re-derive the entry in `overrides/skill-descriptions.json` under the tuning convention: the purpose sentence first, the `/aquarium:<name>` invocation present, a kept `Use when` trigger, negative redirects preserved, and a shorter whole.
3. **Stale exemption** — a surviving mention of the third-party Codex CLI changed, appeared, or vanished. Re-read every listed line, confirm each still names the third-party CLI rather than this host, and re-record the per-line digests in `overrides/codex-exemptions.json`.
4. **Unknown skill sigil** — upstream prose invokes a skill through a dollar-prefixed sigil this edition has no rule for. Add the substitution rule naming its slash form and a matching `FORBIDDEN` family needle.
5. **Required text missing** — a marker a substitution or surgery guard anchors on stopped matching. Move the marker to the surviving schema — version bumps such as `v1` to `v2` are normal — and add arrival markers for new host-neutral scripts.
6. **Host-specific text survived** — apply the cost ladder: a literal substitution when the divergence is textual, an override when it is semantic, a reviewed exemption only when the mention is a true third-party reference.
7. **Script surgery abort** — upstream renamed a surgery anchor, left a dangling reference to a deleted function, or broke the transformed syntax. Re-derive the surgery plan for the new function set. When the change moves host-adapted semantics, derive the ZCode contract from verified host facts first — see the next section — instead of translating upstream prose literally.
8. **Unknown upstream directory** — upstream grew a plugin directory the copy allowlist does not carry. Decide explicitly whether to extend `COPIED_DIRECTORIES` or exclude it, and record the decision in the README.

A new upstream skill also stops the description-tuning stage until it has an entry, and stops `tests/validate.rb` until the invariant list covers it.

## Verify Host Facts When Semantics Move

When upstream changes behavior this edition adapts — the inspection surgery, the tool catalog's registration contracts, version floors — do not encode upstream's prose as this host's truth. Confirm the host fact read-only first: read the installed tool's package source, the `mcp.servers` object of `~/.zcode/cli/config.json`, and the owning CLI's `--help` output. Record the verified contract in the surgery or catalog text, and keep every claim scoped to what was verified. The v0.1.13 update corrected a false installer claim this way: `ooo setup --runtime zcode` configures only Ouroboros' own runtime selection in `~/.ouroboros/config.yaml` and writes no ZCode MCP entry.

## Validate and Document

1. Extend `tests/validate.rb` for any new invariant first, then run it together with `python3 scripts/sync.py --check` and `git diff --check`; all three must pass.
2. Review the generated diff in full. Check at least: the version in `.zcode-plugin/plugin.json`, the generated skill set against upstream plus the edition skills, the surgically transformed `inspect_tools.py`, every tuned description, and the exemption diff.
3. Update `README.md`: the Skills table and counts, the History note for the absorbed releases, the How-generation-works prose for any new rule or marker, and the overrides table when a divergence changed.
4. Record concise shipped-outcome entries under the open `Unreleased` section of `CHANGELOG.md`.

## Commit and Push Behind Review

Stage everything and create one commit `[FEAT] Update the ZCode plugin from upstream Aquarium vX.Y.Z`; pipeline and documentation improvements ride in the same commit by this repository's convention. Push the `update/vX.Y.Z` branch. Then stop: no merge, tag, release, or installation without the user's explicit review approval, and never push to the upstream repository.

## Release After Approval

1. Merge `update/vX.Y.Z` into `main` fast-forward — this repository keeps a linear history — and push `main`.
2. Create the annotated tag `vX.Y.Z` with the conventional message `Aquarium for GLM vX.Y.Z — generated from upstream Aquarium vX.Y.Z (<short-commit>)` and push it.
3. Publish the GitHub release with `gh release create vX.Y.Z` in the established format: an intro line naming the upstream release and commit, a What's-new list covering the absorbed upstream releases and this edition's own changes, links to the upstream release changelogs, and the Install section.
4. Set the release date on the matching `CHANGELOG.md` section, open the next `Unreleased` section above it, and commit that documentation state.

## Refresh the Local Installation

After the release exists, refresh this machine's ZCode installation when the user asks:

1. Back up `~/.zcode/cli/plugins/installed_plugins.json` and `~/.zcode/cli/plugins/marketplaces/aquarium-for-glm/marketplace.json`.
2. Copy the released `plugins/aquarium/` tree to `~/.zcode/cli/plugins/cache/aquarium-for-glm/aquarium/<version>/`, keeping earlier version directories in place — the cache convention retains them.
3. Update `installed_plugins.json` — version, installPath, installedAt — and the marketplace snapshot entry — version, cachePath, and the description from the new manifest.
4. Verify: `zcode plugins list` reports the new version and skill count, and every file of the installed tree matches its recorded SHA-256 in `sync-manifest.json` against the pinned upstream commit.
5. Tell the user that a new session or a restart is required before the new skill snapshot loads.

## Boundaries

- Never push, tag, or write to the upstream submodule; it is read-only evidence.
- Never merge, tag, publish, or install before the user explicitly approves the reviewed diff.
- Never pin upstream `main` or an unreleased commit; released tags only.
- Never bypass a sync abort; each one marks a decision this edition must make deliberately.
