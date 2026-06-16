#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://localhost:8000"
ADMIN_TOKEN="dev_admin_token_123456"
HMAC_SECRET="dev_hmac_secret_CHANGE_ME_IN_PROD"

if ! command -v jq >/dev/null 2>&1; then
  echo "jq saknas. Installera med: sudo apt install -y jq"
  exit 1
fi

OK=0
FAIL=0

check() {
  local label="$1" expected="$2" actual="$3"
  if [ "$actual" = "$expected" ]; then
    echo "  OK: $label"
    OK=$((OK+1))
  else
    echo "  FAIL: $label (expected=$expected, got=$actual)"
    FAIL=$((FAIL+1))
  fi
}

# ──────────────────────────────────────────
echo "=== 1) Health checks ==="
# ──────────────────────────────────────────
for ep in healthz livez readyz; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/v1/$ep")
  check "$ep" "200" "$CODE"
done

# ──────────────────────────────────────────
echo "=== 2) Skapa tenant ==="
# ──────────────────────────────────────────
TENANT_JSON=$(curl -s -X POST "$BASE_URL/api/v1/tenants" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"name":"Smoke Tenant","plan":"basic"}')

TENANT_ID=$(echo "$TENANT_JSON" | jq -r '.id')
WEBHOOK_URL=$(echo "$TENANT_JSON" | jq -r '.webhook_url')

if [ -z "$TENANT_ID" ] || [ "$TENANT_ID" = "null" ]; then
  echo "  FAIL: Kunde inte skapa tenant"
  exit 1
fi
echo "  OK: tenant=$TENANT_ID"

# ──────────────────────────────────────────
echo "=== 3) Registrera user ==="
# ──────────────────────────────────────────
REG_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE_URL/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d "{\"tenant_id\":\"$TENANT_ID\",\"email\":\"smoke@test.com\",\"password\":\"SmokePass1!\"}")
check "register user" "200" "$REG_CODE"

# ──────────────────────────────────────────
echo "=== 4) Webhook: lead_created via HMAC ==="
# ──────────────────────────────────────────
TS=$(date +%s)
BODY_1=$(cat <<JSON
{
  "tenant_id": "$TENANT_ID",
  "lead_id": "lead-smoke-1",
  "event_id": "evt-smoke-001",
  "event_type": "lead_created",
  "source": "n8n-smoke",
  "timestamp": "$(date -Iseconds)",
  "data": {
    "campaign_id": "camp-smoke",
    "campaign_name": "Smoke Campaign",
    "first_name": "Anna",
    "last_name": "Svensson",
    "email": "anna@example.com",
    "phone": "+46701234567"
  }
}
JSON
)
SIG=$(printf '%s' "$TS.$BODY_1" | openssl dgst -sha256 -hmac "$HMAC_SECRET" | awk '{print $2}')

RESP_1=$(curl -s -X POST "$BASE_URL/api/v1/webhooks/lead-event" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: $TS" \
  -H "X-Signature: $SIG" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d "$BODY_1")
echo "  $RESP_1"
check "lead_created ingested" "true" "$(echo "$RESP_1" | jq -r '.detail | test("ingested")')"

# ──────────────────────────────────────────
echo "=== 5) Webhook: sms_sent via token (ska skapa message_log) ==="
# ──────────────────────────────────────────
RESP_2=$(curl -s -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d "{
    \"lead_id\": \"lead-smoke-1\",
    \"event_id\": \"evt-smoke-002\",
    \"event_type\": \"sms.sent\",
    \"source\": \"n8n-smoke\",
    \"timestamp\": \"$(date -Iseconds)\",
    \"data\": {
      \"campaign_id\": \"camp-smoke\",
      \"provider\": \"smsteknik\",
      \"provider_message_id\": \"sms-ext-001\",
      \"body\": \"Hej Anna! Vi har ett erbjudande.\"
    }
  }")
echo "  $RESP_2"
check "sms_sent ingested" "true" "$(echo "$RESP_2" | jq -r '.detail | test("ingested")')"

# ──────────────────────────────────────────
echo "=== 6) Webhook: duplicate event (ska ignoreras) ==="
# ──────────────────────────────────────────
TS2=$(date +%s)
SIG2=$(printf '%s' "$TS2.$BODY_1" | openssl dgst -sha256 -hmac "$HMAC_SECRET" | awk '{print $2}')

RESP_DUP=$(curl -s -X POST "$BASE_URL/api/v1/webhooks/lead-event" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: $TS2" \
  -H "X-Signature: $SIG2" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d "$BODY_1")
check "duplicate ignored" "true" "$(echo "$RESP_DUP" | jq -r '.detail | test("Duplicate")')"

# ──────────────────────────────────────────
echo "=== 7) Webhook: deal_won (ska inte gora status regression) ==="
# ──────────────────────────────────────────
RESP_WON=$(curl -s -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d "{
    \"lead_id\": \"lead-smoke-1\",
    \"event_id\": \"evt-smoke-003\",
    \"event_type\": \"won\",
    \"source\": \"n8n-smoke\",
    \"timestamp\": \"$(date -Iseconds)\",
    \"data\": {
      \"campaign_id\": \"camp-smoke\",
      \"amount\": 15000,
      \"currency\": \"SEK\"
    }
  }")
