-- Migration 002: Add transaction_type to transactions
-- Run in Supabase SQL Editor after 001_invoice_extractor.sql
-- Safe to re-run (IF NOT EXISTS / DO $$ blocks throughout)

-- Add transaction_type column
ALTER TABLE transactions
  ADD COLUMN IF NOT EXISTS transaction_type TEXT
    DEFAULT 'sale'
    CHECK (transaction_type IN ('sale', 'payment_received', 'purchase', 'expense'));

-- Backfill existing rows
UPDATE transactions SET transaction_type = 'sale' WHERE transaction_type IS NULL;
