-- Migration: Add internal_domains column to users table
-- This allows users to specify their company email domains to filter out internal attendees

ALTER TABLE users ADD COLUMN IF NOT EXISTS internal_domains TEXT;
