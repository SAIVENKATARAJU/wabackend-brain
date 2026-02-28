# Deploy Backend to Google Cloud Run

## 1. Required env vars (Cloud Run)

Set these in Cloud Run service variables or Secret Manager:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `OPENAI_KEY` (or provider-specific keys)
- `LLM_PROVIDER` (`openai` / `azure_openai` / `gemini`)
- `CRON_SECRET`
- `WEBHOOK_VERIFY_TOKEN`
- `CORS_ORIGINS=https://akasavani.sdmai.org,http://localhost:3000`
- `COOKIE_DOMAIN=.sdmai.org`
- `COOKIE_SECURE=true`
- `COOKIE_SAMESITE=lax`

Optional for ISP TLS issues (temporary):
- `SUPABASE_DISABLE_SSL_VERIFY=true`

## 2. Build + deploy

```bash
cd /Users/saivenkataraju/projects/wabackend-brain
PROJECT_ID=<your-gcp-project-id> REGION=asia-south1 ./deploy_backend.sh
```

## 3. Domain mapping

- Cloud Run -> Service `wabackend-brain` -> Manage custom domains
- Add `api.akasavani.sdmai.org`
- Create DNS records in your DNS provider as instructed by Google

## 4. Frontend config

Set frontend API base URL:

```env
NEXT_PUBLIC_API_URL=https://api.akasavani.sdmai.org
```

## 5. Health check

- `GET https://api.akasavani.sdmai.org/health`

## 6. Notes

- Keep frontend and backend as separate Cloud Run services.
- If cookies are needed across subdomains, use `COOKIE_DOMAIN=.sdmai.org`.
