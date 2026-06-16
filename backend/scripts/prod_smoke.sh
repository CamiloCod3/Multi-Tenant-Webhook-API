#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"

# Dessa bör i prod komma från .env/.env.production
ADMIN_TOKEN="${TENANT_ADMIN_TOKEN:-dev_admin_token_123456}"
METRICS_TOKEN="${METRICS_TOKEN:-dev_metrics_token_123456}"
HMAC_SECRET="${HMAC_SECRET:-dev_hmac_secret_CHANGE_ME_IN_PROD}"

echo "🔍 PROD SMOKE / SECURITY CHECK"

if ! command -v jq >/dev/null 2>&1; then
  echo "❌ jq saknas. Installera med: sudo apt install -y jq"
  exit 1
fi

echo
echo "1) Health checks"
curl -s "${BASE_URL}/api/v1/healthz"  && echo
curl -s "${BASE_URL}/api/v1/livez"   && echo
curl -s "${BASE_URL}/api/v1/readyz"  && echo

echo
echo "2) Admin endpoints utan/fel token (ska vara 401)"

STATUS=$(curl -s -o /tmp/no_admin_tenants.json -w "%{http_code}" \
  -X POST "${BASE_URL}/api/v1/tenants" \
  -H "Content-Type: application/json" \
  -d '{"name":"Should Fail","plan":"basic"}')

echo "   /tenants utan X-Admin-Token → HTTP $STATUS"
grep -q "401" <<< "$STATUS" || echo "   ⚠️ förväntade 401 här"

