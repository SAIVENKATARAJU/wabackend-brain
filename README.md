Akasavani Backend Implementation Plan
"Stop chasing. Start closing." — An AI-powered follow-up automation platform

Executive Summary
Akasavani is an AI-powered follow-up automation platform designed to help teams automate email follow-ups, reminders, and multi-channel communication. Based on the UI analysis, the platform orchestrates follow-ups across email (Gmail/Outlook), calendar, Slack, and CRM (Salesforce) with features like:

AI-drafted follow-ups with customizable tone presets
Smart nudges with timezone-aware scheduling
Escalation workflows with approval gates
Morning digests summarizing overnight activity
Multi-channel delivery (Email, Slack, Calendar)
Technology Stack Recommendation
Layer	Technology	Rationale
Backend Framework	Python (FastAPI)	Async-first, excellent for AI/ML, type-safe
Database	Supabase PostgreSQL	Real-time subscriptions, Row-Level Security, Auth built-in
Queue/Jobs	Supabase Edge Functions + pg_cron	Serverless, cost-effective, native integration
AI/LLM	OpenAI GPT-4 / Azure OpenAI	Best-in-class for tone adaptation & drafting
Auth	Supabase Auth + OAuth 2.1	Social logins (Google, Slack), PKCE support
Integrations	Gmail API, Google Calendar API, Slack API, Salesforce REST	Native webhooks + polling hybrid
Hosting	Google Cloud Run	Auto-scaling, pay-per-use, container-native
Monitoring	Supabase Dashboard + Cloud Logging	Built-in observability
Phase 1: MVP (Core Follow-up Engine)
Goal: Deliver a working follow-up automation system with Gmail integration and basic AI drafting.

Timeline: 4-6 weeks

1.1 Database Schema
sql
-- Core Tables
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    timezone TEXT DEFAULT 'UTC',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL, -- 'gmail', 'outlook', 'slack', 'salesforce'
    access_token TEXT ENCRYPTED,
    refresh_token TEXT ENCRYPTED,
    token_expires_at TIMESTAMPTZ,
    scopes TEXT[],
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, provider)
);
CREATE TABLE contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    name TEXT,
    company TEXT,
    timezone TEXT,
    crm_id TEXT, -- Salesforce ID if synced
    tags TEXT[],
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, email)
);
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES contacts(id),
    thread_id TEXT NOT NULL, -- Gmail thread ID
    subject TEXT,
    channel TEXT DEFAULT 'email', -- 'email', 'slack'
    status TEXT DEFAULT 'active', -- 'active', 'resolved', 'snoozed'
    tags TEXT[], -- Added for UI support
    last_message_at TIMESTAMPTZ,
    last_reply_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE nudges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id),
    contact_id UUID REFERENCES contacts(id),
    scheduled_at TIMESTAMPTZ NOT NULL,
    sent_at TIMESTAMPTZ,
    status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'sent', 'cancelled', 'failed'
    channel TEXT DEFAULT 'email',
    tone TEXT DEFAULT 'warm', -- 'warm', 'professional', 'urgent'
    draft_content TEXT,
    approved_content TEXT,
    escalation_level INT DEFAULT 0,
    max_escalations INT DEFAULT 2,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE tone_presets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    system_prompt TEXT NOT NULL,
    examples JSONB DEFAULT '[]',
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE digests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    digest_date DATE NOT NULL,
    summary TEXT,
    nudges_scheduled INT DEFAULT 0,
    nudges_sent INT DEFAULT 0,
    conversations_moved INT DEFAULT 0,
    pending_approvals INT DEFAULT 0,
    delivered_at TIMESTAMPTZ,
    channel TEXT DEFAULT 'email', -- 'email', 'slack'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, digest_date)
);
-- Indexes for performance
CREATE INDEX idx_nudges_scheduled ON nudges(scheduled_at) WHERE status = 'pending';
CREATE INDEX idx_nudges_user_status ON nudges(user_id, status);
CREATE INDEX idx_conversations_user_status ON conversations(user_id, status);
CREATE INDEX idx_integrations_user ON integrations(user_id);
-- Index for tag search
CREATE INDEX idx_conversations_tags ON conversations USING GIN(tags);
1.2 API Endpoints (MVP)
Authentication
├── POST   /auth/google          # OAuth with Gmail scopes
├── POST   /auth/callback        # OAuth callback handler
├── GET    /auth/me              # Current user profile
└── POST   /auth/logout          # Session logout
Dashboard (UI Support)
├── GET    /dashboard/stats      # Aggregated stats (Action Items, Time Saved, etc.)
└── GET    /dashboard/activity   # Recent activity feed
Conversations
├── GET    /conversations            # List all conversations (w/ search & filters)
├── GET    /conversations/:id        # Get conversation detail
├── POST   /conversations/:id/snooze # Snooze conversation
├── POST   /conversations/:id/resolve # Mark as resolved
└── PATCH  /conversations/:id/tags   # Update tags
Nudges
├── GET    /nudges                   # List pending nudges
├── GET    /nudges/:id               # Get nudge detail
├── POST   /nudges/:id/approve       # Approve drafted nudge
├── PUT    /nudges/:id/edit          # Edit before approving
├── POST   /nudges/:id/cancel        # Cancel scheduled nudge
├── POST   /nudges/:id/send          # Send immediately
└── POST   /ai/regenerate            # On-demand draft regeneration (UI "Sparkle" button)
Contacts
├── GET    /contacts                 # List contacts
├── GET    /contacts/:id             # Get contact with history
└── PUT    /contacts/:id             # Update contact metadata
Digests
├── GET    /digests/today            # Today's digest summary
└── GET    /digests/:date            # Historical digest
Webhooks (Internal)
├── POST   /webhooks/gmail           # Gmail push notifications
└── POST   /webhooks/calendar        # Calendar event updates
1.3 Core Services Architecture
┌─────────────────────────────────────────────────────────────────┐
│                        API Gateway (FastAPI)                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Auth Service │  │ Conversation │  │   Nudge Scheduler    │  │
│  │              │  │   Service    │  │                      │  │
│  │ • OAuth 2.0  │  │              │  │ • Timezone calc      │  │
│  │ • Token mgmt │  │ • Thread sync│  │ • Queue management   │  │
│  │ • Session    │  │ • Contact    │  │ • Retry logic        │  │
│  └──────────────┘  │   matching   │  └──────────────────────┘  │
│                    └──────────────┘                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  AI Drafter  │  │  Delivery    │  │   Digest Generator   │  │
│  │              │  │   Engine     │  │                      │  │
│  │ • LLM calls  │  │              │  │ • Daily aggregation  │  │
│  │ • Tone adapt │  │ • Gmail API  │  │ • Slack delivery     │  │
│  │ • Context    │  │ • Slack API  │  │ • Email delivery     │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                     Supabase PostgreSQL                         │
│  • Row Level Security • Real-time Subscriptions • Edge Functions│
└─────────────────────────────────────────────────────────────────┘
1.4 MVP Features Checklist
 Google OAuth Integration

