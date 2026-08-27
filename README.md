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
| `dev-setup` | Diagnose and configure selected development tools, and propose an evidence-based repository operating contract behind separate approvals. | `/aquarium:dev-setup` |
| `dev-setup-bundle` | Apply development-tool setup to explicit Git repositories from one external YAML manifest. | `/aquarium:dev-setup-bundle` with a manifest path |
| `docs-setup` | Audit, establish, adopt, or migrate a repository's canonical documentation structure and roadmap IDs. | `/aquarium:docs-setup` |
| `test-setup` | Audit and configure the common Make or Bun testing contract for one repository, with evidence-backed legacy waivers. | `/aquarium:test-setup` |
| `independent-review` | Run one supervised static review with fresh reviewer subagents against staged changes, a commit or range, one task or epic, or a roadmap-independent investigation. | `/aquarium:independent-review` with one review target |
| `orca-review` | Run the canonical independent-review target contract through a user-selected external AI CLI — `claude`, `kimi`, `agy`, or `cursor-agent` — driven by Orca. | `/aquarium:orca-review` with one review target |
| `upgrade` | Update this edition to a newly released upstream Aquarium version behind explicit review: pin the tag, resolve the sync, release, and refresh the local installation. | `/aquarium:upgrade` with one released upstream version |

The four design skills drive Ouroboros as a bounded leaf capability and need it installed and pinned to `>=0.51.1,<0.52.0`; `/aquarium:dev-setup` diagnoses and configures it behind separate approvals. They shape documents only and never implement. Upstream v0.1.13 removed the `design-qa` skill and its Design Gate coupling; a repository-owned Design Gate registry, where one exists, is still honored by `/aquarium:release-qa` through the shared design-gates reference.

`task-handler` loads seven phase skills in order — `task-plan`, `task-implement`, `task-verify`, `task-refine`, `task-document`, `task-review`, `task-close`. Invoke one directly only to resume that exact phase with its required task context.

### How invocation reaches a skill

ZCode resolves skills through the Skill tool by qualified name — `aquarium:<name>`, with the short name accepted as an alias. Typing `/aquarium:<name>` or asking for the skill by name makes the model load it; `/skill <name>` forces one in a running session. Skills installed user-scoped — Ouroboros, Deslop, and the Lora pair — are invoked bare, as `/interview`, `/deslop`, or `/lore-commits`, because user-scoped skills carry no plugin namespace.

### Roadmap commit guard

The plugin ships a `PreToolUse` hook that inspects `Bash` commands and denies a direct `git commit` in a repository whose tracked roadmap carries task lifecycle state, routing it through `task-commit` instead. ZCode auto-loads `hooks/hooks.json` from every enabled plugin's root, so the upstream declaration shape survives unchanged. The hook is local, reads only the proposed command and the working directory, and fails open when it cannot parse its input. Review the declaration under `plugins/aquarium/hooks/hooks.json` after installing.

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
  skills/...                     full-file replacements for host-specific divergence
edition-skills/
  upgrade/SKILL.md               this edition's own skills, carried into the generated plugin
scripts/sync.py                  the transformation
plugins/aquarium/                generated output, committed
  .zcode-plugin/plugin.json      generated manifest — the first name ZCode probes
  hooks/                         the roadmap commit guard declaration and script
  sync-manifest.json             upstream commit and per-file hashes
