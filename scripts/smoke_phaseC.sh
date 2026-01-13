#!/usr/bin/env bash
# scripts/smoke_phaseC.sh — Phase C2: Minimal smoke tests for core invariants
#
# Tests:
#   a) /health returns 200
#   b) Requests without session_id return 400
#   c) Requests with valid session_id return 200
#   d) Memory isolation across two session_ids
#   e) Write guards (empty input fails, duplicate skipped)
#
# Usage: ./scripts/smoke_phaseC.sh [base_url]
#   base_url defaults to http://127.0.0.1:8000

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
PASS_COUNT=0
FAIL_COUNT=0

# Helper: print test result
pass() {
    echo "✓ PASS: $1"
    ((PASS_COUNT++)) || true
}

fail() {
    echo "✗ FAIL: $1"
    ((FAIL_COUNT++)) || true
}

# Helper: check HTTP status code
check_status() {
    local expected=$1
    local actual=$2
    local test_name=$3
    
    if [ "$actual" -eq "$expected" ]; then
        pass "$test_name (expected $expected, got $actual)"
        return 0
    else
        fail "$test_name (expected $expected, got $actual)"
        return 1
    fi
}

# Helper: make curl request and capture status code
curl_status() {
    curl -s -o /dev/null -w "%{http_code}" "$@"
}

# Helper: make curl request and capture response body
curl_body() {
    curl -s "$@"
}

echo "============================================================"
echo "AIr4 Phase C2 Smoke Tests"
echo "Base URL: $BASE_URL"
echo "============================================================"
echo

# Test a) /health returns 200
echo "[Test a] Health check"
HEALTH_STATUS=$(curl_status "$BASE_URL/health")
if check_status 200 "$HEALTH_STATUS" "GET /health"; then
    HEALTH_BODY=$(curl_body "$BASE_URL/health")
    if echo "$HEALTH_BODY" | grep -q '"ok"'; then
        pass "Health response contains 'ok'"
    else
        fail "Health response missing 'ok'"
    fi
fi
echo

# Create two test sessions
echo "[Setup] Creating test sessions"
SESSION1_RESPONSE=$(curl_body -X POST "$BASE_URL/sessions")
SESSION1_ID=$(echo "$SESSION1_RESPONSE" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)

SESSION2_RESPONSE=$(curl_body -X POST "$BASE_URL/sessions")
SESSION2_ID=$(echo "$SESSION2_RESPONSE" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "$SESSION1_ID" ] || [ -z "$SESSION2_ID" ]; then
    fail "Failed to create test sessions"
    echo "SESSION1_RESPONSE: $SESSION1_RESPONSE"
    echo "SESSION2_RESPONSE: $SESSION2_RESPONSE"
    exit 1
fi

pass "Created session1: $SESSION1_ID"
pass "Created session2: $SESSION2_ID"
echo

# Test b) Requests without session_id return 400
echo "[Test b] Missing session_id validation"
MEMORY_ADD_NO_SESSION=$(curl_status -X POST \
    -H "Content-Type: application/json" \
    -d '{"text":"test message for validation"}' \
    "$BASE_URL/memory/add")
check_status 400 "$MEMORY_ADD_NO_SESSION" "POST /memory/add without session_id"
echo

# Test c) Requests with valid session_id return 200
echo "[Test c] Valid session_id acceptance"
MEMORY_ADD_VALID=$(curl_status -X POST \
    -H "Content-Type: application/json" \
    -d '{"text":"This is a test message for session isolation"}' \
    "$BASE_URL/memory/add?session_id=$SESSION1_ID")
check_status 200 "$MEMORY_ADD_VALID" "POST /memory/add with valid session_id"
echo

# Test e) Write guards - empty input fails
echo "[Test e.1] Write guard: empty text fails"
EMPTY_TEXT_STATUS=$(curl_status -X POST \
    -H "Content-Type: application/json" \
    -d '{"text":""}' \
    "$BASE_URL/memory/add?session_id=$SESSION1_ID")
check_status 400 "$EMPTY_TEXT_STATUS" "POST /memory/add with empty text"
echo

