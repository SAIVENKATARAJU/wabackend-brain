-- Migration: Add message delivery status tracking columns
-- These columns track the full lifecycle of each message through Meta's webhook callbacks

-- Add delivery timestamp columns
ALTER TABLE messages ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS read_at TIMESTAMPTZ;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS failed_at TIMESTAMPTZ;

-- Add error tracking for failed messages
ALTER TABLE messages ADD COLUMN IF NOT EXISTS error_code TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS error_message TEXT;

-- Add retry tracking
ALTER TABLE messages ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS max_retries INTEGER DEFAULT 3;

-- Add index on whatsapp_message_id for fast webhook status lookups
CREATE INDEX IF NOT EXISTS idx_messages_whatsapp_message_id 
    ON messages (whatsapp_message_id) 
    WHERE whatsapp_message_id IS NOT NULL;

-- Add index on status for filtering
CREATE INDEX IF NOT EXISTS idx_messages_status ON messages (status);

-- Add index for conversation + direction (for displaying thread history)
CREATE INDEX IF NOT EXISTS idx_messages_conversation_direction 
    ON messages (conversation_id, direction, created_at);
