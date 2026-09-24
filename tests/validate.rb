#!/usr/bin/env ruby
# frozen_string_literal: true

# Validates the invariants that are specific to the ZCode artifact.
#
# Upstream owns the prose contract and already validates it in its own CI, so
# this file deliberately does not re-assert skill wording. It checks only what
# the transformation is responsible for: frontmatter shape, host-neutral text,
# manifest agreement, and freshness against the pinned upstream.

require "json"
require "pathname"
require "set"
require "yaml"

ROOT = Pathname.new(__dir__).parent
PLUGIN = ROOT.join("plugins/aquarium")
MANIFEST = PLUGIN.join(".zcode-plugin/plugin.json")
MARKETPLACE = ROOT.join("marketplace.json")
UPSTREAM_PLUGIN = ROOT.join("upstream/plugins/aquarium")

failures = []

def assert(condition, message)
  return if condition

  warn "error: #{message}"
  exit 1
end

# --- generated tree exists -------------------------------------------------

assert(PLUGIN.directory?, "plugins/aquarium/ has not been generated; run scripts/sync.py")
assert(MANIFEST.file?, ".zcode-plugin/plugin.json has not been generated; run scripts/sync.py")
assert(MARKETPLACE.file?, "marketplace.json is missing from the repository root")

skill_paths = Pathname.glob(PLUGIN.join("skills/*/SKILL.md")).sort
assert(!skill_paths.empty?, "no skills were generated")

sync_manifest = JSON.parse(PLUGIN.join("sync-manifest.json").read)
assert(sync_manifest.dig("upstream", "commit").to_s.length == 40, "sync manifest lacks an upstream commit")

# --- frontmatter shape ------------------------------------------------------

# ZCode reads only `name` and `description` from skill frontmatter and has no
# per-skill invocation gating, so any other key would be dead configuration
# implying a mechanism the host lacks. The upstream sidecar directories that
# carried the policy on Codex must be gone along with their `$` prompts.
ALLOWED_FRONTMATTER_KEYS = %w[description name].freeze

skill_paths.each do |path|
  name = path.dirname.basename.to_s
  frontmatter = path.read.match(/\A---\n(.*?)\n---\n/m)
  assert(frontmatter, "missing frontmatter: #{name}")

  metadata = YAML.safe_load(frontmatter[1], aliases: false)
  assert((metadata.keys - ALLOWED_FRONTMATTER_KEYS).empty?, "unexpected frontmatter keys: #{name}")
  assert(metadata.key?("name") && metadata.key?("description"), "frontmatter must define name and description: #{name}")
  assert(metadata.fetch("name") == name, "skill name/path mismatch: #{name}")
  assert(metadata.fetch("description").include?("Use when"), "description lacks trigger: #{name}")
  # The description is the only skill surface the host exposes to the model,
  # and this edition tunes it around the invocation name; a description that
  # lost the name would break that convention silently.
  assert(
    metadata.fetch("description").include?("/aquarium:#{name}"),
    "description must name the skill's invocation form: #{name}"
  )

  assert(!path.dirname.join("agents").directory?, "Codex sidecar directory must be dropped: #{name}")
end

if UPSTREAM_PLUGIN.directory?
  # The generated skill set is the upstream set minus the deliberate skill
  # exclusions plus every edition skill carried in by the generation; a drift
  # on any side fails here. v0.1.17 excludes `status`: it is the entrypoint
  # over the aquarium-status runtime this edition does not bundle.
  EXCLUDED_SKILLS = %w[status].freeze
  upstream_skills = Pathname.glob(UPSTREAM_PLUGIN.join("skills/*/SKILL.md")).map { |p| p.dirname.basename.to_s }.sort - EXCLUDED_SKILLS
  edition_skills = Pathname.glob(ROOT.join("edition-skills/*/SKILL.md")).map { |p| p.dirname.basename.to_s }.sort
  expected = (upstream_skills + edition_skills).sort
  generated = skill_paths.map { |p| p.dirname.basename.to_s }.sort
  assert(generated == expected, "generated skills do not match upstream minus exclusions plus edition skills: #{(generated - expected) | (expected - generated)}")
end

# --- bundled runtimes are excluded -------------------------------------------