check "deal_won ingested" "true" "$(echo "$RESP_WON" | jq -r '.detail | test("ingested")')"

# ──────────────────────────────────────────
echo "=== 8) Webhook: email_sent EFTER deal_won (status ska vara converted) ==="
# ──────────────────────────────────────────
curl -s -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d "{
    \"lead_id\": \"lead-smoke-1\",
    \"event_id\": \"evt-smoke-004\",
    \"event_type\": \"email.sent\",
    \"source\": \"n8n-smoke\",
    \"timestamp\": \"$(date -Iseconds)\",
    \"data\": {\"provider\": \"mailgun\"}
  }" > /dev/null

# Hamta kontakten och verifiera att status fortfarande ar converted
CONTACTS_JSON=$(curl -s "$BASE_URL/api/v1/tenants/$TENANT_ID/contacts" \
  -H "X-Admin-Token: $ADMIN_TOKEN")
CONTACT_STATUS=$(echo "$CONTACTS_JSON" | jq -r '.[0].status')
check "status still converted after email_sent" "converted" "$CONTACT_STATUS"

CONTACT_ID=$(echo "$CONTACTS_JSON" | jq -r '.[0].id')

# ──────────────────────────────────────────
echo "=== 9) Contacts CRUD ==="
# ──────────────────────────────────────────
# List
LIST_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  "$BASE_URL/api/v1/tenants/$TENANT_ID/contacts" \
  -H "X-Admin-Token: $ADMIN_TOKEN")
check "list contacts" "200" "$LIST_CODE"

# Count
COUNT=$(curl -s "$BASE_URL/api/v1/tenants/$TENANT_ID/contacts/count" \
  -H "X-Admin-Token: $ADMIN_TOKEN" | jq -r '.total')
check "contact count >= 1" "true" "$([ "$COUNT" -ge 1 ] && echo true || echo false)"

# Get single
GET_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  "$BASE_URL/api/v1/tenants/$TENANT_ID/contacts/$CONTACT_ID" \
  -H "X-Admin-Token: $ADMIN_TOKEN")
check "get contact" "200" "$GET_CODE"

# Create manual
CREATE_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE_URL/api/v1/tenants/$TENANT_ID/contacts" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"first_name":"Manual","last_name":"Test","email":"manual@test.com","source":"api"}')
check "create contact" "201" "$CREATE_CODE"

# Create duplicate (same email, ska ge 409)
DUP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE_URL/api/v1/tenants/$TENANT_ID/contacts" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"first_name":"Dup","last_name":"Test","email":"manual@test.com"}')
check "duplicate email 409" "409" "$DUP_CODE"

# Patch
PATCH_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X PATCH "$BASE_URL/api/v1/tenants/$TENANT_ID/contacts/$CONTACT_ID" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"first_name":"Anna-Updated"}')
check "patch contact" "200" "$PATCH_CODE"

# Search
SEARCH_JSON=$(curl -s "$BASE_URL/api/v1/tenants/$TENANT_ID/contacts?search=Anna-Updated" \
  -H "X-Admin-Token: $ADMIN_TOKEN")
SEARCH_COUNT=$(echo "$SEARCH_JSON" | jq 'length')
check "search finds updated contact" "true" "$([ "$SEARCH_COUNT" -ge 1 ] && echo true || echo false)"

# ──────────────────────────────────────────
echo "=== 10) Opt-out ==="
# ──────────────────────────────────────────
OPT_OUT_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE_URL/api/v1/tenants/$TENANT_ID/contacts/$CONTACT_ID/opt-out" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"channel":"sms","source":"smoke_test","reason":"STOP reply"}')
check "opt-out sms" "200" "$OPT_OUT_CODE"

# Verifiera flagga
OPTED=$(curl -s "$BASE_URL/api/v1/tenants/$TENANT_ID/contacts/$CONTACT_ID" \
  -H "X-Admin-Token: $ADMIN_TOKEN" | jq -r '.opted_out_sms')
check "opted_out_sms = true" "true" "$OPTED"

# Opt-out history
HIST_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  "$BASE_URL/api/v1/tenants/$TENANT_ID/contacts/$CONTACT_ID/opt-out-events" \
  -H "X-Admin-Token: $ADMIN_TOKEN")
check "opt-out history" "200" "$HIST_CODE"

# Opt-in
OPT_IN_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE_URL/api/v1/tenants/$TENANT_ID/contacts/$CONTACT_ID/opt-in" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"channel":"sms","source":"smoke_test"}')
check "opt-in sms" "200" "$OPT_IN_CODE"