Gmail read/send scopes
Token refresh handling
Secure storage with pg_crypto
 Email Thread Sync

Gmail push notifications
Thread parsing and tagging
Contact extraction
 AI Draft Generation

GPT-4 integration for nudge drafts
Single "warm, concise" tone preset
Context-aware prompting (previous replies)
 Nudge Scheduling

Timezone-aware scheduling
32-hour default wait before nudging
Basic escalation (2 nudges max)
 Approval Workflow

Approve/Edit/Cancel nudges
Send immediately option
 Morning Digest

Email-based digest delivery
Summary of overnight activity
Phase 2: Multi-Channel & Smart Features
Goal: Add Slack, Calendar, and advanced AI capabilities.

Timeline: 4-6 weeks after MVP

2.1 Features
 Slack Integration

Slack OAuth (OIDC)
Send nudges via Slack DM
Morning digest in Slack channel
Slash commands for quick actions
 Calendar Integration

Google Calendar API
Auto-snooze when OOO detected
Schedule nudges around meetings
Calendar-based follow-up reminders
 Multiple Tone Presets

Custom tone presets per user
Contact-specific tone overrides
Company voice guidelines
 Smart Scheduling

Recipient timezone detection
Optimal send-time prediction
Behavior-based scheduling
 Escalation Rules

Custom escalation chains
Loop in team members
Manager notifications
2.2 New Database Tables
sql
CREATE TABLE escalation_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    conditions JSONB NOT NULL, -- {"after_nudges": 2, "days_silent": 5}
    actions JSONB NOT NULL, -- {"notify": ["manager@company.com"], "channel": "slack"}
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE team_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    member_email TEXT NOT NULL,
    role TEXT DEFAULT 'member', -- 'member', 'manager', 'admin'
    notification_preferences JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE calendar_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    event_id TEXT NOT NULL, -- Google Calendar event ID
    title TEXT,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    attendees JSONB DEFAULT '[]',
    is_ooo BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
2.3 New API Endpoints
Slack
├── POST   /auth/slack               # Slack OAuth
├── GET    /slack/channels           # List available channels
└── PUT    /preferences/slack        # Slack notification settings
Calendar
├── POST   /auth/calendar            # Calendar OAuth
├── GET    /calendar/events          # List upcoming events
└── GET    /calendar/ooo             # Get OOO periods
Tone Presets
├── GET    /tones                    # List tone presets
├── POST   /tones                    # Create custom tone
├── PUT    /tones/:id                # Update tone
└── DELETE /tones/:id                # Delete tone
Escalation
├── GET    /escalation-rules         # List rules
├── POST   /escalation-rules         # Create rule
├── PUT    /escalation-rules/:id     # Update rule
└── DELETE /escalation-rules/:id     # Delete rule
Team
├── GET    /team                     # List team members
├── POST   /team/invite              # Invite member
└── DELETE /team/:id                 # Remove member
Phase 3: CRM Integration & Analytics
Goal: Salesforce integration and actionable insights.

Timeline: 4-6 weeks after Phase 2

3.1 Features
 Salesforce Integration

Bi-directional sync
Contact enrichment
Opportunity linking
Activity logging
 Analytics Dashboard