# v0.1.17 excludes the upstream-bundled runtimes: `tools/` carries the
# aquarium-dev channel manager and the aquarium-status reporter, each owning
# machine-global singleton state (~/.aquarium-dev/, ~/.aquarium) that has one
# owner per machine — the upstream Codex edition. No plugin MCP server is
# registered, the status skill and the development-channel contract leave
# with their runtimes, and these assertions pin that decision from the other
# side: nothing may reappear silently.
assert(!PLUGIN.join("tools").directory?, "tools/ must stay excluded; this edition bundles no runtimes")
assert(!PLUGIN.join(".mcp.json").file?, ".mcp.json must stay absent; this edition registers no plugin MCP server")
assert(!PLUGIN.join("skills/status").directory?, "the status skill must stay excluded with its runtime")
assert(!PLUGIN.join("references/development-contract.md").file?, "the development-channel contract must stay excluded with its runtime")

# --- host-neutral generated text -------------------------------------------

# `~/.agents/skills` and AGENTS.md are deliberately absent: ZCode reads
# both natively, so upstream wording about them stays correct here.
FORBIDDEN_TEXT = ["$aquarium:", "$use-", "$lore-", "$orca-cli", "request_user_input",
                  "--agent codex", ".codex/skills", "${PLUGIN_ROOT}", "Codex"].freeze

# Some upstream text names the Codex CLI as a third-party tool rather than as the
# host — a Mulgae provider, a required CLI version — and stays correct here. Each
# exemption is gated on the upstream bytes a human reviewed, so `sync.py` stops
# when that file changes. Only the `Codex` needle is skipped, and only for these.
CODEX_EXEMPTIONS = begin
  path = ROOT.join("overrides/codex-exemptions.json")
  path.file? ? JSON.parse(path.read).keys.to_set : Set.new
end

# The files the edition hand-authors inside the generated tree; everything
# else under plugins/aquarium/ that exists upstream is carried bytes.
OVERRIDE_PATHS = begin
  path = ROOT.join("overrides/manifest.json")
  path.file? ? JSON.parse(path.read).keys.to_set : Set.new
end

Pathname.glob(PLUGIN.join("**/*.{md,json,py,yaml}")).sort.each do |path|
  relative = path.relative_path_from(PLUGIN).to_s
  next if relative == "sync-manifest.json"

  text = path.read
  FORBIDDEN_TEXT.each do |needle|
    next if needle == "Codex" && CODEX_EXEMPTIONS.include?(relative)

    assert(!text.include?(needle), "generated text contains `#{needle}`: #{relative}")
  end
end

# `FORBIDDEN_TEXT` names one needle per sigil family that already exists, so a
# family upstream introduces later passes it and ships Codex invocation syntax
# in silence. Uppercase spellings are environment variables and do not match.
SIGIL = /\$[a-z][a-z0-9:_-]*/.freeze

Pathname.glob(PLUGIN.join("**/*.md")).sort.each do |path|
  found = path.read.scan(SIGIL).uniq.sort
  assert(
    found.empty?,
    "generated text contains Codex skill sigils #{found.join(', ')}: " \
    "#{path.relative_path_from(PLUGIN)}"
  )
end

assert(
  skill_paths.any? { |path| path.read.include?("/aquarium:") },
  "generated skills never reference the ZCode invocation form"
)

inspection = PLUGIN.join("skills/dev-setup/scripts/inspect_tools.py")
if inspection.file?
  script = inspection.read
  assert(script.include?('".zcode/skills"'), "inspection must search the ZCode skill root")
  assert(script.include?('".agents/skills"'), "inspection must search the shared cross-agent skill root")
  assert(script.include?('".zcode/cli/config.json"'), "inspection must read the ZCode MCP registration")
  assert(script.include?('"host_integration"'), "inspection must report the host integration component")
  assert(script.include?('"runtime_package"'), "inspection must report the Ouroboros runtime-package axis")
  assert(script.include?("zcode_mcp_scopes"), "inspection must classify Mulgae and Gaori registrations from ZCode config")
  # v0.1.16 routes the user-global MCP view through `inspect_global_mcp_scope`;
  # the ZCode restatement lives in the project inspector's replacement, so assert
  # the delegation target rather than a local implementation.
  assert(script.include?("inspect_global_mcp_scope"), "inspection must restate the user-global MCP view on the ZCode config scopes")
  assert(script.include?('"handler_contract_status"'), "inspection must report the Podway handler-contract axis")
  assert(script.include?("aquarium-dev-setup-inspection.v21"), "inspection must keep its schema marker")
  # v0.1.17 moves the writing skills back to the running host's default skill
  # root. The surgery restates `effective_codex_skill_root` to the one ZCode
  # root — the name stays for upstream callers, the body is this host's — and
  # every caller resolves through it, so the restatement and its use in the
  # trusted-skill map are pinned while the Codex-home env read stays gone.
  assert(script.include?('def effective_codex_skill_root() -> Path:'), "inspection must keep the restated skill-root helper")
  assert(script.include?('return Path.home() / ".zcode/skills"'), "the skill-root helper must resolve to the ZCode root")
  assert(script.include?('"humanize-korean": effective_codex_skill_root() / "humanize-korean"'), "the trusted global-skill map must route humanize-korean through the host skill root")
  assert(!script.include?('os.environ.get("CODEX_HOME")'), "inspection must not resolve skill targets through a Codex home")
  # v0.1.17 lifts Ouroboros' upper bound — this host already runs a stable
  # release past the old ceiling — so the unbounded range must arrive.
  assert(script.include?('tool["supported_range"] = ">=0.51.1"'), "the Ouroboros supported range must be unbounded above the floor")
  assert(!script.include?("<0.54.0"), "the Ouroboros supported range must not keep the old ceiling")
