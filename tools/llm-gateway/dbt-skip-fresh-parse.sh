#!/bin/sh
# DBT_PATH for dbt-mcp. dbt-mcp runs `dbt parse` before every lineage/details lookup,
# which costs ~4s even when nothing changed. Skip it when no project file is newer than
# target/manifest.json; pass every other command to the real dbt. entrypoint.sh runs one
# real parse at start, so the manifest is fresh after `dbt deps` and refresh.sh.
set -eu
REAL_DBT=/opt/envs/dbt/.venv/bin/dbt

cmd=""
for arg in "$@"; do
  case "$arg" in -*) ;; *) cmd=$arg; break ;; esac
done

if [ "$cmd" = parse ]; then
  cd "${DBT_PROJECT_DIR:-.}"
  manifest=target/manifest.json
  if [ -f "$manifest" ] && [ -z "$(find . \( -path ./target -o -path ./dbt_packages -o -path ./logs \) -prune \
        -o -type f -newer "$manifest" -print -quit)" ]; then
    exit 0
  fi
fi
exec "$REAL_DBT" "$@"