Response time metrics
Nudge effectiveness
Conversion tracking
Team performance
 Notion Integration

Summaries piped to Notion
Deal board updates
Task creation
 Advanced Digest

Customizable digest time
Digest via Slack + Email
Next best actions
3.2 New Database Tables
sql
CREATE TABLE crm_syncs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL, -- 'salesforce', 'hubspot'
    last_sync_at TIMESTAMPTZ,
    sync_status TEXT DEFAULT 'idle',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE analytics_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL, -- 'nudge_sent', 'reply_received', 'escalation'
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES contacts(id),
    crm_opportunity_id TEXT,
    name TEXT,
    stage TEXT,
    value DECIMAL,
    close_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
3.3 New API Endpoints
CRM
├── POST   /auth/salesforce          # Salesforce OAuth
├── POST   /crm/sync                 # Trigger manual sync
├── GET    /crm/status               # Sync status
└── GET    /crm/opportunities        # List opportunities
Analytics
├── GET    /analytics/summary        # Overall metrics
├── GET    /analytics/nudges         # Nudge performance
├── GET    /analytics/response-times # Response time trends
└── GET    /analytics/team           # Team performance
Notion
├── POST   /auth/notion              # Notion OAuth
├── GET    /notion/databases         # List databases
└── PUT    /preferences/notion       # Configure mapping
Phase 4: Enterprise & Scale
Goal: Multi-tenant, SSO, and enterprise features.

Timeline: Ongoing

4.1 Features
 Microsoft 365 Integration

Outlook email
Microsoft Calendar
Microsoft Teams
 Enterprise SSO

SAML 2.0
SCIM provisioning
Custom domains
 Advanced Security

Audit logging
Data retention policies
GDPR compliance tools
 White-label

Custom branding
Custom domains
Embedded widgets
 API Access

Developer API
Webhooks for events
Rate limiting
Background Jobs & Scheduling
pg_cron Jobs (Supabase)
sql
-- Run every 5 minutes: Process pending nudges
SELECT cron.schedule('process-nudges', '*/5 * * * *', $$
    SELECT process_pending_nudges();
$$);
-- Run every morning at 6 AM user timezone (per-user)
SELECT cron.schedule('morning-digest', '0 * * * *', $$
    SELECT generate_morning_digests();
$$);
-- Run hourly: Sync Gmail threads
SELECT cron.schedule('gmail-sync', '0 * * * *', $$
    SELECT sync_gmail_threads();
$$);
-- Run daily: Token refresh
SELECT cron.schedule('refresh-tokens', '0 0 * * *', $$
    SELECT refresh_expiring_tokens();
$$);
Edge Functions
Function	Trigger	Purpose
send-nudge	HTTP/Queue	Send email/Slack nudge
draft-nudge	Database trigger	AI draft generation
gmail-webhook	HTTP POST	Process Gmail notifications
calendar-webhook	HTTP POST	Process Calendar updates
generate-digest	Scheduled	Create morning digest
Security Considerations
Authentication & Authorization
OAuth 2.1 with PKCE for all integrations
Row-Level Security (RLS) for all tables
Token encryption using pg_crypto
Refresh token rotation on each use
Data Protection
Encryption at rest (Supabase default)
TLS 1.3 for all connections
Minimal token scopes (least privilege)
Audit logging for sensitive operations
Example RLS Policies
sql
-- Users can only see their own data
ALTER TABLE nudges ENABLE ROW LEVEL SECURITY;
CREATE POLICY nudges_user_policy ON nudges
    FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());
-- Same for all other tables
Deployment Architecture
┌─────────────────────────────────────────────────────────────┐
│                     Load Balancer (Cloud Run)               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│   │  API Pod 1  │  │  API Pod 2  │  │  API Pod N  │        │
│   │  (FastAPI)  │  │  (FastAPI)  │  │  (FastAPI)  │        │
│   └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                    Supabase Platform                        │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐    │
│  │  PostgreSQL  │  │    Auth      │  │ Edge Functions │    │
│  │  + Realtime  │  │   + OAuth    │  │   + Workers    │    │
│  └──────────────┘  └──────────────┘  └────────────────┘    │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                  External Services                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────┐   │
│  │  Gmail  │  │  Slack  │  │Calendar │  │ Salesforce  │   │
│  │   API   │  │   API   │  │   API   │  │    API      │   │
│  └─────────┘  └─────────┘  └─────────┘  └─────────────┘   │
└─────────────────────────────────────────────────────────────┘
Success Metrics
Metric	Target (MVP)	Target (Phase 3)
Nudge delivery latency	< 5 seconds	< 2 seconds
API response time (p95)	< 500ms	< 200ms
Draft generation time	< 3 seconds	< 2 seconds
Gmail sync latency	< 1 minute	< 30 seconds
System uptime	99.5%	99.9%
Next Steps
Approve this plan to proceed with implementation
Set up Supabase project with schema migrations
Configure OAuth applications (Google, Slack)
Implement MVP core (Auth → Sync → Draft → Send)
Deploy to staging for testing
IMPORTANT

This plan focuses on backend implementation. The frontend (Next.js) is already in place and will need corresponding API integration once the backend is ready.