end

# --- reviewer backend restatement ---------------------------------------------

# Upstream v0.1.14 builds the shared review contract around Dolgorae
# captures. This edition runs independent-review on the host's own Agent
# tool, so the contract is restated for that backend. No forbidden needle
# covers the word "Dolgorae" alone, so a substitution that stopped matching
# would ship the upstream backend silently; these assertions pin the
# restated half of the contract.
review_contract = PLUGIN.join("references/review-contract.md")
if review_contract.file?
  contract = review_contract.read
  assert(!contract.include?("Dolgorae capture"), "the review contract must not offer Dolgorae captures on this backend")
  assert(contract.include?("Live index read"), "the review contract must name the live staged acquisition")
  assert(contract.include?("Resolved commit blobs"), "the review contract must name the committed acquisition")
  assert(
    contract.include?("dispatches fresh reviewer subagents through the host's own Agent tool"),
    "the review contract must describe the subagent backend"
  )
end

independent_review = PLUGIN.join("skills/independent-review/SKILL.md")
if independent_review.file?
  review_skill = independent_review.read
  assert(review_skill.include?("`Agent` tool"), "independent-review must dispatch through the host Agent tool")
  assert(!review_skill.include?("dolgorae specialist review"), "independent-review must not run the Dolgorae operation")
  assert(review_skill.include?("[finding-disposition.md](../../references/finding-disposition.md)"), "independent-review must load the shared disposition contract")
end

# v0.1.16 rewrote orca-review's unsupported-scope sentence around upstream's
# disabled entrypoint; no forbidden needle covers that claim, so the restated
# boundary is pinned here — the disabled framing must not ship while this
# edition's entrypoint is the enabled native route.
orca_review_path = PLUGIN.join("skills/orca-review/SKILL.md")
if orca_review_path.file?
  orca_review = orca_review_path.read
  assert(!orca_review.include?("Independent Review is disabled"), "orca-review must not carry upstream's disabled-entrypoint framing")
  assert(orca_review.include?("/aquarium:independent-review"), "orca-review must name the subagent review route")
  assert(orca_review.include?("no route is an automatic fallback"), "orca-review must keep the explicit-selection boundary")
end

# --- v0.1.15 bundled aquarium-dev package and global inspector ----------------

# v0.1.17 excludes the bundled runtimes with `tools/`; the v0.1.15 arrival
# guards for the aquarium-dev package leave with it, and the v0.1.14 Dolgorae
# release verifier is gone upstream as well. The global inspector stays, on
# the v0.1.17 v5 schema with the two bundled-runtime members absent: the
# component-vocabulary substitution removed them, and the absence is pinned
# here so neither can reappear as a broken probe against a missing runtime.
assert(
  !PLUGIN.join("skills/dev-setup-global/scripts/verify_dolgorae_release.py").file?,
  "the Dolgorae release verifier left with upstream v0.1.17"
)
global_inspection = PLUGIN.join("skills/dev-setup-global/scripts/inspect_global_tools.py")
if global_inspection.file?
  global_script = global_inspection.read
  assert(global_script.include?("aquarium-dev-setup-global-inspection.v5"), "the global inspector must keep its schema marker")
  # v0.1.16 reduces the global MCP wrapper to a host-neutral delegation; the
  # ZCode restatement lives in the project inspector's replacement, so assert
  # the delegation target rather than a local implementation.
  assert(global_script.include?("inspector.inspect_global_mcp_scope"), "the global MCP view must delegate to the restated inspector helper")
  assert(!global_script.include?('"aquarium-dev"'), "the global inspector must not carry the excluded aquarium-dev component")
  assert(!global_script.include?('"aquarium-status"'), "the global inspector must not carry the excluded aquarium-status component")
  assert(!global_script.include?("inspect_aquarium_status"), "the excluded aquarium-status inspector must be gone with its import")
