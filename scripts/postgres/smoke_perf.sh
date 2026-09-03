#!/bin/bash
set -euo pipefail
sudo -u postgres psql -d vocalguard -c 'SELECT version_num FROM alembic_version;'
sudo -u postgres psql -d vocalguard -c "SELECT indexname FROM pg_indexes WHERE schemaname='public' AND (indexname LIKE 'ix_calls_status%' OR indexname LIKE 'ix_entreprises_%' OR indexname LIKE 'ix_agenda_%' OR indexname LIKE '%trgm%' OR indexname LIKE 'ix_voicemails_read%' OR indexname LIKE 'ix_callers_is_%') ORDER BY 1;"
curl -sf -m 15 http://127.0.0.1:8000/api/v1/entreprises?limit=5 >/dev/null
curl -sf -m 15 http://127.0.0.1:8000/api/v1/voicemails?limit=5 >/dev/null
curl -sf -m 15 'http://127.0.0.1:8000/api/v1/agenda?from_time=2026-01-01T00:00:00&to_time=2026-12-31T00:00:00' >/dev/null
curl -sf -m 15 'http://127.0.0.1:8000/api/v1/clients?limit=10' >/dev/null
curl -sf -m 15 'http://127.0.0.1:8000/api/v1/quotes?limit=10' >/dev/null
echo all_endpoints_ok
