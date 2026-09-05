-- Teal's Daily Fact Challenge v2.19.9
-- Perfect Score Club for the AWTRIX classroom ticker.
-- Run this ONCE in Supabase SQL Editor after deploying the v2.19.9 GitHub files.
--
-- This replaces only the private payload helper used by the existing AWTRIX
-- Top 10 RPCs. It does not change tables, RLS, clock tokens, or the Berry script.
-- The existing Top 10 remains accuracy-first with time as the private tiebreaker.
-- After the Top 10 text, the ticker appends alphabetized 10/10 nicknames that
-- are not already in the Top 10. Test students and inactive students remain excluded.

create or replace function public.awtrix_top10_payload_for_block(p_block integer)
returns jsonb
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
    v_class_id uuid;
    v_class_name text;
    v_challenge_id uuid;
    v_count integer := 0;
    v_names text;
    v_perfect_count integer := 0;
    v_perfect_names text;
    v_text text;
begin
    if p_block not between 1 and 3 then
        return jsonb_build_object('ok', false, 'error', 'invalid_block');
    end if;

    select case p_block
        when 1 then block1_class_id
        when 2 then block2_class_id
        when 3 then block3_class_id
    end
    into v_class_id
    from public.awtrix_clock_config
    where config_id = 1;

    if v_class_id is null then
        return jsonb_build_object('ok', false, 'error', 'block_not_mapped', 'block', p_block);
    end if;

    select class_name
    into v_class_name
    from public.classes
    where class_id = v_class_id;

    select challenge_id
    into v_challenge_id
    from public.daily_challenges
    where challenge_date = (now() at time zone 'America/Indiana/Indianapolis')::date
    limit 1;

    if v_challenge_id is not null then
        with ranked as (
            select
                row_number() over (
                    order by da.correct_count desc, da.timed_seconds asc, da.completed_at asc
                ) as rank,
                s.nickname,
                da.correct_count
            from public.daily_attempts da
            join public.students s on s.student_id = da.student_id
            where da.challenge_id = v_challenge_id
              and da.completed_at is not null
              and s.class_id = v_class_id
              and s.active = true
              and coalesce(s.is_test, false) = false
        )
        select
            (select count(*)::integer from ranked where rank <= 10),
            (select string_agg('#' || rank::text || ' ' || nickname, '   ' order by rank)
               from ranked where rank <= 10),
            (select count(*)::integer from ranked where correct_count = 10 and rank > 10),
            (select string_agg(nickname, '   ' order by lower(nickname), nickname)
               from ranked where correct_count = 10 and rank > 10)
        into v_count, v_names, v_perfect_count, v_perfect_names;
    end if;

    if v_count > 0 then
        v_text := 'BLOCK ' || p_block::text || ' TOP 10!   ' || v_names;
    else
        v_text := 'BLOCK ' || p_block::text || ' TOP 10!   NO FINISHERS YET';
    end if;

    if v_perfect_count > 0 then
        v_text := v_text || '   PERFECT SCORE CLUB!   ' || v_perfect_names;
    end if;

    return jsonb_build_object(
        'ok', true,
        'block', p_block,
        'class_name', coalesce(v_class_name, 'Class'),
        'count', v_count,
        'perfect_count', v_perfect_count,
        'text', v_text
    );
end;
$$;

revoke all on function public.awtrix_top10_payload_for_block(integer) from public;
revoke all on function public.awtrix_top10_payload_for_block(integer) from anon;
revoke all on function public.awtrix_top10_payload_for_block(integer) from authenticated;
