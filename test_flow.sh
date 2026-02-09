#!/bin/bash
# Test the backend flow using curls
USER_ID="78558f43-7e6e-46dd-beb6-bc868ad87460"
BASE_URL="http://localhost:8001"

echo "1. Health Check"
curl -s "$BASE_URL/health" | jq .
echo ""

echo "2. Dashboard Stats (should work with mock auth)"
curl -s -H "Authorization: Bearer $USER_ID" "$BASE_URL/dashboard/stats" | jq .
echo ""

echo "3. List Conversations (Should be empty initially)"
curl -s -H "Authorization: Bearer $USER_ID" "$BASE_URL/conversations/" | jq .
echo ""

# To make this E2E real, we need data.
# Since we don't have a POST /conversations endpoint (it comes via webhooks),
# let's try to list contacts to see if any exist.
echo "4. List Contacts"
curl -s -H "Authorization: Bearer $USER_ID" "$BASE_URL/contacts/" | jq .
echo ""
