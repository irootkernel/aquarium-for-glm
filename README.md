# Aquarium for GLM

Aquarium development skills packaged as a ZCode plugin. This repository is a **generated artifact**: the source of truth is the Codex plugin at [irootkernel/aquarium](https://github.com/irootkernel/aquarium), pinned here as a submodule and transformed by `scripts/sync.py`.

By [Root Kernel](https://home.rootkernel.xyz) · Support: [cs@rootkernel.xyz](mailto:cs@rootkernel.xyz)

## Aquarium Editions

- [Aquarium](https://github.com/irootkernel/aquarium)
- [Aquarium for Claude](https://github.com/irootkernel/aquarium-for-claude)
- [Aquarium for Kimi](https://github.com/irootkernel/aquarium-for-kimi)

## Install

ZCode installs plugins through its desktop client. Open Settings → Plugin Management → Discover, add this repository as a marketplace — GitHub repository `irootkernel/aquarium-for-glm`, or a local directory pointing at a checkout — then Get `aquarium`. Restart or start a new session so the skill snapshot reloads.

ZCode probes `.claude-plugin/marketplace.json` first and then a root `marketplace.json`; this repository ships the root file, which is also the name the official marketplace is served under.

The generated plugin is committed, so installation never depends on the submodule being fetched.

## Skills

| Skill | Purpose | Invocation |
|---|---|---|
| `new-project` | Shape a greenfield project into an approved PRD and initial roadmap with Ouroboros, without implementing it. | `/aquarium:new-project` |
| `new-feature` | Shape one feature epic for an existing project with Ouroboros, without implementing it. | `/aquarium:new-feature` |
| `refactor` | Shape one major refactor or behavior-change epic with Ouroboros, without implementing it. | `/aquarium:refactor` |
| `war-room` | Diagnose one difficult bug and propose a task, epic, or incomplete investigation without a fix. | `/aquarium:war-room` |
| `epic-handler` | Orchestrate an epic through sequential task goals and a convergent epic-wide audit. | `/aquarium:epic-handler` with a roadmap path and one epic ID |
| `epic-validator` | Cold-validate a completed epic and converge confirmed gaps through remediation goals. | `/aquarium:epic-validator` with a roadmap path and one epic ID |
| `task-handler` | Strengthen the procedure around one task goal through focused phase skills and verified transitions. | `/aquarium:task-handler` with a roadmap path and one task ID |
| `task-commit` | Reconcile roadmap task lifecycle state and create one authorized commit that preserves unrelated work. | Automatic for commit requests, or `/aquarium:task-commit` |
| `release-handler` | Prepare, validate, publish, or retarget one stable release with cumulative changelog settlement. | `/aquarium:release-handler` with an intended or planned version |
| `release-qa` | Run one full scenario-based QA pass for an exact main release candidate, or one bounded confirmation pass after remediated findings. | `/aquarium:release-qa` with an intended or confirmed version |
| `dev-setup` | Diagnose and configure repository-local tooling — project configuration such as `.podway`, `.mulgae`, `.gaori`, Sorage binding, project MCP — and reconcile the root AGENTS.md/CLAUDE.md operating guidance. | `/aquarium:dev-setup` |
| `dev-setup-global` | Diagnose, install, and update user-global development tools: global CLIs, paired skills under `~/.agents/skills`, global MCP registrations, services, and Ouroboros. | `/aquarium:dev-setup-global` |
| `dev-setup-bundle` | Apply development-tool setup to explicit Git repositories from one external YAML manifest. | `/aquarium:dev-setup-bundle` with a manifest path |
| `docs-setup` | Audit, establish, adopt, or migrate a repository's canonical documentation structure and roadmap IDs. | `/aquarium:docs-setup` |
| `test-setup` | Audit and configure the common Make or Bun testing contract for one repository, with evidence-backed legacy waivers. | `/aquarium:test-setup` |
| `independent-review` | Run one supervised static review with fresh reviewer subagents against staged changes, `HEAD`, a commit or range, one task or epic, or a roadmap-independent investigation. | `/aquarium:independent-review` with one review target |
| `orca-review` | Run the canonical review contract with one fresh requested native reviewer, such as Claude, owned and supervised by the local Orca runtime for a staged, `HEAD`, commit, or range target. | `/aquarium:orca-review` with one review target and reviewer |
| `upgrade` | Update this edition to a newly released upstream Aquarium version behind explicit review: pin the tag, resolve the sync, release, and refresh the local installation. | `/aquarium:upgrade` with one released upstream version |

The four design skills drive Ouroboros as a bounded leaf capability and need it installed and pinned to `>=0.51.1,<0.54.0` (0.53 included); `/aquarium:dev-setup-global` diagnoses and configures it behind separate approvals. They shape documents only and never implement. Upstream v0.1.13 removed the `design-qa` skill and its Design Gate coupling; a repository-owned Design Gate registry, where one exists, is still honored by `/aquarium:release-qa` through the shared design-gates reference.

Upstream v0.1.15 replaced the `aquarium-dev` skill with a bundled CLI + MCP package under `tools/aquarium-dev/`. The package ships in the generated plugin, and its `aquarium-dev` MCP server registers through the plugin's own root `.mcp.json` — the file ZCode auto-loads for plugin servers — so it needs no user-global `mcp.servers` entry. Install or update the runtime only through `/aquarium:dev-setup-global` on an explicit request.

`task-handler` loads seven phase skills in order — `task-plan`, `task-implement`, `task-verify`, `task-refine`, `task-document`, `task-review`, `task-close`. Invoke one directly only to resume that exact phase with its required task context.

### How invocation reaches a skill

ZCode resolves skills through the Skill tool by qualified name — `aquarium:<name>`, with the short name accepted as an alias. Typing `/aquarium:<name>` or asking for the skill by name makes the model load it; `/skill <name>` forces one in a running session. Skills installed user-scoped — Ouroboros, Deslop, and the Lora pair — are invoked bare, as `/interview`, `/deslop`, or `/lore-commits`, because user-scoped skills carry no plugin namespace.

### Roadmap commit guard

The plugin ships a `PreToolUse` hook that inspects `Bash` commands and denies a direct `git commit` in a repository whose tracked roadmap carries task lifecycle state, routing it through `task-commit` instead; a gated commit additionally requires a non-empty `user.name` and `user.email` from the repository's local or worktree Git configuration, so the hook also reads those identity values. ZCode auto-loads `hooks/hooks.json` from every enabled plugin's root, so the upstream declaration shape survives unchanged. The hook is local, reads only the proposed command, the working directory, tracked roadmap files, and the repository's local and worktree Git identity configuration, and fails open when it cannot parse its input. Review the declaration under `plugins/aquarium/hooks/hooks.json` after installing.

### No per-skill invocation gating

ZCode has no `disable-model-invocation` equivalent: every discovered skill stays model-invocable, and the upstream Codex sidecars that gated implicit invocation have no counterpart here. The generated artifact therefore derives no frontmatter flag at all, and the trigger discipline lives entirely in each skill's `Use when` description — a surface this edition tunes for the host through `overrides/skill-descriptions.json`. To disable a specific skill, set `skills.overrides` (a `{"<skill-name>": {"enable": false}}` map) in `~/.zcode/cli/config.json`.

## How generation works

```
upstream/                        git submodule, pinned to one upstream commit
  plugins/aquarium/              the Codex plugin — never edited here
overrides/
  manifest.json                  path → SHA-256 of the upstream file each override was derived from
  codex-exemptions.json          path → SHA-256 of each generated line whose surviving "Codex" mention was reviewed
  skill-descriptions.json        skill → SHA-256 of the pre-tuning description plus the tuned trigger surface
  skills/... , references/...    full-file replacements for host-specific divergence
edition-skills/
  upgrade/SKILL.md               this edition's own skills, carried into the generated plugin
scripts/sync.py                  the transformation
plugins/aquarium/                generated output, committed
  .zcode-plugin/plugin.json      generated manifest — the first name ZCode probes
  .mcp.json                      generated plugin MCP manifest — ZCode auto-loads it from the plugin root
  tools/aquarium-dev/            the bundled aquarium-dev CLI + MCP package (v0.1.15)
  hooks/                         the roadmap commit guard declaration and script
  sync-manifest.json             upstream commit and per-file hashes
marketplace.json                 hand-written root marketplace pointing at ./plugins/aquarium
```

`sync.py` copies the upstream plugin, applies literal substitutions, reworks whole functions of the bundled inspection scripts through name-anchored surgery, applies overrides, tunes every skill description, drops the Codex sidecar directories, derives the manifest, and converts the upstream root `.mcp.json` into the ZCode plugin form — `mcpServers` with stdio fields, `tool_timeout_sec` becoming `timeoutMs`, and the launcher rooted at `${ZCODE_PLUGIN_ROOT}`, the one template scope ZCode expands for plugin servers. ZCode auto-loads that file directly, and its documented manifest `mcpServers` forms accept a directory, array, or inline object rather than a file path, so the manifest itself deliberately carries no `mcpServers` key. It refuses to run against an empty submodule, refuses to run when upstream grows a directory the transformation does not handle, and fails if host-specific text survives.

Four files diverge semantically and are kept as overrides rather than substitutions:

| Override | Why |
|---|---|
| `skills/independent-review/SKILL.md` | Upstream v0.1.15 routes the reviewer through a same-release Dolgorae skill with global Codex Profiles and delegated settlement; this edition keeps dispatching fresh read-only `Explore` subagents through the host's own `Agent` tool and drops that machinery wholesale, adopting only the backend-neutral contract parts — the shared finding-disposition contract, stricter adjudication with preserved severity and effective priority, and the no-staging consent rule — while `workspace` and `dirty` stay unsupported because they require a capture this backend cannot provide. A subagent shares the coordinator's model, so the skill claims a fresh context rather than an independent model, and buys coverage by giving several reviewers distinct lenses. `/aquarium:orca-review` remains the external-provider path. |
| `skills/dev-setup/SKILL.md` | Upstream v0.1.15 split repository-local setup from global setup; the override keeps the split and resolves every host question to ZCode terms — project MCP registration lives in the `mcp.servers` object of the repository's `.zcode/config.json`, global state is delegated to `/aquarium:dev-setup-global`, and canonical global skills are trusted by presence under `~/.agents/skills` only. |
| `skills/dev-setup-global/SKILL.md` | The new user-global setup skill, restated for this host: global MCP registrations live in `~/.zcode/cli/config.json`, the paired skills install under the shared `~/.agents/skills` root, the aquarium-dev MCP registration ships in the plugin's own `.mcp.json`, and Ouroboros has one integration surface — no per-Codex-home rows — with any `--codex-home` reported as not applicable. |
| `references/tool-catalog.md` | The shared catalog (upstream moved it from `skills/dev-setup/references/` in v0.1.15), carrying the edition's MCP registrations — Mulgae, Gaori, and Ouroboros as user-global entries under the `mcp.servers` object of `~/.zcode/cli/config.json`, verified by reading those files because ZCode has no `mcp` CLI probe, with `/mcp` in a session showing live status — plus the v0.1.15 floors (Dolgorae v0.1.2 with its paired `use-dolgorae` skill, Mulgae v0.1.19 on the v6 envelope, Gaori v0.1.16 with `use-gaori-status`, Sorage v0.1.x, Podway v0.2.9 with the `use-podway` skill pinned to commit `9014225…`), the aquarium-dev package section, the single-surface Ouroboros contract with the `runtime_package` axis, and the GLM-subagent stance: Aquarium's own reviews and reusable Specialist requests dispatch through the host's `Agent` tool, leaving `/use-dolgorae` for explicitly requested Dolgorae-native operations. |

`skills/dev-setup/references/agents-guidance.md` needed an override while upstream described a Codex-only instruction-file contract; upstream v0.1.10 rewrote it around the host-neutral `AGENTS.md` operating contract with `CLAUDE.md` delegation, which ZCode reads natively, so it now passes through substitutions unchanged.

`edition-skills/` holds the one skill this edition owns outright: `upgrade`, which walks a full upstream release cycle for this repository — pin the released tag, resolve every sync abort in order, re-derive overrides and description tunings, validate, and prepare the reviewed release and the local installation. Generation copies each edition skill into the generated tree after the overrides and before the description tuning, so it ships as `/aquarium:upgrade`, passes the same frontmatter, tuning, and needle checks as an upstream skill, and stops the run when its name collides with a new upstream skill.

Everything else is a literal substitution: the `$aquarium:` sigil becomes `/aquarium:`, the `$use-*` skill sigils become `/use-*`, the `$create-podway-procedure` maintainer skill sigil becomes `/create-podway-procedure`, the Ouroboros sigils `$interview`, `$pm`, `$seed`, and `$qa` become `/interview`, `/pm`, `/seed`, and `/qa` because Ouroboros installs user-scoped skills that ZCode reads natively from `~/.agents/skills`, the separately installed `$deslop` becomes `/deslop`, the v0.1.14 writing pair `$humanizer` and `$humanize-korean` becomes `/humanizer` and `/humanize-korean`, `request_user_input` becomes `AskUserQuestion`, `Codex goal` becomes `ZCode todo list`, and the inspection script resolves skills from the ZCode roots — `~/.zcode/skills` and the shared `~/.agents/skills` — and diagnoses every MCP registration against this host instead of Codex. v0.1.14 also pins roadmap commit identities to task-scoped shell variables; they are environment overrides in a `git -c` command rather than skill sigils, so they take the uppercase `AQUARIUM_COMMIT_NAME`/`AQUARIUM_COMMIT_EMAIL` spelling that convention implies and that the lowercase sigil scan deliberately ignores. The v0.1.11 review split carries its own substitutions: the Orca supervision reference names `/aquarium:orca-review` as the workflow it backs and drops the Codex dispatch clause `independent-review` never runs here, and orca-review's `non-Codex` phrasing becomes `external provider`, because the default review backend on this host is the skill's own reviewer subagent rather than Codex. The v0.1.14 review-contract rewrite carries a third family: the shared contract's Independent Review half — its scope table, target authority, backend, settlement, and result sentences — is restated for the subagent backend, `workspace` and `dirty` are marked unsupported for both backends because neither provides the immutable capture they require, and orca-review's redirect to `independent-review` for those scopes names that boundary instead. The same family restates the shared disposition contract's re-review sentence (Independent Review rebinds a fresh dispatch rather than creating a capture) and qualifies the shipped Dolgorae consumer contract's opening as upstream documentation no workflow here runs, and it broadens the aquarium-dev plugin-artifact boundary from a Codex home to any host's plugin home. The v0.1.13 design-gate removal needed no rule of its own: deleting `design-qa` upstream removed its skill directory with it, and the skills-match validation confirms the set. v0.1.15 added three more families: the guidance bullet and review-contract settlement sentence that delegate reviews and Specialist Engagements to `/use-dolgorae` are restated for `Agent`-tool subagents while the shipped Dolgorae consumer contract keeps only its not-used-here qualifier (with the v0.1.2 floor); the Podway reference's "Codex objective"/"Codex tool contract" phrasing maps onto the todo-list surface the way `Codex goal` already did; and the aquarium-dev package's host-naming clauses — its restart sentence, launcher and manager boundaries, MCP tool instructions, and the plugin-manifest path its runtime entry reads — resolve to ZCode terms.

Whole functions of `inspect_tools.py` diverge too far for literal rules, so the transformation also performs name-anchored surgery: each rule names a top-level function to replace or delete, the function's span comes from `ast` line numbers, and post-surgery checks reject a rule whose function upstream no longer defines, a replacement that drops its namesake, any syntax error, and any dangling reference to a deleted function. Anchoring on names instead of exact bytes keeps a rule working through upstream body edits — the failure mode of the giant literal blocks this mechanism replaced — while upstream renames still stop generation loudly. The v0.1.14 writing-skill inspection added one such rule: upstream resolves the im-not-ai target through a Codex home, so the surgery replaces that resolver with a ZCode `effective_writing_skill_root()` helper that pins the target to the shared `~/.agents/skills` root; v0.1.15 added a `trusted_global_skills` presence map with the same bug, and a substitution pins its `humanize-korean` entry to the same shared root — the fix upstream itself shipped after the tag. v0.1.15 also re-derived `inspect_ouroboros` for upstream's new per-home signature — accepting `codex_home`/`cli_observation` for interface compatibility while the ZCode form adds the `runtime_package` axis from the registration's launcher pin — and added two new plans for the user-global inspector: `inspect_global_mcp` reads the config scopes the project inspector exposes instead of calling the deleted Codex-CLI probes, and the global `inspect_ouroboros` collapses upstream's per-home rows into one `integration` object plus a `shared_root_skills` inventory, deleting the home-discovery machinery outright.

The hook command keeps the `hooks/hooks.json` declaration shape — ZCode auto-loads it — and rewrites `${PLUGIN_ROOT}` to `${ZCODE_PLUGIN_ROOT}`, which ZCode expands for hook processes. That substitution is load-bearing: the Codex spelling is unset under ZCode, so the unsubstituted command expands to `/hooks/task_commit_gate.py`, `python3` exits 2, and `PreToolUse` reads exit 2 as a denial — blocking every `Bash` call. A forbidden needle and a required-text assertion both guard it.

Upstream diagnoses Ouroboros by asking Codex — `ooo codex doctor` for its integration artifacts and `codex mcp get ouroboros --json` for the registration, validated against a launcher contract: the direct `ooo mcp serve` form or the canonical isolated `uvx --isolated --python >=3.12 --from ouroboros-ai[mcp]` launcher selecting codex through its environment keys or command suffix, with per-Codex-home rows bound to each discovered home. ZCode has no `mcp` CLI probe and the `ooo zcode` group ships no doctor command, so the surgical replacements classify every MCP registration — `ouroboros`, `mulgae`, and `gaori` — from the host's config files: the user-level `~/.zcode/cli/config.json`, the project-level `.zcode/config.json` override, and the effective scope the project entry wins. The Ouroboros classification reuses the upstream launcher-contract matchers with one host decision: the runtime selectors must name one coherent runtime, and this edition accepts both `zcode` — the GLM-native runtime its catalog proposes — and `codex`, valid when that CLI is the configured Ouroboros backend. The entry doubles as the host-integration signal, because on this host the integration is exactly that entry plus the user-scoped Ouroboros skills; v0.1.15's `runtime_package` axis is derived from the same registration — `pinned` from the isolated launcher's version pin, `different` when the pin diverges from the installed CLI, `selected_cli` for the direct launcher. Runtime configuration follows the launcher kind: an isolated launcher establishes it by contract — the base CLI's doctor would inspect an unrelated package environment — while a direct launcher keeps `ooo mcp doctor --json` with the `mcp_import` check exempted, because the MCP 2 server registered in config launches as a separate process while the CLI environment keeps MCP 1.x, so that check fails on a correctly configured machine.

Skill discovery narrows for the same reason. Upstream resolves user-scoped skills from the Codex and shared cross-agent roots; the generated inspector resolves the ZCode roots alone, because one host's artifact should diagnose one host. ZCode exposes no config-dir environment variable, so the roots are literal. The shared `~/.agents/skills` root needs no substitution: ZCode reads it natively, so Ouroboros, Deslop, and Lora skills installed there are genuinely reachable.

ZCode defines no per-server timeout fields in `mcp.servers`, so the catalog's Mulgae and Gaori entries carry no `startupTimeoutMs`/`toolTimeoutMs` values; host-level MCP deadlines apply, and the CLI fallback paths remain the bounded completion route when a review or test run may exceed them. Lora and Deslop install through `npx skills --agent zcode`: the CLI's global canonical store is the shared `~/.agents/skills` root — verified against the installed `skills` package — with an entry for the `zcode` agent under `~/.zcode/skills` pointing at that same copy, so one installation is reachable through both roots rather than duplicated.

An unmapped sigil is the quiet failure: it is valid Markdown naming a command the reader's host does not have, so neither a forbidden needle nor a required-text assertion notices it, and one needle per known sigil only ever catches the sigils that already exist. Generation therefore rejects any remaining lowercase `$name` in generated Markdown. Uppercase spellings are environment variables the generated tree still needs and do not match.

The `Codex` name is otherwise forbidden in generated text. Six exemption groups remain: `references/tool-catalog.md` names the Codex CLI as a Mulgae provider, a required CLI version, and an Ouroboros runtime backend, which stays true here; `references/dolgorae-review-contract.md` ships as the upstream backend's documentation — global Codex Profiles are that backend's concept — and no skill here loads it; `skills/dev-setup/scripts/inspect_tools.py` and the two `dev-setup-global` inspection scripts carry surgery comments and the `InvalidCodexHome` identifiers that name upstream's per-home machinery, which the restated code deliberately reports as not applicable; and the edition's own `upgrade` skill names the third-party Codex CLI once, in its stale-exemption re-review instruction. An exemption records the SHA-256 of every generated line that still contains `Codex`, so one review judgement covers exactly the mentions the artifact ships: upstream edits that leave each exempted line byte-identical keep the exemption valid, while any new, changed, or removed mention line stops the sync and names the line to re-read. The host-neutral inspectors that ship from upstream — `test-setup`, `docs-setup`, both `release-handler` inspectors, the review-target inspector, the release-qa confirmation manager, the Dolgorae release verifier (moved beside the global inspector in v0.1.15), the `dev-setup-global` inspector pair, and the eight `tools/aquarium-dev` package files — each carry a required-text marker guarding that they arrive whole rather than transformed away. `references/dolgorae-review-contract.md` still ships as the upstream backend's documentation even though no skill here loads it, and the restated review contract says exactly that.

Skill descriptions are the one surface tuned past upstream. ZCode exposes only each skill's frontmatter `description` to the model, so `overrides/skill-descriptions.json` replaces all of them with a shorter trigger surface: the purpose sentence first, the `/aquarium:<name>` invocation present, a kept `Use when` trigger, and the negative redirects preserved. Each entry pins the SHA-256 of the pre-tuning description — the value upstream plus substitutions and overrides produced — so an upstream or override change to any description stops the run until the tuning is re-derived, and a new upstream skill stops it until an entry exists; `tests/validate.rb` asserts the invocation-name convention holds for every generated skill.

## Upgrade

```bash
git -C upstream fetch --tags origin
git -C upstream checkout <new-tag>
python3 scripts/sync.py
ruby tests/validate.rb
git add -A && git commit
```

Each override records the SHA-256 of the upstream file it came from. When upstream changes one of those files the sync stops and names it, because merging a stale override would ship guidance that no longer matches its source. Re-derive the override against the new upstream content and update `overrides/manifest.json`. The description tuning carries the same guard for its own surface through `overrides/skill-descriptions.json`.

## History notes

- v0.1.12 raised Podway to v0.2.6, reauthored the five Procedures, hardened Orca reviews around provider-native auto-approval with a repository-state snapshot, added the release-qa confirmation manager, and took the dev-setup inspector to v10 with the Ouroboros isolated-launcher contract; the edition links in the upstream READMEs were also fixed to `aquarium-for-*`.
- v0.1.13 removed `design-qa` and its Design Gate coupling from the design, delivery, and validation workflows; a repository-owned Design Gate registry is honored by `release-qa` only where one already exists.
- v0.1.14 added the explicit `aquarium-dev` development channel, official Dolgorae v0.1.1 installation and verification, exact-upstream Humanizer and im-not-ai installation, one shared finding-disposition contract across Independent Review, Mulgae, and Orca Review, the roadmap commit-identity pinning that became `AQUARIUM_COMMIT_NAME`/`AQUARIUM_COMMIT_EMAIL` here, and a reworked Orca Review that reads staged changes directly in the registered worktree; Podway's floor rose to v0.2.8 with named runtime modes and daemon-status v3. Upstream routed Independent Review through Dolgorae's immutable captures — this edition kept its own reviewer-subagent backend, adopted the backend-neutral contract changes, and left `workspace` and `dirty` scopes unsupported on both backends because neither provides a capture.
- v0.1.15 replaced the `aquarium-dev` skill with a bundled CLI + MCP package (`tools/aquarium-dev/`) that this edition ships with a derived ZCode-form `.mcp.json`, added the `dev-setup-global` skill for user-global setup (restated here for the single config surface), raised the tool floors (Dolgorae v0.1.2 with its paired skill, Mulgae v0.1.19, Gaori v0.1.16, Podway v0.2.9 with the `use-podway` pin), added optional Sorage, split `dev-setup` down to repository-local concerns, and rebuilt test setup and release QA. Upstream delegated reviews and Specialist Engagements to a same-release Dolgorae skill; this edition routes both through fresh `Agent`-tool subagents and keeps Dolgorae as an explicitly requested third-party CLI. The edition also pinned v0.1.15's new `trusted_global_skills` map to `~/.agents/skills` — the same humanize-korean path fix upstream shipped after the tag — and restated the new per-Codex-home Ouroboros model as this host's single integration surface.

## Validate

```bash
python3 scripts/sync.py --check
ruby tests/validate.rb
git diff --check
```

`--check` regenerates into a temporary directory and fails if the committed output drifted. The Ruby validation covers only what this repository is responsible for — frontmatter shape against the host's contract, host-neutral generated text, the commit hook's ZCode contract, byte-identical Podway procedures, manifest and marketplace agreement, and the generated tree's coverage of upstream. Upstream owns the prose contract and validates it in its own CI.

## Documentation style

Do not hard-wrap prose. Keep each prose paragraph on one source line; use line breaks only for structural Markdown, code, tables, lists, or other syntax where the break is meaningful.

## License

MIT, inherited from upstream. This repository vendors no third-party skill source: Deslop and Lora are installed from their own upstream repositories by `/aquarium:dev-setup-global`, each keeping its original licence.