marketplace.json                 hand-written root marketplace pointing at ./plugins/aquarium
```

`sync.py` copies the upstream plugin, applies literal substitutions, reworks whole functions of the bundled inspection script through name-anchored surgery, applies overrides, tunes every skill description, drops the Codex sidecar directories, and derives the manifest. It refuses to run against an empty submodule, refuses to run when upstream grows a directory the transformation does not handle, and fails if host-specific text survives.

Three files diverge semantically and are kept as overrides rather than substitutions:

| Override | Why |
|---|---|
| `skills/independent-review/SKILL.md` | Replaces Orca orchestration with fresh read-only review subagents dispatched through the host's own `Agent` tool; `/aquarium:orca-review` remains the Orca-driven multi-provider path. Because a subagent shares the coordinator's model, the skill claims a fresh context rather than an independent model, and buys coverage by giving several reviewers distinct lenses. |
| `skills/dev-setup/SKILL.md` | Resolves every host question to ZCode terms: MCP registration and scope questions target the `mcp.servers` object of `~/.zcode/cli/config.json` and the project-level `.zcode/config.json` override, and the Ouroboros configuration actions name the ZCode runtime instead of the packaged Codex installers — `ooo setup --runtime zcode` configures only Ouroboros' own runtime selection in `~/.ouroboros/config.yaml` and writes no ZCode MCP entry, so the registration merge and skill installation stay separate manual actions here. The two-stage guidance approval gate is unchanged. |
| `skills/dev-setup/references/tool-catalog.md` | Registers Mulgae, Gaori, and Ouroboros MCP servers as user-global entries under the `mcp.servers` object of `~/.zcode/cli/config.json` and verifies the global, isolated-local, and effective views by reading those configuration files, because ZCode has no `mcp` CLI probe; `/mcp` in a session shows live status. The Ouroboros entry is the canonical isolated `uvx --isolated --from ouroboros-ai[mcp]` launcher selecting the `zcode` runtime through its environment; a `codex` selection is equally valid when that CLI is the configured Ouroboros backend. |

`skills/dev-setup/references/agents-guidance.md` needed an override while upstream described a Codex-only instruction-file contract; upstream v0.1.10 rewrote it around the host-neutral `AGENTS.md` operating contract with `CLAUDE.md` delegation, which ZCode reads natively, so it now passes through substitutions unchanged.

`edition-skills/` holds the one skill this edition owns outright: `upgrade`, which walks a full upstream release cycle for this repository — pin the released tag, resolve every sync abort in order, re-derive overrides and description tunings, validate, and prepare the reviewed release and the local installation. Generation copies each edition skill into the generated tree after the overrides and before the description tuning, so it ships as `/aquarium:upgrade`, passes the same frontmatter, tuning, and needle checks as an upstream skill, and stops the run when its name collides with a new upstream skill.

Everything else is a literal substitution: the `$aquarium:` sigil becomes `/aquarium:`, the `$use-*` skill sigils become `/use-*`, the `$create-podway-procedure` maintainer skill sigil becomes `/create-podway-procedure`, the Ouroboros sigils `$interview`, `$pm`, `$seed`, and `$qa` become `/interview`, `/pm`, `/seed`, and `/qa` because Ouroboros installs user-scoped skills that ZCode reads natively from `~/.agents/skills`, the separately installed `$deslop` becomes `/deslop`, `request_user_input` becomes `AskUserQuestion`, `Codex goal` becomes `ZCode todo list`, and the inspection script resolves skills from the ZCode roots — `~/.zcode/skills` and the shared `~/.agents/skills` — and diagnoses every MCP registration against this host instead of Codex. The v0.1.11 review split carries its own substitutions: the Orca supervision reference names `/aquarium:orca-review` as the workflow it backs and drops the Codex dispatch clause `independent-review` never runs here, and orca-review's `non-Codex` phrasing becomes `external provider`, because the default review backend on this host is the skill's own reviewer subagent rather than Codex. The v0.1.13 design-gate removal needed no rule of its own: deleting `design-qa` upstream removed its skill directory with it, and the skills-match validation confirms the set.

Whole functions of `inspect_tools.py` diverge too far for literal rules, so the transformation also performs name-anchored surgery: each rule names a top-level function to replace or delete, the function's span comes from `ast` line numbers, and post-surgery checks reject a rule whose function upstream no longer defines, a replacement that drops its namesake, any syntax error, and any dangling reference to a deleted function. Anchoring on names instead of exact bytes keeps a rule working through upstream body edits — the failure mode of the giant literal blocks this mechanism replaced — while upstream renames still stop generation loudly.

The hook command keeps the `hooks/hooks.json` declaration shape — ZCode auto-loads it — and rewrites `${PLUGIN_ROOT}` to `${ZCODE_PLUGIN_ROOT}`, which ZCode expands for hook processes. That substitution is load-bearing: the Codex spelling is unset under ZCode, so the unsubstituted command expands to `/hooks/task_commit_gate.py`, `python3` exits 2, and `PreToolUse` reads exit 2 as a denial — blocking every `Bash` call. A forbidden needle and a required-text assertion both guard it.

Upstream diagnoses Ouroboros by asking Codex — `ooo codex doctor` for its integration artifacts and `codex mcp get ouroboros --json` for the registration, which v0.1.12's v10 inspector now validates against a launcher contract: the direct `ooo mcp serve` form or the canonical isolated `uvx --isolated --python >=3.12 --from ouroboros-ai[mcp]` launcher selecting codex through its environment keys or command suffix. ZCode has no `mcp` CLI probe and the `ooo zcode` group ships no doctor command, so the surgical replacements classify every MCP registration — `ouroboros`, `mulgae`, and `gaori` — from the host's config files: the user-level `~/.zcode/cli/config.json`, the project-level `.zcode/config.json` override, and the effective scope the project entry wins. The Ouroboros classification reuses the upstream launcher-contract matchers with one host decision: the runtime selectors must name one coherent runtime, and this edition accepts both `zcode` — the GLM-native runtime its catalog proposes — and `codex`, valid when that CLI is the configured Ouroboros backend. The entry doubles as the host-integration signal, because on this host the integration is exactly that entry plus the user-scoped Ouroboros skills. Runtime configuration follows the launcher kind: an isolated launcher establishes it by contract — the base CLI's doctor would inspect an unrelated package environment — while a direct launcher keeps `ooo mcp doctor --json` with the `mcp_import` check exempted, because the MCP 2 server registered in config launches as a separate process while the CLI environment keeps MCP 1.x, so that check fails on a correctly configured machine.

Skill discovery narrows for the same reason. Upstream resolves user-scoped skills from the Codex and shared cross-agent roots; the generated inspector resolves the ZCode roots alone, because one host's artifact should diagnose one host. ZCode exposes no config-dir environment variable, so the roots are literal. The shared `~/.agents/skills` root needs no substitution: ZCode reads it natively, so Ouroboros, Deslop, and Lora skills installed there are genuinely reachable.

ZCode defines no per-server timeout fields in `mcp.servers`, so the catalog's Mulgae and Gaori entries carry no `startupTimeoutMs`/`toolTimeoutMs` values; host-level MCP deadlines apply, and the CLI fallback paths remain the bounded completion route when a review or test run may exceed them. Lora and Deslop install through `npx skills --agent zcode` into `~/.zcode/skills`; when the same skill already exists in the shared `~/.agents/skills` root, the catalog updates that copy in place rather than creating a duplicate ZCode also loads.

An unmapped sigil is the quiet failure: it is valid Markdown naming a command the reader's host does not have, so neither a forbidden needle nor a required-text assertion notices it, and one needle per known sigil only ever catches the sigils that already exist. Generation therefore rejects any remaining lowercase `$name` in generated Markdown. Uppercase spellings are environment variables the generated tree still needs and do not match.

The `Codex` name is otherwise forbidden in generated text. One exemption remains: `tool-catalog.md` names the Codex CLI as a Mulgae provider, a required CLI version, and an Ouroboros runtime backend, which stays true here. An exemption records the SHA-256 of every generated line that still contains `Codex`, so one review judgement covers exactly the mentions the artifact ships: upstream edits that leave each exempted line byte-identical keep the exemption valid, while any new, changed, or removed mention line stops the sync and names the line to re-read. The v0.1.11 provider contracts dropped Codex as an orca-review provider, so the former second exemption retired. The host-neutral inspectors that ship from upstream — `test-setup`, `docs-setup`, both `release-handler` inspectors, the review-target inspector, the provider-terminal helper, the repository-state snapshot inspector, and the release-qa confirmation manager — each carry a required-text marker guarding that they arrive whole rather than transformed away.

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

MIT, inherited from upstream. This repository vendors no third-party skill source: Deslop and Lora are installed from their own upstream repositories by `/aquarium:dev-setup`, each keeping its original licence.
