# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.3.0] - 2026-10-26

### Added
- **Load your data** page (sidebar, dashboard and Settings): separate drop zones for dbt `manifest.json` (required for dbt), `catalog.json` (recommended), Snowflake view `.sql` files, a Power BI PBIP folder or `.zip`, and `.pbix` files (layout only). Each file is validated on arrival (type, size, dbt schema, `CREATE VIEW`, PBIP contents) and shown as OK, Warning or Error. Project name, default database and default schema fields, a Scan button with progress, **Use my data** and **Remove my data** with confirmation.
- Upload API (`/api/upload`, `/api/upload/files/{slot}`, `/api/upload/scan`, `/api/upload/activate`, `/api/upload/workspace`). Files are streamed to `LINEAGELENS_HOME/workspace/<project>/` (never `/inputs`), a `lineagelens.yml` is generated for them, and the uploaded project stays active after a restart.
- Settings `LINEAGELENS_ALLOW_UPLOAD` (default `true`), `LINEAGELENS_MAX_UPLOAD_MB` (500), `LINEAGELENS_MAX_UNZIPPED_MB` (2000) and `LINEAGELENS_MAX_ZIP_FILES` (20000).
- `docs/github-about.md` with the repository description and topics.
- Tests for uploads: validation, traversal, zip-slip, symlinks, zip bombs, size limits, header and origin checks, persistence and CLI precedence.

### Security
- Upload paths are normalised and refused when absolute, using drive letters, `..`, control or reserved characters, or overlong segments. Only an allow-list of extensions is kept. Zips are checked for zip-slip, symlinks, encryption, entry count, declared and real unpacked size.
- Upload requests need the `X-Requested-With: LineageLens` header in addition to the Origin and Host checks. Other JSON requests keep the 5 MB body limit.

### Changed
- Data precedence: `--config` / `--sample` on the command line, then uploaded data, then `LINEAGELENS_CONFIG`, then the sample.
- README rewritten: shorter, with a walk-through, a features table, collapsible reference sections and new screenshots in `docs/screenshots/`.
- New dependency: `python-multipart` 0.0.32 (hash-locked).

### Fixed
- Top-bar search: the shortcut hint no longer wraps or touches the edge. It now shows two keycaps, `Ctrl` `K` (or `⌘` `K` on macOS), that are hidden on narrow screens. The box is 36 px high, with an accent focus ring and the placeholder "Search columns, measures, visuals". Clicking anywhere in the box or pressing Ctrl/Cmd+K opens it.

## [2.2.0] - 2026-10-26

### Added
- New brand in `docs/brand/`: an original mark (a source node traced along one orthogonal path to the node it lands on), a wordmark set in Inter SemiBold and converted to outlines, light, dark and monochrome variants, favicons (SVG, ICO, PNG 16/32/48/180/192/512) and a 1280×640 GitHub social preview. `tools/brand/build_brand.py` regenerates the SVGs.
- `[project.urls]` in `pyproject.toml` and repository metadata in `frontend/package.json`.

### Changed
- UI restyled to a flat, neutral design: one blue accent, neutral greys, 1 px borders, 6-8 px radii, no gradients, glows or decorative shadows, denser controls and plain wording.
- Node-type colours reduced to one hue per layer family (source, dbt, Snowflake, Power BI model, measures, RLS, report).
- The support button is now a small "Sponsor" text link in the sidebar footer. It stays hidden until `BUYMEACOFFEE_URL` is set to a real page (a value containing `YOUR_USERNAME` counts as unset).
- `GITHUB_REPO_URL` now defaults to https://github.com/dhruvpuri-goswami/LineageLens. README, CONTRIBUTING, SECURITY and issue-template links point to the repository.
- README screenshots retaken.

## [2.1.0] - 2026-10-26

### Added
- Docker: multi-stage `Dockerfile` (Node build stage, slim Python 3.12 runtime), non-root user, `HEALTHCHECK` on `/api/health`.
- `docker-compose.yml`: published on `127.0.0.1:8765` only, named data volume, `./inputs` mounted read-only, `restart: unless-stopped`, read-only root filesystem, all capabilities dropped, `no-new-privileges`.
- `.env.example` documenting every setting, `.dockerignore`, `inputs/README.md`.
- Settings from environment variables (`LINEAGELENS_*`, `BUYMEACOFFEE_URL`, `GITHUB_REPO_URL`) and an optional `.env` file.
- Structured logging (`LINEAGELENS_LOG_FORMAT=json`) with a request log and request ids.
- Security middleware: CSP and other security headers, `Host` allow-list (DNS-rebinding protection), cross-origin write blocking, request size limit.
- Path safety for config and diff paths (NUL / length checks, suffix checks, optional `LINEAGELENS_ALLOWED_ROOTS`), and `LINEAGELENS_ALLOW_CONFIG_WRITE`.
- `requirements.lock`: every runtime dependency pinned with hashes for all platforms.
- `Makefile` and `setup.ps1` (Windows setup without Docker), and `.gitattributes` for consistent line endings.
- CI builds the Docker image and smoke-tests `/api/health`.
- 13 security and settings tests (61 in total).

### Changed
- Errors are returned as JSON (`error`, `detail`) without stack traces; unexpected errors are logged.
- API docs (`/api/docs`) are off by default because Swagger UI loads from a CDN; enable with `LINEAGELENS_ENABLE_DOCS=true`.
- The theme bootstrap script moved out of `index.html` so the CSP needs no inline scripts.
- Uvicorn runs without the `Server` header, access log or reload.
- Sample and test host names use `example` domains.

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
