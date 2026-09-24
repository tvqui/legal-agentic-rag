# Operations

Run `run.bat help` from the repository root. Long-running services (`online`
and `frontend`) should use separate terminals.

Copy `.env.example` to `.env` only when local overrides are needed. Keep
secrets in `.env`; do not commit `.env`, `data/`, `artifacts/`, `build/`, or
human-review records.

The ONLINE release archive belongs in `build/releases/`. If the archive is
replaced, update its SHA-256 and expected build fingerprints together in all
`config/online*.yaml` files; never mix reports or indexes from different
builds.
