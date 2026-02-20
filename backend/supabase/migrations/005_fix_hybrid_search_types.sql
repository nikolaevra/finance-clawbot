-- ============================================================
-- Fix: cast RRF score computation to double precision
--
-- The original hybrid_memory_search returned numeric from the
-- 1.0 / (k + rank) expression, but the function signature
-- declares score as double precision → Postgres error 42804.
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
