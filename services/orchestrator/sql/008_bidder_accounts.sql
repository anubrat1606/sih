-- Round 6: a bidder is a real user of this system now, not a second auth
-- system -- same `users` table, same login, one new nullable column
-- linking an account to the bidder record it acts as (NULL for every
-- role except BIDDER). The role CHECK constraint has to be dropped and
-- recreated to admit the new value; Postgres has no "add a value to a
-- CHECK" statement. Additive and idempotent either way: existing rows
-- and their NULL bidder_id stay exactly as they were.

ALTER TABLE users ADD COLUMN IF NOT EXISTS bidder_id text;

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('BIDDER','OFFICER','SENIOR_OFFICER','ADMIN'));
