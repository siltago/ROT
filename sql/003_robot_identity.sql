-- Run this once in the Supabase project's SQL Editor before the robot
-- brain uses SUPABASE_URL/SUPABASE_KEY. Holds the robot's persisted
-- self-identity (who he is, his day-to-day focus areas, and accumulated
-- self-notes) as a single row, same shape as 001_learned_skills.sql and
-- 002_robot_needs.sql.
create table if not exists robot_identity (
    id text primary key,
    data jsonb not null,
    updated_at timestamptz not null default now()
);
