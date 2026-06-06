-- DanmuAI community: reports, staff moderation RLS, ban enforcement (006).
-- Scope: community-site + VITE_SUPABASE_* only. Not used by desktop config.db or main.py.

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------

create or replace function public.community_is_active(p_user_id uuid default auth.uid())
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.community_profiles p
    where p.user_id = p_user_id
      and p.status = 'active'
  );
$$;

create or replace function public.community_is_admin(p_user_id uuid default auth.uid())
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.community_profiles p
    where p.user_id = p_user_id
      and p.role = 'admin'
      and p.status = 'active'
  );
$$;

-- ---------------------------------------------------------------------------
-- Reports
-- ---------------------------------------------------------------------------

create table public.community_reports (
  id uuid primary key default gen_random_uuid(),
  reporter_id uuid not null references auth.users (id) on delete cascade,
  target_type text not null
    check (target_type in ('post', 'comment')),
  post_id uuid not null references public.community_posts (id) on delete cascade,
  comment_id uuid references public.community_comments (id) on delete cascade,
  reason text
    check (reason is null or char_length(trim(reason)) between 1 and 500),
  status text not null default 'pending'
    check (status in ('pending', 'resolved', 'dismissed')),
  resolved_at timestamptz,
  resolved_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  constraint community_reports_target_shape check (
    (target_type = 'post' and comment_id is null)
    or (target_type = 'comment' and comment_id is not null)
  )
);

create unique index community_reports_unique_post
  on public.community_reports (reporter_id, post_id)
  where target_type = 'post';

create unique index community_reports_unique_comment
  on public.community_reports (reporter_id, comment_id)
  where target_type = 'comment';

create index community_reports_pending_idx
  on public.community_reports (status, created_at desc)
  where status = 'pending';

create or replace function public.community_reports_rate_limit()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_count int;
begin
  select count(*)::int into v_count
  from public.community_reports r
  where r.reporter_id = new.reporter_id
    and r.created_at > now() - interval '24 hours';
  if v_count >= 20 then
    raise exception 'report rate limit exceeded';
  end if;
  return new;
end;
$$;

create trigger community_reports_rate_limit_trg
  before insert on public.community_reports
  for each row execute function public.community_reports_rate_limit();

-- ---------------------------------------------------------------------------
-- Guard triggers (staff moderation + admin ban)
-- ---------------------------------------------------------------------------

create or replace function public.community_profiles_guard_update()
returns trigger
language plpgsql
as $$
begin
  if public.community_is_admin() and old.user_id is distinct from auth.uid() then
    if new.user_id is distinct from old.user_id
       or new.username is distinct from old.username
       or new.role is distinct from old.role then
      raise exception 'admin may only change status';
    end if;
    if new.status is distinct from old.status then
      return new;
    end if;
    raise exception 'admin profile update not allowed';
  end if;

  if public.community_is_staff(old.user_id) then
    return new;
  end if;
  if new.username is distinct from old.username
     or new.role is distinct from old.role
     or new.status is distinct from old.status
     or new.user_id is distinct from old.user_id then
    raise exception 'profile field change not allowed';
  end if;
  return new;
end;
$$;

create or replace function public.community_posts_guard_update()
returns trigger
language plpgsql
as $$
begin
  if public.community_is_staff() and old.author_id is distinct from auth.uid() then
    if old.is_deleted = false and new.is_deleted = true then
      if new.title is distinct from old.title
         or new.content is distinct from old.content
         or new.category is distinct from old.category
         or new.tags is distinct from old.tags
         or new.author_id is distinct from old.author_id then
        raise exception 'staff soft-delete may not change content';
      end if;
      if new.deleted_at is null then
        new.deleted_at := now();
      end if;
      return new;
    end if;
    if old.is_deleted = false and new.is_deleted = false then
      if new.is_featured is distinct from old.is_featured
         and new.title is not distinct from old.title
         and new.content is not distinct from old.content
         and new.category is not distinct from old.category
         and new.tags is not distinct from old.tags
         and new.author_id is not distinct from old.author_id
         and new.is_deleted is not distinct from old.is_deleted
         and new.deleted_at is not distinct from old.deleted_at then
        return new;
      end if;
    end if;
    raise exception 'staff post update not allowed';
  end if;

  if public.community_is_staff(old.author_id) then
    return new;
  end if;

  if old.is_deleted = false and new.is_deleted = false then
    if new.title is distinct from old.title
       or new.content is distinct from old.content
       or new.category is distinct from old.category
       or new.tags is distinct from old.tags
       or new.author_id is distinct from old.author_id
       or new.is_featured is distinct from old.is_featured
       or new.is_deleted is distinct from old.is_deleted
       or new.deleted_at is distinct from old.deleted_at then
      raise exception 'post update not allowed';
    end if;
    if new.like_count is distinct from old.like_count
       or new.comment_count is distinct from old.comment_count then
      return new;
    end if;
  end if;

  if old.is_deleted = false and new.is_deleted = true then
    if new.title is distinct from old.title
       or new.content is distinct from old.content
       or new.category is distinct from old.category
       or new.tags is distinct from old.tags
       or new.author_id is distinct from old.author_id
       or new.is_featured is distinct from old.is_featured
       or new.like_count is distinct from old.like_count
       or new.comment_count is distinct from old.comment_count then
      raise exception 'only soft-delete fields may change';
    end if;
    if new.deleted_at is null then
      new.deleted_at := now();
    end if;
    return new;
  end if;

  raise exception 'post update not allowed';
