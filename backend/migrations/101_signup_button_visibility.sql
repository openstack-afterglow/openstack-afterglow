-- Apply before readers/writers requiring independent signup button visibility.
-- Preserve admission, quotas, revision and absent-policy source fallback.
ALTER TABLE enrollment_policy ADD COLUMN IF NOT EXISTS public_signup_button_visible BOOLEAN NOT NULL DEFAULT TRUE;
