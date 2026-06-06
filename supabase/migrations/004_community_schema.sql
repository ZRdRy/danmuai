-- DanmuAI community: profiles, posts, comments, likes (RLS + soft delete, no post/comment edit).
-- Scope: community-site + VITE_SUPABASE_* only. Not used by desktop config.db or main.py.

-- ---------------------------------------------------------------------------
-- Helpers (community_is_staff after tables — references community_profiles)
-- ---------------------------------------------------------------------------

create or replace function public.community_normalize_username(raw text)
returns text
language plpgsql
immutable
as $$
declare
  v text;
begin
  v := lower(trim(raw));
  if v is null or v = '' then
    raise exception 'username required';
  end if;
  if v !~ '^[a-z0-9_]{3,24}$' then
    raise exception 'username must be 3-24 chars: lowercase letters, digits, underscore';
  end if;
  return v;
end;
$$;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table public.community_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users (id) on delete cascade,
  username text not null unique,
  display_name text,
  avatar_key text not null default 'default',
  role text not null default 'user'
    check (role in ('user', 'moderator', 'admin')),
  status text not null default 'active'
    check (status in ('active', 'banned')),
  created_at timestamptz not null default now(),
  constraint community_profiles_username_format
    check (username ~ '^[a-z0-9_]{3,24}$')
);

create table public.community_posts (
  id uuid primary key default gen_random_uuid(),
  author_id uuid not null references auth.users (id) on delete cascade,
  title text not null
    check (char_length(title) between 2 and 80),
  content text not null
    check (char_length(content) between 10 and 5000),
  category text not null
    check (category in ('prompt', 'experience', 'help', 'config', 'showcase')),
  tags text[] not null default '{}'
    check (cardinality(tags) <= 5),
  like_count int not null default 0
    check (like_count >= 0),
  comment_count int not null default 0
    check (comment_count >= 0),
  is_featured boolean not null default false,
  is_deleted boolean not null default false,
  created_at timestamptz not null default now(),
  deleted_at timestamptz,
  constraint community_posts_no_markdown_images
    check (content !~* '\!\[.*\]\(.*\)'),
  constraint community_posts_no_image_urls
    check (content !~* 'https?://[^\s<>"'']+\.(png|jpe?g|gif|webp|bmp|svg)(\?[^\s]*)?')
);

create table public.community_comments (
  id uuid primary key default gen_random_uuid(),
  post_id uuid not null references public.community_posts (id) on delete cascade,
  author_id uuid not null references auth.users (id) on delete cascade,
  content text not null
    check (char_length(content) between 1 and 1000),
  is_deleted boolean not null default false,
  created_at timestamptz not null default now(),
  deleted_at timestamptz,
  constraint community_comments_no_markdown_images
    check (content !~* '\!\[.*\]\(.*\)'),
  constraint community_comments_no_image_urls
    check (content !~* 'https?://[^\s<>"'']+\.(png|jpe?g|gif|webp|bmp|svg)(\?[^\s]*)?')
);

