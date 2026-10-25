# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.0.0] - 2026-10-25

### Added
- A new lineage map renderer:
  - swim lanes per layer and crossing minimisation;
  - groups (tables, measure folders, pages) that collapse automatically, with expand/collapse all;
  - merged edges between groups;
  - hover-to-trace, click-to-focus and isolate a path;
  - depth, type and confidence filters, and search inside the graph;
  - minimap, zoom/fit controls, full-screen mode and keyboard shortcuts;
  - Overview (lane summary) and Table views;
  - PNG and SVG export.
- A large synthetic sample, *Helios Retail Group* (about 940 objects, 7 reports, 151 visuals). Pick it in Settings or use `serve --sample large`.
- A redesigned dashboard:
  - a "Which column are you changing?" search with recent and suggested columns;
  - four insight cards, each with why it matters and a link to the details;
  - collapsible scan details and a how-it-works guide.
- Example refactor and empty states in the Change Simulator.
- Buy-me-a-coffee and Star-on-GitHub links, configured in `lineagelens/links.py` or with environment variables, and hidden when empty.
- Open-source files: LICENSE (MIT), CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, issue and PR templates, and a CI workflow.

### Changed
- New design system: tokens, a sectioned sidebar, a header with breadcrumbs, page descriptions, glossary tooltips, motion, and a refined dark mode.
- `/api/health` now also returns `version` and `links`.

### Removed
- The React Flow and dagre dependencies (replaced by the custom renderer).

## [1.0.0] - 2026-10-24

### Added
- First release:
  - parsers for dbt, Snowflake, TMDL/BIM, PBIR/legacy reports, DAX and M;
  - Impact Explorer, Upstream Trace, Change Simulator, Catalog and Settings;
  - HTML, XLSX, CSV and JSON exports, the CLI, and CI examples.
