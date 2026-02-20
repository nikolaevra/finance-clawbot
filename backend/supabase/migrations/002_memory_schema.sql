-- ============================================================
-- Memory System: Chunks table with hybrid search (pgvector + tsvector)
-- ============================================================

-- Enable pgvector extension for semantic search
create extension if not exists vector;

-- Memory chunks: derived index over memory files in Supabase Storage.
-- Source of truth is Storage; this table is rebuildable from those files.
create table if not exists memory_chunks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade not null,
  source_file text not null,       -- e.g. 'daily/2025-02-08.md' or 'MEMORY.md'
  chunk_text text not null,
  chunk_index int not null default 0,
  embedding vector(1536),          -- text-embedding-3-small output dimension
  tsv tsvector generated always as (to_tsvector('english', chunk_text)) stored,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Indexes
create index idx_memory_chunks_user_id on memory_chunks(user_id);
create index idx_memory_chunks_source on memory_chunks(user_id, source_file);
create index idx_memory_chunks_tsv on memory_chunks using gin(tsv);
create index idx_memory_chunks_embedding on memory_chunks
  using hnsw (embedding vector_cosine_ops);

-- Row Level Security
alter table memory_chunks enable row level security;

create policy "Users can manage own memory chunks"
  on memory_chunks for all using (auth.uid() = user_id);

-- Auto-update updated_at
create trigger memory_chunks_updated_at
  before update on memory_chunks
  for each row execute function update_updated_at_column();

-- ============================================================
-- Hybrid search function: keyword (tsvector) + semantic (pgvector)
-- merged via Reciprocal Rank Fusion (RRF)
-- ============================================================
create or replace function hybrid_memory_search(
  p_user_id uuid,
  p_query_text text,
  p_query_embedding vector(1536),
  p_limit int default 10
)
returns table (
  source_file text,
  chunk_text text,
  score double precision
)
language plpgsql
as $$
declare
  k constant int := 60;  -- RRF smoothing constant
begin
  return query
  with keyword_results as (
    select
      mc.source_file,
      mc.chunk_text,
      row_number() over (
        order by ts_rank(mc.tsv, plainto_tsquery('english', p_query_text)) desc
      ) as rank_kw
    from memory_chunks mc
    where mc.user_id = p_user_id
      and mc.tsv @@ plainto_tsquery('english', p_query_text)
    order by rank_kw
    limit p_limit * 3
  ),
  semantic_results as (
    select
      mc.source_file,
      mc.chunk_text,
      row_number() over (
        order by mc.embedding <=> p_query_embedding
      ) as rank_sem
    from memory_chunks mc
    where mc.user_id = p_user_id
      and mc.embedding is not null
    order by rank_sem
    limit p_limit * 3
  ),
  fused as (
    select
      coalesce(kw.source_file, sem.source_file) as source_file,
      coalesce(kw.chunk_text, sem.chunk_text) as chunk_text,
      coalesce(1.0::double precision / (k + kw.rank_kw), 0::double precision) +
      coalesce(1.0::double precision / (k + sem.rank_sem), 0::double precision) as rrf_score
    from keyword_results kw
    full outer join semantic_results sem
      on kw.source_file = sem.source_file
      and kw.chunk_text = sem.chunk_text
  )
  select
    f.source_file,
    f.chunk_text,
    f.rrf_score as score
  from fused f
  order by f.rrf_score desc
  limit p_limit;
end;
$$;
