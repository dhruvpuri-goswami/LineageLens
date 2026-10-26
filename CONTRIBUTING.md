# Contributing to LineageLens

Thanks for helping! LineageLens is a small, local-first tool, and its guiding rules are:

1. **Deterministic.** No AI, LLM or RAG. Every lineage link must come from a parser rule that can be explained.
2. **Local and private.** No telemetry, no CDN assets, and no outbound calls unless the user turns on an optional connector.
3. **Synthetic data only.** Never commit or attach real company SQL, dbt models, Power BI files or data. Reproduce bugs with the bundled samples, or with a minimal anonymised example.

## Development setup

```bash
git clone https://github.com/dhruvpuri-goswami/LineageLens.git
cd LineageLens
python -m venv .venv
.venv/bin/pip install -e ".[dev]"        # Windows: .venv\Scripts\pip install -e ".[dev]"
.venv/bin/python -X warn_default_encoding -m pytest   # or: make test

cd frontend
npm ci
npm run typecheck && npm test
npm run dev        # http://localhost:5173, proxies /api to :8765
npm run build      # writes the production UI to lineagelens/static
```

Run the backend while you develop the UI: `.venv/bin/lineagelens serve --no-browser` (add `--sample large` for the big sample).

## Issues and pull requests

- Report bugs and request features in [GitHub Issues](https://github.com/dhruvpuri-goswami/LineageLens/issues). Use the templates.

- Keep each PR focused, and add or adjust tests (pytest for parsers and the API, vitest for the graph layout).
- Run `python -X warn_default_encoding -m pytest`, `npm run typecheck`, `npm test` and `npm run build` before you push. CI runs the same checks on Linux, macOS and Windows.
- Always pass `encoding="utf-8"` (or `"utf-8-sig"` for files Windows tools may save with a BOM) to `open()`, `read_text()` and `write_text()`. The test suite turns an implicit locale encoding into an error.
- Keep the generated reports and console output plain text (no emoji); they are read in Windows consoles and CI logs.
- For UI changes, include a screenshot in light **and** dark mode. Follow the existing design tokens in `frontend/src/index.css` (one accent colour, neutral greys, 1 px borders, 6-8 px radii).
- Add a line to `CHANGELOG.md` under *Unreleased*.

## Adding a parser rule

Parsers live in `lineagelens/extractors/`. Add a synthetic fixture to `lineagelens/samples/` (or to a test) that shows the construct, and assert the resulting edges and their confidence. If a construct cannot be resolved exactly, emit a warning instead of guessing.

## Regenerating the samples

`tools/make_samples.py` and `tools/make_large_sample.py` regenerate the synthetic projects. The output must stay fictional.
