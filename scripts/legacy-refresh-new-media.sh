#!/usr/bin/env bash
set -Eeuo pipefail

# Refresh metadata for items created recently. Secrets are deliberately not
# stored in this script: use EMBY_TOKEN or let it read the newest active token
# from Emby's local authentication database.
EMBY_URL="${EMBY_URL:-http://127.0.0.1:8096}"
DELAY="${EMBY_REFRESH_DELAY:-4}"
MINUTES="${EMBY_REFRESH_MINUTES:-60}"
AUTH_DB="${EMBY_AUTH_DB:-/root/docker-compose/emby/config/data/authentication.db}"

token="${EMBY_TOKEN:-}"
if [[ -z "$token" && -s "$AUTH_DB" ]]; then
  token="$(python3 - "$AUTH_DB" <<'PY'
import sqlite3
import sys

db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True, timeout=10)
try:
    row = db.execute(
        "SELECT AccessToken FROM Tokens_2 "
        "WHERE IsActive=1 ORDER BY DateLastActivityInt DESC LIMIT 1"
    ).fetchone()
finally:
    db.close()
print(row[0] if row and row[0] else "")
PY
)"
fi

if [[ -z "$token" ]]; then
  echo "No active Emby token found; skipping recent-item refresh." >&2
  exit 0
fi

since_date="$(date -u -d "-${MINUTES} minutes" +"%Y-%m-%dT%H:%M:%SZ")"
payload="$(curl --fail --silent --show-error --get \
  --data-urlencode "Recursive=true" \
  --data-urlencode "IncludeItemTypes=Movie,Series,Season,Episode,MusicVideo,BoxSet" \
  --data-urlencode "MinDateCreated=${since_date}" \
  --data-urlencode "SortBy=DateCreated" \
  --data-urlencode "SortOrder=Ascending" \
  --data-urlencode "Fields=Id" \
  --data-urlencode "Limit=1000" \
  -H "X-Emby-Token: ${token}" \
  "${EMBY_URL%/}/emby/Items")"

mapfile -t item_ids < <(jq -r '.Items[]?.Id // empty' <<<"$payload" | sort -u)
if ((${#item_ids[@]} == 0)); then
  echo "No Emby items created in the last ${MINUTES} minutes."
  exit 0
fi

echo "Refreshing metadata for ${#item_ids[@]} recent Emby item(s)."
count=0
for item_id in "${item_ids[@]}"; do
  curl --fail --silent --show-error -X POST \
    -H "X-Emby-Token: ${token}" \
    "${EMBY_URL%/}/emby/Items/${item_id}/Refresh?Recursive=true&MetadataRefreshMode=FullRefresh&ImageRefreshMode=Default&ReplaceAllMetadata=true&ReplaceAllImages=false" \
    >/dev/null
  count=$((count + 1))
  echo "Refreshed ${count}/${#item_ids[@]}: ${item_id}"
  sleep "$DELAY"
done
