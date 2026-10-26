# inputs/

> **Easier option:** open **Load your data** in the app and upload the same files from
> your browser. No config file is needed, and uploads are stored in the data volume
> (`/data/workspace/`), not here. Uploaded data takes precedence over this folder until
> you click **Remove my data**.

Docker Compose mounts this folder **read-only** at `/inputs` in the container.
Put your own exported files here. Nothing in this folder is committed (see `.gitignore`)
and nothing leaves your computer.

```
inputs/
  lineagelens.yml            # your config (paths relative to this file)
  dbt/target/manifest.json   # from `dbt compile`
  dbt/target/catalog.json    # from `dbt docs generate`
  snowflake/views/*.sql      # CREATE VIEW DDL not managed by dbt (optional)
  powerbi/Sales.SemanticModel/   # PBIP / TMDL folders
  powerbi/Sales.Report/
```

Minimal `lineagelens.yml`:

```yaml
project_name: My analytics
dbt:
  - project_dir: dbt
snowflake:
  view_dirs: [snowflake/views]
  default_database: ANALYTICS
  default_schema: REPORTING
powerbi:
  search_dirs: [powerbi]
```

Then run `docker compose restart` and click **Re-scan** in the app.
Without `lineagelens.yml` the app shows the bundled synthetic sample.
