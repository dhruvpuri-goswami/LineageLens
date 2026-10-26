# Security Policy

## Design

- The server binds to `127.0.0.1` only. Do not expose it to a network.
- There is no telemetry, no update check and no remote asset. The UI is fully bundled.
- LineageLens only reads your dbt, Snowflake and Power BI files; it never writes to them.
- The optional Snowflake and Fabric connectors read metadata only. Credentials come from environment variables and are never stored.

## Supported versions

| Version | Supported |
|---|---|
| 2.x | Yes |
| < 2.0 | No |

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private vulnerability reporting: [Report a vulnerability](https://github.com/dhruvpuri-goswami/LineageLens/security/advisories/new) (the repository's *Security* tab), or contact the maintainer, Dhruvpuri Goswami, privately. Include:

- the version (`lineagelens --version` or the sidebar footer),
- the steps to reproduce, using synthetic data only,
- the impact you expect.

You will get an acknowledgement within 7 days. Fixes are released as a patch version and credited in the CHANGELOG, unless you prefer to stay anonymous.
