#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-}"
REGION="${REGION:-asia-south1}"
REPO="${REPO:-akasavani}"
SERVICE="${SERVICE:-wabackend-brain}"
IMAGE="${IMAGE:-wabackend-brain}"
DOMAIN="${DOMAIN:-api.akasavani.sdmai.org}"

if [[ -z "$PROJECT_ID" ]]; then
  echo "Set PROJECT_ID env var first"
  exit 1
fi

gcloud config set project "$PROJECT_ID"

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

gcloud artifacts repositories create "$REPO"   --repository-format=docker   --location="$REGION"   --description="Akasavani containers" || true

gcloud builds submit --config cloudbuild.yaml   --substitutions=_REGION="$REGION",_REPO="$REPO",_SERVICE="$SERVICE",_IMAGE="$IMAGE"

SERVICE_URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"

echo "Cloud Run URL: $SERVICE_URL"
echo "Map custom domain in Cloud Run console to: $DOMAIN"