end;
$$;

create or replace function public.community_comments_guard_update()
returns trigger
language plpgsql
as $$
begin
  if public.community_is_staff() and old.author_id is distinct from auth.uid() then
    if old.is_deleted = false and new.is_deleted = true then
      if new.content is distinct from old.content
         or new.post_id is distinct from old.post_id
         or new.author_id is distinct from old.author_id then
        raise exception 'staff soft-delete may not change content';
      end if;
      if new.deleted_at is null then
        new.deleted_at := now();
      end if;
      return new;
    end if;
    raise exception 'staff comment update not allowed';
  end if;

  if public.community_is_staff(old.author_id) then
    return new;
  end if;

  if old.is_deleted = false and new.is_deleted = true then
    if new.content is distinct from old.content
       or new.post_id is distinct from old.post_id
       or new.author_id is distinct from old.author_id then
      raise exception 'only soft-delete fields may change';
    end if;
    if new.deleted_at is null then
      new.deleted_at := now();
    end if;
    return new;
  end if;

  raise exception 'comment update not allowed';
end;
$$;

-- ---------------------------------------------------------------------------
-- RLS: tighten writes to active users; staff / admin policies
-- ---------------------------------------------------------------------------

alter table public.community_reports enable row level security;

-- profiles: own row readable when banned (for UI message)
create policy "community_profiles_select_own"
  on public.community_profiles
  for select
  to authenticated
  using (user_id = auth.uid());

create policy "community_profiles_select_staff"
  on public.community_profiles
  for select
  to authenticated
  using (public.community_is_staff());

create policy "community_profiles_admin_update_status"
  on public.community_profiles
  for update
  to authenticated
  using (public.community_is_admin())
  with check (public.community_is_admin());

-- posts: require active author on insert; staff moderate
drop policy if exists "community_posts_insert_own" on public.community_posts;
create policy "community_posts_insert_own"
  on public.community_posts
  for insert
  to authenticated
  with check (
    author_id = auth.uid()
    and public.community_is_active()
    and is_deleted = false
    and is_featured = false
  );

create policy "community_posts_staff_soft_delete"
  on public.community_posts
  for update
  to authenticated
  using (public.community_is_staff() and is_deleted = false)
  with check (public.community_is_staff());

create policy "community_posts_staff_featured"
  on public.community_posts
  for update
  to authenticated
  using (public.community_is_staff() and is_deleted = false)
  with check (public.community_is_staff());

-- comments
drop policy if exists "community_comments_insert_own" on public.community_comments;
create policy "community_comments_insert_own"
  on public.community_comments
  for insert
  to authenticated
  with check (
    author_id = auth.uid()
    and public.community_is_active()
    and is_deleted = false
    and exists (
      select 1
      from public.community_posts p
      where p.id = post_id
        and p.is_deleted = false
    )
  );

create policy "community_comments_staff_soft_delete"
  on public.community_comments
  for update
  to authenticated
  using (public.community_is_staff() and is_deleted = false)
  with check (public.community_is_staff());

-- likes
drop policy if exists "community_likes_insert_own" on public.community_post_likes;
create policy "community_likes_insert_own"
  on public.community_post_likes
  for insert
  to authenticated
  with check (
    user_id = auth.uid()
    and public.community_is_active()
    and exists (
      select 1
      from public.community_posts p
      where p.id = post_id
        and p.is_deleted = false
    )
  );

-- reports
create policy "community_reports_insert_active"
  on public.community_reports
  for insert
  to authenticated
  with check (
    reporter_id = auth.uid()
    and public.community_is_active()
    and (
      (
        target_type = 'post'
        and exists (
          select 1
          from public.community_posts p
          where p.id = post_id
            and p.is_deleted = false
        )
      )
      or (
        target_type = 'comment'
        and exists (
          select 1
          from public.community_comments c
          join public.community_posts p on p.id = c.post_id
          where c.id = comment_id
            and c.post_id = post_id
            and c.is_deleted = false
            and p.is_deleted = false
        )
      )
    )
  );

create policy "community_reports_select_staff"
  on public.community_reports
  for select
  to authenticated
  using (public.community_is_staff());

create policy "community_reports_update_staff"
  on public.community_reports
  for update
  to authenticated
  using (public.community_is_staff())
  with check (public.community_is_staff());