# Test e) Write guards - whitespace-only fails
echo "[Test e.2] Write guard: whitespace-only text fails"
WHITESPACE_STATUS=$(curl_status -X POST \
    -H "Content-Type: application/json" \
    -d '{"text":"   "}' \
    "$BASE_URL/memory/add?session_id=$SESSION1_ID")
check_status 400 "$WHITESPACE_STATUS" "POST /memory/add with whitespace-only text"
echo

# Test e) Write guards - too short fails
echo "[Test e.3] Write guard: text too short fails"
SHORT_TEXT_STATUS=$(curl_status -X POST \
    -H "Content-Type: application/json" \
    -d '{"text":"abc"}' \
    "$BASE_URL/memory/add?session_id=$SESSION1_ID")
check_status 400 "$SHORT_TEXT_STATUS" "POST /memory/add with text < 5 chars"
echo

# Test e) Write guards - duplicate skipped
echo "[Test e.4] Write guard: duplicate text skipped"
DUPLICATE_TEXT="This is a duplicate test message for session one"
# Add first time
FIRST_ADD=$(curl_body -X POST \
    -H "Content-Type: application/json" \
    -d "{\"text\":\"$DUPLICATE_TEXT\"}" \
    "$BASE_URL/memory/add?session_id=$SESSION1_ID")
if echo "$FIRST_ADD" | grep -q '"ok"'; then
    pass "First add succeeded"
else
    fail "First add failed: $FIRST_ADD"
fi

# Add duplicate (should be skipped)
DUPLICATE_ADD=$(curl_body -X POST \
    -H "Content-Type: application/json" \
    -d "{\"text\":\"$DUPLICATE_TEXT\"}" \
    "$BASE_URL/memory/add?session_id=$SESSION1_ID")
if echo "$DUPLICATE_ADD" | grep -q '"skipped"'; then
    pass "Duplicate add correctly skipped"
else
    fail "Duplicate add not skipped: $DUPLICATE_ADD"
fi
echo

# Test d) Memory isolation across two session_ids
echo "[Test d] Memory isolation across sessions"
# Add unique text to session1
ISOLATION_TEXT="This is unique text for session one isolation test"
curl_body -X POST \
    -H "Content-Type: application/json" \
    -d "{\"text\":\"$ISOLATION_TEXT\"}" \
    "$BASE_URL/memory/add?session_id=$SESSION1_ID" > /dev/null

# Add different text to session2
curl_body -X POST \
    -H "Content-Type: application/json" \
    -d '{"text":"This is unique text for session two isolation test"}' \
    "$BASE_URL/memory/add?session_id=$SESSION2_ID" > /dev/null

# Search in session1 - should find session1's text
SEARCH_SESSION1=$(curl_body "$BASE_URL/memory/search?q=isolation&session_id=$SESSION1_ID&k=10")
if echo "$SEARCH_SESSION1" | grep -q "session one"; then
    pass "Session1 search finds session1's text"
else
    fail "Session1 search did not find session1's text"
fi

# Search in session1 - should NOT find session2's text
if echo "$SEARCH_SESSION1" | grep -q "session two"; then
    fail "Session1 search found session2's text (isolation violation)"
else
    pass "Session1 search correctly excludes session2's text"
fi

# Search in session2 - should find session2's text
SEARCH_SESSION2=$(curl_body "$BASE_URL/memory/search?q=isolation&session_id=$SESSION2_ID&k=10")
if echo "$SEARCH_SESSION2" | grep -q "session two"; then
    pass "Session2 search finds session2's text"
else
    fail "Session2 search did not find session2's text"
fi

# Search in session2 - should NOT find session1's text
if echo "$SEARCH_SESSION2" | grep -q "session one"; then
    fail "Session2 search found session1's text (isolation violation)"
else
    pass "Session2 search correctly excludes session1's text"
fi
echo

# Summary
echo "============================================================"
echo "Test Summary"
echo "============================================================"
echo "Passed: $PASS_COUNT"
echo "Failed: $FAIL_COUNT"
echo

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo "✓ All tests passed!"
    exit 0
else
    echo "✗ Some tests failed"
    exit 1
fi