OPTED_AFTER=$(curl -s "$BASE_URL/api/v1/tenants/$TENANT_ID/contacts/$CONTACT_ID" \
  -H "X-Admin-Token: $ADMIN_TOKEN" | jq -r '.opted_out_sms')
check "opted_out_sms = false after opt-in" "false" "$OPTED_AFTER"

# ──────────────────────────────────────────
echo "=== 11) Webhook: opt_out via event ==="
# ──────────────────────────────────────────
curl -s -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d "{
    \"lead_id\": \"lead-smoke-1\",
    \"event_id\": \"evt-smoke-005\",
    \"event_type\": \"stop\",
    \"source\": \"sms-reply\",
    \"timestamp\": \"$(date -Iseconds)\",
    \"data\": {\"reason\": \"Customer replied STOP\"}
  }" > /dev/null

OPTED_VIA_WH=$(curl -s "$BASE_URL/api/v1/tenants/$TENANT_ID/contacts/$CONTACT_ID" \
  -H "X-Admin-Token: $ADMIN_TOKEN" | jq -r '.opted_out_sms')
check "opt-out via webhook event" "true" "$OPTED_VIA_WH"

# ──────────────────────────────────────────
echo "=== 12) Message logs ==="
# ──────────────────────────────────────────
# List (ska ha rader fran sms_sent + email_sent events)
MSG_LIST=$(curl -s "$BASE_URL/api/v1/tenants/$TENANT_ID/message-logs" \
  -H "X-Admin-Token: $ADMIN_TOKEN")
MSG_COUNT=$(echo "$MSG_LIST" | jq 'length')
check "message_logs >= 2" "true" "$([ "$MSG_COUNT" -ge 2 ] && echo true || echo false)"

# Filter by contact
MSG_CONTACT=$(curl -s "$BASE_URL/api/v1/tenants/$TENANT_ID/message-logs?contact_id=$CONTACT_ID" \
  -H "X-Admin-Token: $ADMIN_TOKEN" | jq 'length')
check "message_logs for contact >= 1" "true" "$([ "$MSG_CONTACT" -ge 1 ] && echo true || echo false)"

# POST manual message log
POST_MSG_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE_URL/api/v1/tenants/$TENANT_ID/message-logs" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d "{
    \"contact_id\": \"$CONTACT_ID\",
    \"channel\": \"sms\",
    \"direction\": \"outbound\",
    \"provider\": \"smsteknik\",
    \"body\": \"Manuellt loggat SMS\",
    \"status\": \"sent\"
  }")
check "POST message-log" "201" "$POST_MSG_CODE"

# Invalid channel (ska ge 422)
BAD_CH_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE_URL/api/v1/tenants/$TENANT_ID/message-logs" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d "{\"contact_id\":\"$CONTACT_ID\",\"channel\":\"telegram\",\"status\":\"sent\"}")
check "invalid channel 422" "422" "$BAD_CH_CODE"

# ──────────────────────────────────────────
echo "=== 13) Metrics overview ==="
# ──────────────────────────────────────────
OVERVIEW=$(curl -s "$BASE_URL/api/v1/metrics/overview?tenant_id=$TENANT_ID" \
  -H "X-Admin-Token: $ADMIN_TOKEN")

OV_CONTACTS=$(echo "$OVERVIEW" | jq -r '.total_contacts')
OV_EVENTS=$(echo "$OVERVIEW" | jq -r '.total_lead_events')
OV_MSGS=$(echo "$OVERVIEW" | jq -r '.total_messages')
OV_REVENUE=$(echo "$OVERVIEW" | jq -r '.total_revenue')

check "overview total_contacts >= 1" "true" "$([ "$OV_CONTACTS" -ge 1 ] && echo true || echo false)"
check "overview total_lead_events >= 3" "true" "$([ "$OV_EVENTS" -ge 3 ] && echo true || echo false)"
check "overview total_messages >= 2" "true" "$([ "$OV_MSGS" -ge 2 ] && echo true || echo false)"
check "overview revenue > 0" "true" "$(echo "$OV_REVENUE > 0" | bc -l | grep -q 1 && echo true || echo false)"

# ──────────────────────────────────────────
echo "=== 14) Failed events ==="
# ──────────────────────────────────────────
FE_LIST_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  "$BASE_URL/api/v1/tenants/$TENANT_ID/failed-events" \
  -H "X-Admin-Token: $ADMIN_TOKEN")
check "list failed-events" "200" "$FE_LIST_CODE"

FE_COUNT=$(curl -s "$BASE_URL/api/v1/tenants/$TENANT_ID/failed-events/count" \
  -H "X-Admin-Token: $ADMIN_TOKEN" | jq -r '.total')
check "failed-events count = 0" "0" "$FE_COUNT"

# ──────────────────────────────────────────
echo ""
echo "=== RESULTAT: $OK OK, $FAIL FAIL ==="

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi