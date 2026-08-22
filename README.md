# Aquarium for GLM

Aquarium development skills packaged as a ZCode plugin. This repository is a **generated artifact**: the source of truth is the Codex plugin at [irootkernel/aquarium](https://github.com/irootkernel/aquarium), pinned here as a submodule and transformed by `scripts/sync.py`.

By [Root Kernel](https://home.rootkernel.xyz) · Support: [cs@rootkernel.xyz](mailto:cs@rootkernel.xyz)

## Install

ZCode installs plugins through its desktop client. Open Settings → Plugin Management → Discover, add this repository as a marketplace — GitHub repository `irootkernel/aquarium-for-glm`, or a local directory pointing at a checkout — then Get `aquarium`. Restart or start a new session so the skill snapshot reloads.

ZCode probes `.claude-plugin/marketplace.json` first and then a root `marketplace.json`; this repository ships the root file, which is also the name the official marketplace is served under.

The generated plugin is committed, so installation never depends on the submodule being fetched.

## Skills

| Skill | Purpose | Invocation |
|---|---|---|
| `new-project` | Shape a greenfield project into an approved PRD and initial roadmap with Ouroboros, without implementing it. | `/aquarium:new-project` |
| `new-feature` | Shape one feature epic and its Design Gate impact for an existing project. | `/aquarium:new-feature` |
| `refactor` | Shape one refactor epic with compatibility, migration, rollback, and gate impact. | `/aquarium:refactor` |
| `war-room` | Diagnose one difficult bug and propose a task, epic, or incomplete investigation without a fix. | `/aquarium:war-room` |
| `design-qa` | Create, change, reactivate, or retire durable local Design Gates behind an approved exact diff. | `/aquarium:design-qa` |
| `epic-handler` | Orchestrate an epic through sequential task goals and a convergent epic-wide audit. | `/aquarium:epic-handler` with a roadmap path and one epic ID |
| `epic-validator` | Cold-validate a completed epic and converge confirmed gaps through remediation goals. | `/aquarium:epic-validator` with a roadmap path and one epic ID |
| `task-handler` | Strengthen the procedure around one task goal through focused phase skills and verified transitions. | `/aquarium:task-handler` with a roadmap path and one task ID |
| `task-commit` | Reconcile roadmap task lifecycle state and create one authorized commit that preserves unrelated work. | Automatic for commit requests, or `/aquarium:task-commit` |
| `release-qa` | Exercise the current release candidate through read-only user scenarios covering every change since the previous stable release. | `/aquarium:release-qa` with an intended or confirmed version |
| `dev-setup` | Diagnose and configure selected development tools, and propose reference-based instruction-file guidance behind separate approvals. | `/aquarium:dev-setup` |
| `dev-setup-bundle` | Apply development-tool setup to explicit Git repositories from one external YAML manifest. | `/aquarium:dev-setup-bundle` with a manifest path |
| `independent-review` | Run a supervised read-only requirements and code review with fresh reviewer subagents, then adjudicate their findings. | `/aquarium:independent-review` with one epic or task |

The five design skills drive Ouroboros as a bounded leaf capability and need it installed and pinned to `>=0.51.1,<0.52.0`; `/aquarium:dev-setup` diagnoses and configures it behind separate approvals. They shape documents only and never implement.

`task-handler` loads seven phase skills in order — `task-plan`, `task-implement`, `task-verify`, `task-refine`, `task-document`, `task-review`, `task-close`. Invoke one directly only to resume that exact phase with its required task context.

### How invocation reaches a skill

ZCode resolves skills through the Skill tool by qualified name — `aquarium:<name>`, with the short name accepted as an alias. Typing `/aquarium:<name>` or asking for the skill by name makes the model load it; `/skill <name>` forces one in a running session. Skills installed user-scoped — Ouroboros, Deslop, and the Lora pair — are invoked bare, as `/interview`, `/deslop`, or `/lore-commits`, because user-scoped skills carry no plugin namespace.

### Roadmap commit guard

The plugin ships a `PreToolUse` hook that inspects `Bash` commands and denies a direct `git commit` in a repository whose tracked roadmap carries task lifecycle state, routing it through `task-commit` instead. ZCode auto-loads `hooks/hooks.json` from every enabled plugin's root, so the upstream declaration shape survives unchanged. The hook is local, reads only the proposed command and the working directory, and fails open when it cannot parse its input. Review the declaration under `plugins/aquarium/hooks/hooks.json` after installing.

### No per-skill invocation gating

ZCode has no `disable-model-invocation` equivalent: every discovered skill stays model-invocable, and the upstream Codex sidecars that gated implicit invocation have no counterpart here. The generated artifact therefore derives no frontmatter flag at all, and the trigger discipline lives entirely in each skill's `Use when` description — the same contract the upstream prose already carries. To disable a specific skill, set `skills.overrides` (a `{"<skill-name>": {"enable": false}}` map) in `~/.zcode/cli/config.json`.

## How generation works

```
upstream/                        git submodule, pinned to one upstream commit
  plugins/aquarium/              the Codex plugin — never edited here
overrides/
  manifest.json                  path → SHA-256 of the upstream file each override was derived from
  codex-exemptions.json          path → SHA-256 of an upstream file whose remaining "Codex" mentions were reviewed
  skills/...                     full-file replacements for host-specific divergence
scripts/sync.py                  the transformation
plugins/aquarium/                generated output, committed
  .zcode-plugin/plugin.json      generated manifest — the first name ZCode probes
  hooks/                         the roadmap commit guard declaration and script
  sync-manifest.json             upstream commit and per-file hashes
marketplace.json                 hand-written root marketplace pointing at ./plugins/aquarium
```

`sync.py` copies the upstream plugin, applies literal substitutions, applies overrides, drops the Codex sidecar directories, and derives the manifest. It refuses to run against an empty submodule, refuses to run when upstream grows a directory the transformation does not handle, and fails if host-specific text survives.

Four files diverge semantically and are kept as overrides rather than substitutions:

| Override | Why |
|---|---|
| `skills/independent-review/SKILL.md` | Replaces Orca orchestration with fresh read-only review subagents dispatched through the host's own `Agent` tool; Orca's supervised workers drive Claude and Codex accounts only. Because a subagent shares the coordinator's model, the skill claims a fresh context rather than an independent model, and buys coverage by giving several reviewers distinct lenses. |
| `skills/dev-setup/SKILL.md` | Resolves the instruction-file target to `AGENTS.md`, which ZCode reads natively. The two-stage approval gate is unchanged. |
| `skills/dev-setup/references/agents-guidance.md` | The whole file is instruction-file editing guidance, which is exactly what differs per host. |
| `skills/dev-setup/references/tool-catalog.md` | Registers Mulgae, Gaori, and Ouroboros MCP servers under the `mcp.servers` object of `.zcode/config.json` (project) and `~/.zcode/cli/config.json` (user) and verifies them by reading the effective configuration, because ZCode has no `mcp` CLI probe; `/mcp` in a session shows live status. Ouroboros registration can also come from `ooo setup --runtime zcode`, which is the packaged installer for this host. |

Everything else is a literal substitution: the `$aquarium:` sigil becomes `/aquarium:`, the `$use-*` skill sigils become `/use-*`, the Ouroboros sigils `$interview`, `$pm`, `$seed`, and `$qa` become `/interview`, `/pm`, `/seed`, and `/qa` because Ouroboros installs user-scoped skills that ZCode reads natively from `~/.agents/skills`, the separately installed `$deslop` becomes `/deslop`, `request_user_input` becomes `AskUserQuestion`, `Codex goal` becomes `ZCode todo list`, and the inspection script resolves skills from the ZCode roots — `~/.zcode/skills` and the shared `~/.agents/skills` — and diagnoses Ouroboros against this host instead of Codex.

The hook command keeps the `hooks/hooks.json` declaration shape — ZCode auto-loads it — and rewrites `${PLUGIN_ROOT}` to `${ZCODE_PLUGIN_ROOT}`, which ZCode expands for hook processes. That substitution is load-bearing: the Codex spelling is unset under ZCode, so the unsubstituted command expands to `/hooks/task_commit_gate.py`, `python3` exits 2, and `PreToolUse` reads exit 2 as a denial — blocking every `Bash` call. A forbidden needle and a required-text assertion both guard it.

Upstream diagnoses Ouroboros by asking Codex — `ooo codex doctor` for its integration artifacts and `codex mcp get ouroboros --json` for its registration. ZCode has neither probe, and the `ooo zcode` group ships no doctor command. The generated inspector instead reads the registration from the host's config files — `~/.zcode/cli/config.json` user-level, then the project-level `.zcode/config.json` override — under the `mcp.servers` object, and takes that entry as the host-integration signal, because on this host the integration is exactly that entry plus the user-scoped Ouroboros skills. Runtime health comes from `ooo mcp doctor --json` with the `mcp_import` check exempted: the MCP 2 server registered in config launches as a separate process while the CLI environment keeps MCP 1.x, so that check fails on a correctly configured machine. The Mulgae and Gaori MCP probes stay Codex-based, as they do in the Claude and Kimi forks — their deep registration verification is coupled to Codex CLI output upstream.

Skill discovery narrows for the same reason. Upstream resolves user-scoped skills from the Codex and shared cross-agent roots; the generated inspector resolves the ZCode roots alone, because one host's artifact should diagnose one host. ZCode exposes no config-dir environment variable, so the roots are literal. The shared `~/.agents/skills` root needs no substitution: ZCode reads it natively, so Ouroboros, Deslop, and Lora skills installed there are genuinely reachable.

ZCode defines no per-server timeout fields in `mcp.servers`, so the catalog's Mulgae and Gaori entries carry no `startupTimeoutMs`/`toolTimeoutMs` values; host-level MCP deadlines apply, and the CLI fallback paths remain the bounded completion route when a review or test run may exceed them. Lora and Deslop install through `npx skills --agent zcode` into `~/.zcode/skills`; when the same skill already exists in the shared `~/.agents/skills` root, the catalog updates that copy in place rather than creating a duplicate ZCode also loads.

An unmapped sigil is the quiet failure: it is valid Markdown naming a command the reader's host does not have, so neither a forbidden needle nor a required-text assertion notices it, and one needle per known sigil only ever catches the sigils that already exist. Generation therefore rejects any remaining lowercase `$name` in generated Markdown. Uppercase spellings are environment variables the generated tree still needs and do not match.

The `Codex` name is otherwise forbidden in generated text. `tool-catalog.md` is exempt because it names the Codex CLI as a Mulgae provider and a required CLI version, which stays true here. The exemption records the upstream digest it was judged against, so the sync stops when that file changes.

## Upgrade

```bash
git -C upstream fetch --tags origin
git -C upstream checkout <new-tag>
python3 scripts/sync.py
ruby tests/validate.rb
git add -A && git commit
```

Each override records the SHA-256 of the upstream file it came from. When upstream changes one of those files the sync stops and names it, because merging a stale override would ship guidance that no longer matches its source. Re-derive the override against the new upstream content and update `overrides/manifest.json`.

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
