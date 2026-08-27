# Changelog

This file records concise shipped outcomes of the Aquarium for GLM edition. Releases before v0.1.14 are recorded in this repository's GitHub releases; upstream outcomes live in the [Aquarium changelog](https://github.com/irootkernel/aquarium/blob/main/CHANGELOG.md).

## v0.1.14 - Unreleased

### Added

- Add the edition-local `/aquarium:upgrade` skill that walks one full upstream Aquarium release cycle for this repository: pin the submodule to a released tag, resolve every sync abort in order, re-derive overrides and description tunings, validate, and prepare the reviewed release and the local ZCode installation.
- Teach the generation to carry `edition-skills/` into the generated plugin: edition-owned skills ship through the plugin, stop on name collisions with upstream skills, and pass the same frontmatter, tuning, and needle checks as upstream skills.
