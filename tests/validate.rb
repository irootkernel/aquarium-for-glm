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

  assert(!path.dirname.join("agents").directory?, "Codex sidecar directory must be dropped: #{name}")
end

if UPSTREAM_PLUGIN.directory?
  upstream_skills = Pathname.glob(UPSTREAM_PLUGIN.join("skills/*/SKILL.md")).map { |p| p.dirname.basename.to_s }.sort
  generated = skill_paths.map { |p| p.dirname.basename.to_s }.sort
  assert(generated == upstream_skills, "generated skills do not match upstream: #{(generated - upstream_skills) | (upstream_skills - generated)}")
end

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
  assert(script.include?("zcode_mcp_scopes"), "inspection must classify Mulgae and Gaori registrations from ZCode config")
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
# upstream directory would otherwise be dropped in silence.
if UPSTREAM_PLUGIN.directory?
  upstream_directories = UPSTREAM_PLUGIN.children.select(&:directory?).map { |p| p.basename.to_s } - [".codex-plugin"]
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