end
ouroboros_inspection = PLUGIN.join("skills/dev-setup-global/scripts/inspect_ouroboros.py")
if ouroboros_inspection.file?
  ouroboros_script = ouroboros_inspection.read
  assert(
    ouroboros_script.include?("no_per_home_integration_on_zcode"),
    "the Ouroboros inspection must report the single-surface ZCode restatement"
  )
  assert(
    ouroboros_script.include?("shared_root_skills"),
    "the Ouroboros inspection must report the shared-root skill inventory"
  )
  # v0.1.17 adds shared-root conflict detection; on this host byte-matching
  # shared-root copies are the canonical installation and only non-matching
  # name conflicts degrade, so both keys must arrive from the surgery.
  assert(
    ouroboros_script.include?('"shared_skill_conflicts"'),
    "the Ouroboros inspection must report shared-root conflicts"
  )
end

# The test-setup inspector ships host-neutral from upstream; the schema marker
# guards that it survives the transformation whole.
testing = PLUGIN.join("skills/test-setup/scripts/inspect_testing.py")
if testing.file?
  assert(
    testing.read.include?("aquarium-test-setup-inspection.v1"),
    "the test-setup inspector must keep its schema marker"
  )
end

# --- v0.1.16 review intent restatement --------------------------------------

# Upstream v0.1.16 disables its Dolgorae-backed Independent Review entrypoint
# and frames the new shared intent contract around that refusal and a native
# Codex subagent route. This edition's entrypoint is enabled and IS the native
# ZCode subagent route, so the restated surfaces must carry that stance; no
# forbidden needle covers these phrases, so a substitution that stopped
# matching would ship the disabled framing silently.
intent_contract = PLUGIN.join("references/review-intent-contract.md")
if intent_contract.file?
  contract = intent_contract.read
  assert(contract.include?("## Route an Independent Review request"), "the intent contract must route through the enabled entrypoint")
  assert(contract.include?("## Use a native ZCode review subagent"), "the intent contract must name the native ZCode subagent route")
  assert(!contract.include?("disabled `/aquarium:independent-review`"), "the intent contract must not carry the disabled-entrypoint framing")
  assert(!contract.include?("native Codex"), "the intent contract must not name the Codex host's route")
end
finding_disposition = PLUGIN.join("references/finding-disposition.md")
if finding_disposition.file?
  disposition = finding_disposition.read
  assert(
    disposition.include?("dispatched by `/aquarium:independent-review`"),
    "the disposition contract must name the enabled reviewer-subagent backend"
  )
  assert(!disposition.include?("dormant Independent Review"), "the disposition contract must not carry the dormant-route framing")
  assert(!disposition.include?("native Codex"), "the disposition contract must not name the Codex host's route")
end

# --- v0.1.17 review-routing restatement --------------------------------------

# Upstream v0.1.17 adds the selectable review-routing contract: workflows
# choose one of `mulgae`, `orca`, `native-codex`, or `waived`. The route
# token is a machine identifier carried by the byte-identical Procedure
# mirrors and the route-neutral evidence fields, so it ships verbatim while
# the prose names this host: the native route dispatches through the host's
# own `Agent` tool. No forbidden needle covers the lowercase token or the
# lowercase "native codex" spelling, so the restated surfaces are pinned.
routing_contract = PLUGIN.join("references/review-routing-contract.md")
if routing_contract.file?
  routing = routing_contract.read
  assert(routing.include?("`native-codex`"), "the routing contract must keep the native route token as a machine identifier")
  assert(routing.include?("native ZCode"), "the routing contract must name the native ZCode route")
  assert(!routing.include?("native Codex"), "the routing contract must not name the Codex host's route")
  assert(
    routing.include?("a fresh subagent dispatched through the host's own `Agent` tool"),
    "the routing contract must name the Agent-tool dispatch for the native route"
  )
end
%w[
  skills/task-review/SKILL.md
  skills/task-handler/SKILL.md
  skills/epic-handler/SKILL.md
  skills/epic-validator/SKILL.md
  skills/task-close/SKILL.md
  skills/task-commit/SKILL.md
  references/evidence-residency.md
  references/finding-disposition.md
  references/procedure-node-contracts.md
].each do |relative|
  path = PLUGIN.join(relative)
  next unless path.file?

  text = path.read
  assert(!text.include?("native Codex"), "the native route must be named for this host: #{relative}")
  assert(text.include?("native ZCode") || text.include?("`native-codex`"), "the native route must stay addressable: #{relative}")
