-- Extends proj_tenders (006_tenders.sql) with the fields the admin tender
-- builder needs to capture at creation: department/organization, issue
-- date, and tender category. Additive only -- existing rows and the old
-- five-field shape stay valid, all three new columns are nullable so a
-- tender created before this migration reads back as honest NULLs, not a
-- guessed value.

ALTER TABLE proj_tenders ADD COLUMN IF NOT EXISTS department  text;
ALTER TABLE proj_tenders ADD COLUMN IF NOT EXISTS issue_date  date;
ALTER TABLE proj_tenders ADD COLUMN IF NOT EXISTS category    text;
