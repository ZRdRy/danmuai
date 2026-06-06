-- scope: community-site (Vercel SPA) — public read-only maintenance flag
-- DanmuAI desktop / 001–003 tables are unrelated.

CREATE TABLE IF NOT EXISTS public.community_site_status (
  id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  maintenance_enabled boolean NOT NULL DEFAULT true,
  message text NOT NULL DEFAULT '社区正在进化中，非常抱歉',
  updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.community_site_status (id, maintenance_enabled, message)
VALUES (1, true, '社区正在进化中，非常抱歉')
ON CONFLICT (id) DO UPDATE
SET
  maintenance_enabled = EXCLUDED.maintenance_enabled,
  message = EXCLUDED.message,
  updated_at = now();

ALTER TABLE public.community_site_status ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS community_site_status_anon_select ON public.community_site_status;
CREATE POLICY community_site_status_anon_select
  ON public.community_site_status
  FOR SELECT
  TO anon, authenticated
  USING (true);