end
# The Mulgae default portfolio routes every role to ZCode, which runs the
# user's configured GLM model on this host; the catalog restatement names
# that positioning and the v0.1.23 machine contracts it rides on.
catalog_path = PLUGIN.join("references/tool-catalog.md")
if catalog_path.file?
  catalog = catalog_path.read
  assert(catalog.include?("GLM-native host"), "the tool catalog must keep the GLM-native positioning")
  assert(catalog.include?("v0.1.23"), "the tool catalog must carry the Mulgae v0.1.23 floor")
  assert(catalog.include?("grok-4.7"), "the tool catalog must carry the Grok model pin as a third-party fact")
  assert(catalog.include?("gpt-5.6-sol"), "the tool catalog must carry the Codex model pin as a third-party fact")
  assert(catalog.include?("5b88e99bfaed0643b4bfb1c035f9c4acdc476d05"), "the tool catalog must carry the v0.2.11 use-podway pin")
  assert(!catalog.include?("9014225982e4c316237e0d6e35052414d2dbc770"), "the superseded use-podway hotfix pin must be gone")
  assert(catalog.include?("`>=0.51.1` without an upper bound"), "the tool catalog must carry the unbounded Ouroboros range")
end

# --- manifests agree with upstream -----------------------------------------

manifest = JSON.parse(MANIFEST.read)
assert(manifest.fetch("skills") == "./skills/", "plugin manifest must point at ./skills/")
assert(manifest.fetch("license") == "MIT", "plugin license must be MIT")
assert(!manifest.fetch("description").include?("Codex"), "plugin description must not name Codex")
assert(!manifest.key?("hooks"), "ZCode auto-loads hooks/hooks.json; the manifest must not declare hooks")

if UPSTREAM_PLUGIN.directory?
  codex = JSON.parse(UPSTREAM_PLUGIN.join(".codex-plugin/plugin.json").read)
  %w[name version homepage license keywords].each do |key|
    assert(manifest.fetch(key) == codex.fetch(key), "plugin manifest field `#{key}` diverges from upstream")
  end
  upstream_author = codex.fetch("author")
  upstream_author = upstream_author.fetch("name") if upstream_author.is_a?(Hash)
  assert(manifest.fetch("author") == upstream_author, "plugin manifest field `author` diverges from upstream")
end

# --- plugin MCP manifest ----------------------------------------------------

# v0.1.15 registered the bundled aquarium-dev MCP server in a root
# `.mcp.json`; v0.1.17 excludes the runtime with `tools/`, so no plugin MCP
# manifest is generated at all. The absence is asserted above with the other
# bundled-runtime exclusions; nothing here derives a server manifest.

# --- marketplace shape ------------------------------------------------------

# ZCode probes `.claude-plugin/marketplace.json` and then a root
# `marketplace.json`; this repository ships the root file, which is also the
# name the official marketplace is served under.
marketplace = JSON.parse(MARKETPLACE.read)
assert(marketplace.fetch("name") == "aquarium-for-glm", "marketplace must be named aquarium-for-glm")
plugins = marketplace.fetch("plugins")
assert(plugins.length == 1, "the marketplace must list exactly one plugin")
entry = plugins.fetch(0)
assert(entry.fetch("name") == "aquarium", "the marketplace entry must name the aquarium plugin")
assert(entry.fetch("source") == "./plugins/aquarium", "the marketplace entry must point at ./plugins/aquarium")

# --- generated tree covers upstream ----------------------------------------

# `COPIED_DIRECTORIES` is an allowlist with no counterpart check, so a new
# upstream directory would otherwise be dropped in silence. `tools/` is the
# recorded v0.1.17 exclusion — this edition bundles no runtimes — so it is
# subtracted here alongside the manifest directory that never copies.
if UPSTREAM_PLUGIN.directory?
  upstream_directories = UPSTREAM_PLUGIN.children.select(&:directory?).map { |p| p.basename.to_s } - [".codex-plugin", "tools"]
  upstream_directories.sort.each do |name|
    assert(PLUGIN.join(name).directory?, "generated plugin is missing upstream directory `#{name}/`")
  end
end

# --- roadmap commit hook ----------------------------------------------------