create table public.community_post_likes (
  post_id uuid not null references public.community_posts (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (post_id, user_id)
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

create index community_posts_list_idx
  on public.community_posts (is_deleted, created_at desc);

create index community_posts_category_idx
  on public.community_posts (category)
  where is_deleted = false;

create index community_posts_featured_idx
  on public.community_posts (is_featured, created_at desc)
  where is_deleted = false and is_featured = true;

create index community_comments_post_idx
  on public.community_comments (post_id, created_at)
  where is_deleted = false;

create index community_post_likes_user_idx
  on public.community_post_likes (user_id);

-- ---------------------------------------------------------------------------
-- Count triggers (like_count / comment_count)
-- ---------------------------------------------------------------------------

create or replace function public.community_posts_like_count_sync()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if tg_op = 'INSERT' then
    update public.community_posts
    set like_count = like_count + 1
    where id = new.post_id;
    return new;
  elsif tg_op = 'DELETE' then
    update public.community_posts
    set like_count = greatest(0, like_count - 1)
    where id = old.post_id;
    return old;
  end if;
  return null;
end;
$$;

create trigger community_post_likes_count_trg
  after insert or delete on public.community_post_likes
  for each row execute function public.community_posts_like_count_sync();

create or replace function public.community_posts_comment_count_sync()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if tg_op = 'INSERT' then
    if not coalesce(new.is_deleted, false) then
      update public.community_posts
      set comment_count = comment_count + 1
      where id = new.post_id;
    end if;
    return new;
  elsif tg_op = 'UPDATE' then
    if old.is_deleted = false and new.is_deleted = true then
      update public.community_posts
      set comment_count = greatest(0, comment_count - 1)
      where id = new.post_id;
    elsif old.is_deleted = true and new.is_deleted = false then
      update public.community_posts
      set comment_count = comment_count + 1
      where id = new.post_id;
    end if;
    return new;
  elsif tg_op = 'DELETE' then
    if not coalesce(old.is_deleted, false) then
      update public.community_posts
      set comment_count = greatest(0, comment_count - 1)
      where id = old.post_id;
    end if;
    return old;
  end if;
  return null;
end;
$$;

create trigger community_comments_count_trg
  after insert or update of is_deleted or delete on public.community_comments
  for each row execute function public.community_posts_comment_count_sync();

-- ---------------------------------------------------------------------------
-- Staff helper (must run after community_profiles exists)
-- ---------------------------------------------------------------------------

create or replace function public.community_is_staff(p_user_id uuid default auth.uid())
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
      and p.role in ('admin', 'moderator')
      and p.status = 'active'
  );
$$;

-- ---------------------------------------------------------------------------
-- Guard triggers (no edit content / role escalation)
-- ---------------------------------------------------------------------------

create or replace function public.community_profiles_guard_update()
returns trigger
language plpgsql
as $$
begin
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

create trigger community_profiles_guard_update_trg
  before update on public.community_profiles
  for each row execute function public.community_profiles_guard_update();

create or replace function public.community_posts_guard_update()
returns trigger
language plpgsql
as $$
begin
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

create trigger community_posts_guard_update_trg
  before update on public.community_posts
  for each row execute function public.community_posts_guard_update();

create or replace function public.community_comments_guard_update()
returns trigger
language plpgsql
as $$
begin
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

create trigger community_comments_guard_update_trg
  before update on public.community_comments
  for each row execute function public.community_comments_guard_update();

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------

alter table public.community_profiles enable row level security;
alter table public.community_posts enable row level security;
alter table public.community_comments enable row level security;
alter table public.community_post_likes enable row level security;

-- profiles
create policy "community_profiles_select_active"
  on public.community_profiles
  for select
  to anon, authenticated
  using (status = 'active');

create policy "community_profiles_insert_own"
  on public.community_profiles
  for insert
  to authenticated
  with check (
    user_id = auth.uid()
    and role = 'user'
    and status = 'active'
  );

create policy "community_profiles_update_own"
  on public.community_profiles
  for update
  to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

-- posts
create policy "community_posts_select_visible"
  on public.community_posts
  for select
  to anon, authenticated
  using (is_deleted = false or author_id = auth.uid());

create policy "community_posts_insert_own"
  on public.community_posts
  for insert
  to authenticated
  with check (
    author_id = auth.uid()
    and is_deleted = false
    and is_featured = false
  );

create policy "community_posts_soft_delete_own"
  on public.community_posts
  for update
  to authenticated
  using (author_id = auth.uid() and is_deleted = false)
  with check (author_id = auth.uid() and is_deleted = true);

-- comments
create policy "community_comments_select_visible"
  on public.community_comments
  for select
  to anon, authenticated
  using (
    is_deleted = false
    or author_id = auth.uid()
    or exists (
      select 1
      from public.community_posts p
      where p.id = post_id
        and p.author_id = auth.uid()
    )
  );

create policy "community_comments_insert_own"
  on public.community_comments
  for insert
  to authenticated
  with check (
    author_id = auth.uid()
    and is_deleted = false
    and exists (
      select 1
      from public.community_posts p
      where p.id = post_id
        and p.is_deleted = false
    )
  );

create policy "community_comments_soft_delete_author"
  on public.community_comments
  for update
  to authenticated
  using (author_id = auth.uid() and is_deleted = false)
  with check (author_id = auth.uid() and is_deleted = true);

create policy "community_comments_soft_delete_post_owner"
  on public.community_comments
  for update
  to authenticated
  using (
    is_deleted = false
    and exists (
      select 1
      from public.community_posts p
      where p.id = post_id
        and p.author_id = auth.uid()
        and p.is_deleted = false
    )
  )
  with check (is_deleted = true);

-- likes
create policy "community_likes_select_all"
  on public.community_post_likes
  for select
  to anon, authenticated
  using (true);

create policy "community_likes_insert_own"
  on public.community_post_likes
  for insert
  to authenticated
  with check (
    user_id = auth.uid()
    and exists (
      select 1
      from public.community_posts p
      where p.id = post_id
        and p.is_deleted = false
    )
  );

create policy "community_likes_delete_own"
  on public.community_post_likes
  for delete
  to authenticated
  using (user_id = auth.uid());
