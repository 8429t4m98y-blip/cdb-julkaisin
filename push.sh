#!/usr/bin/env bash
# CDB-julkaisin — pysyvä push GitHubiin.
# Lukee GH_TOKEN:n keskitetystä .env:stä (../../Instagram API/.env), ei tallenna
# tokenia git-configiin eikä tulosta sitä. Työntää nykyisen mainin originiin,
# jonka jälkeen GitHub Actions -cron julkaisee erääntyneet postaukset.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$DIR/../../Instagram API/.env"
REPO="github.com/8429t4m98y-blip/cdb-julkaisin.git"

if [ ! -f "$ENV_FILE" ]; then
  echo "✗ .env ei löytynyt: $ENV_FILE" >&2; exit 1
fi

TOKEN="$(grep -E '^GH_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '[:space:]')"
if [ -z "${TOKEN:-}" ]; then
  echo "✗ GH_TOKEN puuttuu .env:stä. Lisää rivi: GH_TOKEN=github_pat_..." >&2; exit 1
fi

echo "→ Haetaan origin ja työnnetään main …"
git -C "$DIR" fetch origin --quiet
# Työnnä token-URL:lla; kaiutetaan vain onnistuminen, ei tokenia.
if git -C "$DIR" push "https://x-access-token:${TOKEN}@${REPO}" HEAD:main 2>/tmp/cdb_push_err; then
  echo "✓ Työnnetty GitHubiin. Cron julkaisee erääntyneet postaukset (15 min välein)."
else
  # Siivotaan mahdollinen token pois virheviestistä ennen näyttöä.
  sed "s#x-access-token:[^@]*@#x-access-token:***@#g" /tmp/cdb_push_err >&2
  rm -f /tmp/cdb_push_err
  exit 1
fi
rm -f /tmp/cdb_push_err