STATUS=$(curl -s -o /tmp/bad_admin_tenants.json -w "%{http_code}" \
  -X POST "${BASE_URL}/api/v1/tenants" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: WRONG_TOKEN" \
  -d '{"name":"Should Fail 2","plan":"basic"}')

echo "   /tenants med fel X-Admin-Token → HTTP $STATUS"
grep -q "401" <<< "$STATUS" || echo "   ⚠️ förväntade 401 här"

STATUS=$(curl -s -o /tmp/no_admin_metrics_overview.json -w "%{http_code}" \
  "${BASE_URL}/api/v1/metrics/overview")

echo "   /metrics/overview utan X-Admin-Token → HTTP $STATUS"
grep -q "401" <<< "$STATUS" || echo "   ⚠️ förväntade 401 här"

echo
echo "3) Skapa tenant med korrekt X-Admin-Token (ska funka)"

TENANT_JSON=$(curl -s \
  -X POST "${BASE_URL}/api/v1/tenants" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: ${ADMIN_TOKEN}" \
  -d '{"name":"ProdSmoke Tenant","plan":"basic"}')

echo "$TENANT_JSON"
TENANT_ID=$(echo "$TENANT_JSON" | jq -r '.id')
echo "TENANT_ID = ${TENANT_ID}"

if [ -z "$TENANT_ID" ] || [ "$TENANT_ID" = "null" ]; then
  echo "❌ Kunde inte skapa tenant – avbryter."
  exit 1
fi

echo
echo "4) Auth / register edge cases (endast via X-Admin-Token)"

echo "   4.1) För kort / svagt lösen (ska ge 422)"
BAD_REG_STATUS=$(curl -s -o /tmp/bad_reg.json -w "%{http_code}" \
  -X POST "${BASE_URL}/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: ${ADMIN_TOKEN}" \
  -d "{
    \"tenant_id\": \"${TENANT_ID}\",
    \"email\": \"shortpw@example.com\",
    \"password\": \"abc\"
  }")

echo "   /auth/register med för kort pw → HTTP $BAD_REG_STATUS"
grep -q "422" <<< "$BAD_REG_STATUS" || echo "   ⚠️ förväntade 422 här"

echo "   4.2) Normal register (ska funka)"
REG_JSON=$(curl -s \
  -X POST "${BASE_URL}/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: ${ADMIN_TOKEN}" \
  -d "{
    \"tenant_id\": \"${TENANT_ID}\",
    \"email\": \"prodsmoke@example.com\",
    \"password\": \"DemoPass123!\"
  }")

echo "$REG_JSON"

echo
echo "5) Webhook security edge cases (lead-event)"

BODY_JSON=$(cat <<EOF
{
  "tenant_id": "${TENANT_ID}",
  "lead_id": "lead-edge",
  "event_id": "evt-edge-1",
  "event_type": "lead_created",
  "source": "n8n-prodsmoke",
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "data": {
    "campaign_id": "camp-edge",
    "campaign_name": "Edge Test Kampanj"
  }
}
EOF
)

echo "   5.1) Utan signatur (ska bli 401)"
WS1_STATUS=$(curl -s -o /tmp/ws1.json -w "%{http_code}" \
  -X POST "${BASE_URL}/api/v1/webhooks/lead-event" \
  -H "Content-Type: application/json" \
  -d "$BODY_JSON")
echo "   webhook utan signatur → HTTP $WS1_STATUS"

echo "   5.2) Med fel signatur (ska bli 401)"
BAD_TS=$(date +%s)
BAD_SIG="deadbeef"
WS2_STATUS=$(curl -s -o /tmp/ws2.json -w "%{http_code}" \
  -X POST "${BASE_URL}/api/v1/webhooks/lead-event" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: ${BAD_TS}" \
  -H "X-Signature: ${BAD_SIG}" \
  -d "$BODY_JSON")
echo "   webhook fel signatur → HTTP $WS2_STATUS"

echo "   5.3) Expired timestamp (> 5 min, ska bli 401)"
OLD_TS=$(( $(date +%s) - 600 ))

SIG_OLD=$(HMAC_SECRET="$HMAC_SECRET" OLD_TS="$OLD_TS" BODY_JSON="$BODY_JSON" python3 - <<'PY'
import hmac, hashlib, os
secret = os.environ["HMAC_SECRET"].encode()
ts = os.environ["OLD_TS"].encode()
body = os.environ["BODY_JSON"].encode()
msg = ts + b"." + body
print(hmac.new(secret, msg, hashlib.sha256).hexdigest())
PY
)

WS3_STATUS=$(curl -s -o /tmp/ws3.json -w "%{http_code}" \
  -X POST "${BASE_URL}/api/v1/webhooks/lead-event" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: ${OLD_TS}" \
  -H "X-Signature: ${SIG_OLD}" \
  -d "$BODY_JSON")
echo "   webhook expired timestamp → HTTP $WS3_STATUS"

echo "   5.4) Korrekt signatur (ska bli 200)"
CUR_TS=$(date +%s)

SIG_OK=$(HMAC_SECRET="$HMAC_SECRET" CUR_TS="$CUR_TS" BODY_JSON="$BODY_JSON" python3 - <<'PY'
import hmac, hashlib, os
secret = os.environ["HMAC_SECRET"].encode()
ts = os.environ["CUR_TS"].encode()
body = os.environ["BODY_JSON"].encode()
msg = ts + b"." + body
print(hmac.new(secret, msg, hashlib.sha256).hexdigest())
PY
)

WS4_RESP=$(curl -s \
  -X POST "${BASE_URL}/api/v1/webhooks/lead-event" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: ${CUR_TS}" \
  -H "X-Signature: ${SIG_OK}" \
  -d "$BODY_JSON")
echo "   webhook korrekt signatur → $WS4_RESP"

echo
echo "6) Prometheus /metrics – token-skydd"

MET_NOHDR_STATUS=$(curl -s -o /tmp/metrics_nohdr.txt -w "%{http_code}" \
  "${BASE_URL}/metrics")
echo "   /metrics utan X-Metrics-Token → HTTP $MET_NOHDR_STATUS"

MET_BAD_STATUS=$(curl -s -o /tmp/metrics_bad.txt -w "%{http_code}" \
  -H "X-Metrics-Token: WRONG_TOKEN" \
  "${BASE_URL}/metrics")
echo "   /metrics med fel X-Metrics-Token → HTTP $MET_BAD_STATUS"

MET_OK_STATUS=$(curl -s -o /tmp/metrics_ok.txt -w "%{http_code}" \
  -H "X-Metrics-Token: ${METRICS_TOKEN}" \
  "${BASE_URL}/metrics")
echo "   /metrics med korrekt X-Metrics-Token → HTTP $MET_OK_STATUS"

echo
echo "7) Rate limiting-test (trycka över 30/min på metrics/overview)"

COUNT_429=0
for i in $(seq 1 40); do
  CODE=$(curl -s -o /tmp/rl_${i}.json -w "%{http_code}" \
    "${BASE_URL}/api/v1/metrics/overview" \
    -H "X-Admin-Token: ${ADMIN_TOKEN}" \
    -H "X-Tenant-ID: ${TENANT_ID}")
  if [ "$CODE" = "429" ]; then
    COUNT_429=$((COUNT_429+1))
  fi
done
echo "   Fick $COUNT_429 st 429-svar vid 40 requests (förväntat ~10)."

echo
echo "✅ PROD SMOKE / SECURITY CHECK klar"