# ZCode auto-loads hooks/hooks.json from the plugin root, so the nested
# upstream declaration survives and must not be declared in the manifest.
hooks_path = PLUGIN.join("hooks/hooks.json")
assert(hooks_path.file?, "hooks/hooks.json must stay in the generated tree")
gate_path = PLUGIN.join("hooks/task_commit_gate.py")
assert(gate_path.file?, "the roadmap commit hook script was not generated")

hooks = JSON.parse(hooks_path.read).fetch("hooks").fetch("PreToolUse")
assert(hooks.length == 1, "hooks.json must declare exactly one PreToolUse entry")
hook_entry = hooks.fetch(0)
assert(hook_entry.fetch("matcher") == "^Bash$", "the commit hook must match Bash only")
commands = hook_entry.fetch("hooks")
assert(commands.length == 1, "the commit hook entry must declare exactly one command")
command = commands.fetch(0)

# ZCode provides ZCODE_PLUGIN_ROOT to hook processes. Under the Codex
# spelling the shell expands nothing, `python3` cannot open the gate script,
# and it exits 2 — which PreToolUse reads as deny. Every Bash call would be
# blocked, so assert the correct spelling positively and the wrong one
# negatively.
assert(
  command.fetch("command") == 'python3 "${ZCODE_PLUGIN_ROOT}/hooks/task_commit_gate.py"',
  "the commit hook must resolve its script through ZCODE_PLUGIN_ROOT: #{command.fetch('command')}"
)

gate = gate_path.read
assert(gate.include?("/aquarium:task-commit"), "the commit hook must name the ZCode invocation form")
assert(gate.include?("permissionDecision"), "the commit hook must use the PreToolUse permission protocol")
assert(!gate.match?(%r{https?://}), "the commit hook must stay local")

# --- managed Podway procedures ----------------------------------------------

# The integration contract requires the installed copies to be byte-identical to
# these sources, so the procedure IDs must survive transformation untouched.
if UPSTREAM_PLUGIN.directory?
  Pathname.glob(PLUGIN.join("assets/podway/procedures/*.yaml")).sort.each do |path|
    relative = path.relative_path_from(PLUGIN)
    assert(
      path.binread == UPSTREAM_PLUGIN.join(relative).binread,
      "managed Podway procedure must be byte-identical to upstream: #{relative}"
    )
    assert(
      YAML.safe_load(path.read, aliases: false).fetch("id") == path.basename(".yaml").to_s,
      "managed Podway procedure id must match its filename: #{relative}"
    )
  end
end

# --- documentation convention ----------------------------------------------

def structural?(line)
  # Match the stripped line: an indented sub-bullet is still structural, and
  # classifying it as prose makes two adjacent ones look hard-wrapped.
  stripped = line.strip
  stripped.empty? || stripped.match?(/\A(?:\#{1,6}\s|[-*+]\s|\d+\.\s|>|\||<)/)
end

Pathname.glob(ROOT.join("**/*.md")).reject { |p| p.to_s.include?("/upstream/") }.sort.each do |path|
  # v0.1.15 ships some carried references (mulgae-review-contract.md,
  # gaori-integration.md) with hand-wrapped prose. Upstream owns the
  # wrapping of files it authored, so anything carried at an upstream path
  # is skipped — substitution rules rewrite words, never wrapping — while
  # edition-authored content stays under the convention: overrides, edition
  # skills, and repository docs.
  relative = path.relative_path_from(ROOT)
  carried = relative.to_s.start_with?("plugins/aquarium/")
  carried_relative = relative.sub(%r{\Aplugins/aquarium/}, "")
  next if carried && UPSTREAM_PLUGIN.join(carried_relative).file? && !OVERRIDE_PATHS.include?(carried_relative)

  fenced = false
  in_frontmatter = false
  previous_prose = false
  path.read.lines.each_with_index do |line, index|
    stripped = line.chomp
    if index.zero? && stripped == "---"
      in_frontmatter = true
      next
    end
    if in_frontmatter
      in_frontmatter = false if stripped == "---"
      next
    end
    if stripped.start_with?("```")
      fenced = !fenced
      previous_prose = false
      next
    end
    next if fenced

    prose = !structural?(stripped)
    if prose && previous_prose
      failures << "#{path.relative_path_from(ROOT)}:#{index + 1}: hard-wrapped prose"
    end
    previous_prose = prose
  end
end

assert(failures.empty?, "hard-wrapped prose found:\n#{failures.join("\n")}")

puts "validated #{skill_paths.length} generated skills and ZCode artifact invariants"
