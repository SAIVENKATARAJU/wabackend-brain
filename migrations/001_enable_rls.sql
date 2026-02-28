-- ============================================================================
-- Row Level Security (RLS) Migration for Akasavani
-- ============================================================================
-- This migration enables Row Level Security on all user data tables
-- to provide database-level protection against unauthorized access.
--
-- Run this script in your Supabase SQL Editor or via migration tool.
-- ============================================================================

-- ============================================================================
-- STEP 1: Enable RLS on all tables
-- ============================================================================

-- Users table (if exists)
ALTER TABLE IF EXISTS users ENABLE ROW LEVEL SECURITY;

-- Core data tables
ALTER TABLE IF EXISTS contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS nudges ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS tone_presets ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS digests ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- STEP 2: Create RLS Policies for each table
-- ============================================================================

-- ----------------------------------------------------------------------------
-- USERS TABLE
-- Users can only see and modify their own profile
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS users_select_own ON users;
CREATE POLICY users_select_own ON users
    FOR SELECT
    USING (id = auth.uid());

DROP POLICY IF EXISTS users_update_own ON users;
CREATE POLICY users_update_own ON users
    FOR UPDATE
    USING (id = auth.uid())
    WITH CHECK (id = auth.uid());

-- ----------------------------------------------------------------------------
-- CONTACTS TABLE
-- Users can only access their own contacts
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS contacts_user_policy ON contacts;
CREATE POLICY contacts_user_policy ON contacts
    FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- ----------------------------------------------------------------------------
-- CONVERSATIONS TABLE
-- Users can only access their own conversations
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS conversations_user_policy ON conversations;
CREATE POLICY conversations_user_policy ON conversations
    FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- ----------------------------------------------------------------------------
-- NUDGES TABLE
-- Users can only access their own nudges
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS nudges_user_policy ON nudges;
CREATE POLICY nudges_user_policy ON nudges
    FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- ----------------------------------------------------------------------------
-- MESSAGES TABLE
-- Users can only access their own messages
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS messages_user_policy ON messages;
CREATE POLICY messages_user_policy ON messages
    FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- ----------------------------------------------------------------------------
-- INTEGRATIONS TABLE
-- Users can only access their own integrations
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS integrations_user_policy ON integrations;
CREATE POLICY integrations_user_policy ON integrations
    FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- ----------------------------------------------------------------------------
-- USER_PREFERENCES TABLE
-- Users can only access their own preferences
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS user_preferences_user_policy ON user_preferences;
CREATE POLICY user_preferences_user_policy ON user_preferences
    FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- ----------------------------------------------------------------------------
-- TONE_PRESETS TABLE
-- Users can only access their own tone presets
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS tone_presets_user_policy ON tone_presets;
CREATE POLICY tone_presets_user_policy ON tone_presets
    FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- ----------------------------------------------------------------------------
-- DIGESTS TABLE
-- Users can only access their own digests
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS digests_user_policy ON digests;
CREATE POLICY digests_user_policy ON digests
    FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- ============================================================================
-- STEP 3: Service Role Bypass (for backend operations)
-- ============================================================================
-- Note: The Supabase service_role key bypasses RLS by default.
-- This is needed for backend operations like webhooks and cron jobs.
-- 
-- Your backend uses SUPABASE_SERVICE_KEY which has full access.
-- For user-facing operations, consider using the user's JWT token instead.

-- ============================================================================
-- STEP 4: Verify RLS is enabled
-- ============================================================================
-- Run this query to verify RLS is enabled on all tables:
--
-- SELECT schemaname, tablename, rowsecurity 
-- FROM pg_tables 
-- WHERE schemaname = 'public' 
-- AND tablename IN ('users', 'contacts', 'conversations', 'nudges', 
--                   'messages', 'integrations', 'user_preferences', 
--                   'tone_presets', 'digests');
--
-- Expected: rowsecurity = true for all tables

-- ============================================================================
-- STEP 5: Test RLS Policies
-- ============================================================================
-- To test, you can use the Supabase SQL Editor with a specific user context:
--
-- SET LOCAL ROLE authenticated;
-- SET LOCAL request.jwt.claims = '{"sub": "user-uuid-here"}';
-- SELECT * FROM contacts; -- Should only return contacts for that user
--
-- Or test via API with different user tokens.

-- ============================================================================
-- ROLLBACK (if needed)
-- ============================================================================
-- To disable RLS (NOT RECOMMENDED for production):
--
-- ALTER TABLE contacts DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE conversations DISABLE ROW LEVEL SECURITY;
-- -- ... etc for other tables

COMMENT ON POLICY contacts_user_policy ON contacts IS 'Users can only access their own contacts';
COMMENT ON POLICY conversations_user_policy ON conversations IS 'Users can only access their own conversations';
COMMENT ON POLICY nudges_user_policy ON nudges IS 'Users can only access their own nudges';
COMMENT ON POLICY messages_user_policy ON messages IS 'Users can only access their own messages';
COMMENT ON POLICY integrations_user_policy ON integrations IS 'Users can only access their own integrations';