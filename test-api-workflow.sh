#!/bin/bash

# Complete API Workflow Test

API_URL="https://8eoswo3gj4.execute-api.us-east-1.amazonaws.com/prod"

echo "========================================"
echo "AI Demo Builder - API Workflow Test"
echo "========================================"
echo ""

# Step 1: Analyze GitHub Repo
echo "Step 1: Analyzing GitHub Repository..."
echo "========================================"
ANALYZE_RESPONSE=$(curl -s -X POST "$API_URL/analyze" \
  -H "Content-Type: application/json" \
  -d '{"github_url": "https://github.com/anthropics/anthropic-sdk-python"}')

echo "Response:"
echo "$ANALYZE_RESPONSE" | jq '.' 2>/dev/null || echo "$ANALYZE_RESPONSE"
echo ""

# Step 2: Get AI Suggestions (this creates the session)
echo "Step 2: Getting AI Suggestions & Creating Session..."
echo "====================================================="

SUGGESTIONS_RESPONSE=$(curl -s -X POST "$API_URL/suggestions" \
  -H "Content-Type: application/json" \
  -d "$ANALYZE_RESPONSE")

echo "Response:"
echo "$SUGGESTIONS_RESPONSE" | jq '.' 2>/dev/null || echo "$SUGGESTIONS_RESPONSE"
echo ""

# Extract session_id from suggestions response
SESSION_ID=$(echo "$SUGGESTIONS_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('session_id', ''))" 2>/dev/null)

if [ -z "$SESSION_ID" ]; then
    echo "❌ Failed to extract session_id from suggestions"
    echo "Suggestions response: $SUGGESTIONS_RESPONSE"
    exit 1
fi

echo "✅ Session created: $SESSION_ID"
echo ""

# Step 3: Get Upload URL
echo "Step 3: Getting Upload URL..."
echo "========================================"
UPLOAD_RESPONSE=$(curl -s -X POST "$API_URL/upload-url" \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"suggestion_id\": 1,
    \"filename\": \"demo-video.mp4\"
  }")

echo "Response:"
echo "$UPLOAD_RESPONSE" | jq '.' 2>/dev/null || echo "$UPLOAD_RESPONSE"
echo ""

# Extract upload URL
UPLOAD_URL=$(echo "$UPLOAD_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('upload_url', ''))" 2>/dev/null)

if [ ! -z "$UPLOAD_URL" ]; then
    echo "✅ Upload URL generated"
    echo "   URL: ${UPLOAD_URL:0:80}..."
else
    echo "⚠️  No upload URL in response"
fi
echo ""

# Step 4: Check Status
echo "Step 3: Checking Status..."
echo "========================================"
STATUS_RESPONSE=$(curl -s -X GET "$API_URL/status/$SESSION_ID")

echo "Response:"
echo "$STATUS_RESPONSE" | jq '.' 2>/dev/null || echo "$STATUS_RESPONSE"
echo ""

# Summary
echo "========================================"
echo "Test Summary"
echo "========================================"
echo "Session ID: $SESSION_ID"
echo ""
echo "Next steps:"
echo "1. Upload a video to the presigned URL"
echo "2. Generate final video: curl -X POST $API_URL/generate/$SESSION_ID"
echo ""