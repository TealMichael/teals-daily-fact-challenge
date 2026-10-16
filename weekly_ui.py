from __future__ import annotations

import html
import importlib
import random
import time
from datetime import datetime, timezone

import streamlit as st

import weekly as _weekly

if getattr(_weekly, "WEEKLY_LOGIC_SCHEMA_VERSION", 0) < 3:
    _weekly = importlib.reload(_weekly)

from config import APP_VERSION
from player_season_stats import attach_snapshot, load_or_prepare_snapshot, stats_line
from pulse_ui import render_pregame_pulse
from automation_recovery import maybe_recover_critical_automation
from gate4_ui import (
    maybe_render_final_celebration,
    render_gate4_demo,
    render_history,
    render_leaderboards,
    render_live_sunday,
    render_nav,
    render_profile,
)
from weekly import (
    POSITIONS,
    et_label,
    first_incomplete_position,
    lineup_readiness,
    lineup_progress,
    next_position,
    parse_timestamp,
    picks_by_position,
    pool_is_ready,
    position_pool,
    previous_position,
    required_backup_positions,
    schedule_ineligible_starter_positions,
    selected_pool_ids_missing_from_visible_pool,
    seconds_until,
    unavailable_starter_positions,
    safe_status,
    week_phase,
)

UTC = timezone.utc
WEEKLY_UI_SCHEMA_VERSION = 14
# Previous release: WEEKLY_UI_SCHEMA_VERSION = 13
# Previous cumulative marker: WEEKLY_UI_SCHEMA_VERSION = 12
# Prior cumulative UI marker: WEEKLY_UI_SCHEMA_VERSION = 11
# Prior cumulative UI marker: WEEKLY_UI_SCHEMA_VERSION = 10
# Legacy regression marker only: WEEKLY_UI_SCHEMA_VERSION = 9


def _compact_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "less than a minute"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if hours < 24:
        return f"{hours} hr" + (f" {remaining_minutes} min" if remaining_minutes else "")
    days = hours // 24
    remaining_hours = hours % 24
    return f"{days} day{'s' if days != 1 else ''}" + (f" {remaining_hours} hr" if remaining_hours else "")


def _refresh_age_label(value: str | datetime | None) -> tuple[str, int | None]:
    stamp = parse_timestamp(value)
    if not stamp:
        return "refresh pending", None
    age_seconds = max(0, int((datetime.now(UTC) - stamp).total_seconds()))
    if age_seconds < 60:
        return "just now", age_seconds
    if age_seconds < 3600:
        minutes = age_seconds // 60
        return f"{minutes} min ago", age_seconds
    if age_seconds < 86400:
        hours = age_seconds // 3600
        return f"{hours} hr ago", age_seconds
    days = age_seconds // 86400
    return f"{days} day{'s' if days != 1 else ''} ago", age_seconds


def _render_sunday_status_card(week: dict, picks: list[dict], pool_by_id: dict[str, dict]) -> None:
    """One-glance pre-lock confidence card for the real weekly game."""
    status = lineup_readiness(picks, pool_by_id)
    chosen = int(status["chosen"])
    total = int(status["total"])
    unavailable = list(status["unavailable"])
    needs_backup = list(status["needs_backup"])
    questionable = list(status["questionable"])
    schedule_unavailable = schedule_ineligible_starter_positions(picks, pool_by_id)

    # Keep an injury warning visible even when an OUT starter is safely covered
    # by an emergency backup. "Ready" should mean the lineup is protected, not
    # that the starter's injury disappeared from the Sunday Status card.
    out_starters: list[str] = []
    for pos, pick in picks_by_position(picks).items():
        starter = pool_by_id.get(str(pick.get("pool_player_id")))
        if starter and safe_status(starter.get("availability_status")) == "OUT":
            out_starters.append(pos)
    covered_out = [pos for pos in out_starters if pos not in unavailable]

    if unavailable:
        tone = "danger"
        icon = "🚫"
        title = "Lineup needs a replacement"
        subtitle = f"{chosen} of {total} picks saved"
    elif chosen < total:
        tone = "warn"
        icon = "🧩"
        title = "Finish your five"
        subtitle = f"{chosen} of {total} picks complete"
    elif needs_backup:
        tone = "warn"
        icon = "⚠️"
        title = "Lineup needs attention"
        subtitle = "All five picks are saved"
    elif covered_out:
        tone = "warn"
        icon = "⚠️"
        title = "Lineup ready — backup set"
        subtitle = "All five picks are set"
    else:
        tone = "ok"
        icon = "✅"
        title = "Lineup ready"
        subtitle = "All five picks are set"

    injury_parts: list[str] = []
    out_unavailable = [pos for pos in unavailable if pos not in schedule_unavailable]
    if schedule_unavailable:
        injury_parts.append(
            f"🚫 {len(schedule_unavailable)} starter{'s' if len(schedule_unavailable) != 1 else ''} moved outside the eligible Sunday slate • replacement needed"
        )
    if out_unavailable:
        injury_parts.append(f"🚫 {len(out_unavailable)} starter{'s' if len(out_unavailable) != 1 else ''} OUT • backup needed")
    if covered_out:
        injury_parts.append(f"⚠️ {len(covered_out)} starter{'s' if len(covered_out) != 1 else ''} OUT • emergency backup{'s' if len(covered_out) != 1 else ''} ready")
    if questionable:
        if needs_backup:
            injury_parts.append(f"⚠️ {len(questionable)} Questionable • {len(needs_backup)} backup{'s' if len(needs_backup) != 1 else ''} needed")
        else:
            injury_parts.append(f"⚠️ {len(questionable)} Questionable • emergency backup{'s' if len(questionable) != 1 else ''} ready")
    if not injury_parts:
        injury_parts.append("✅ No starter injury flags")
    injury_text = " • ".join(injury_parts)

    lock_seconds = seconds_until(week.get("locks_at"))
    lock_text = f"Locks in {_compact_duration(lock_seconds)}" if lock_seconds > 0 else "Picks are locked"
    refresh_label, refresh_age = _refresh_age_label(week.get("last_data_refresh_at"))
    near_lock = 0 < lock_seconds <= 2 * 3600
    stale_near_lock = near_lock and (refresh_age is None or refresh_age > 30 * 60)
    refresh_icon = "⚠️" if stale_near_lock else "🏈"
    refresh_text = f"NFL data updated {refresh_label}" if refresh_age is not None else "NFL data refresh pending"

    st.markdown(
        f'''<div class="sunday-status sunday-status-{tone}">
  <div class="sunday-status-head"><span class="sunday-status-icon">{icon}</span><div><div class="eyebrow">Sunday status</div><div class="sunday-status-title">{html.escape(title)}</div></div></div>
  <div class="sunday-status-sub">{html.escape(subtitle)}</div>
  <div class="sunday-status-lines"><div>{html.escape(injury_text)}</div><div>🕐 {html.escape(lock_text)}</div><div>{refresh_icon} {html.escape(refresh_text)}</div></div>
</div>''',
        unsafe_allow_html=True,
    )
    if stale_near_lock:
        st.caption("NFL status data is older than expected this close to lock. Your saved lineup is safe; check again after the next refresh.")


@st.fragment(run_every="60s")
def _render_live_prelock_status(store, week: dict, player: dict) -> None:
    """Keep the Sunday confidence card fresh while a phone sits open.

    This fragment never edits a lineup. It rereads the current week/pool/lineup
    and can invoke the already-leased automation fallback if the final injury
    refresh is late. A lock transition gets a full app rerun so the builder
    cannot remain visually open after 1 PM ET.
    """
    fresh_week = store.get_week(str(week["id"])) or week
    fresh_week, _recovery = maybe_recover_critical_automation(store, fresh_week)
    if week_phase(fresh_week) == "locked":
        st.rerun()
    fresh_pool = store.get_week_pool(str(fresh_week["id"]), visible_only=True)
    _lineup, picks, resolved_pool, pool_by_id = _load_lineup(
        store,
        fresh_week,
        player,
        fresh_pool,
        snapshot_ttl_seconds=0,
    )
    _render_sunday_status_card(fresh_week, picks, pool_by_id)


@st.fragment(run_every="15s")
def _lock_transition_guard(locks_at: str | datetime | None) -> None:
    """Move an idle pre-lock builder/review screen to live mode promptly."""
    if seconds_until(locks_at) <= 0:
        st.rerun()


def _countdown(target_iso: str, label: str) -> None:
    safe_target = html.escape(str(target_iso), quote=True)
    safe_label = html.escape(label)
    st.components.v1.html(
        f"""
<div class="tsp-countdown-card">
  <div class="tsp-countdown-label">{safe_label}</div>
  <div class="tsp-countdown-grid" aria-label="Countdown">
    <div class="tsp-countdown-unit"><div id="tsp-days" class="tsp-countdown-value">--</div><div class="tsp-countdown-unit-label">DAYS</div></div>
    <div class="tsp-countdown-unit"><div id="tsp-hours" class="tsp-countdown-value">--</div><div class="tsp-countdown-unit-label">HRS</div></div>
    <div class="tsp-countdown-unit"><div id="tsp-minutes" class="tsp-countdown-value">--</div><div class="tsp-countdown-unit-label">MIN</div></div>
    <div class="tsp-countdown-unit"><div id="tsp-seconds" class="tsp-countdown-value">--</div><div class="tsp-countdown-unit-label">SEC</div></div>
  </div>
</div>
<style>
  :root {{ color-scheme: light; }}
  html, body {{ margin:0; padding:0; background:transparent; }}
  .tsp-countdown-card {{
    box-sizing:border-box;
    width:100%;
    font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    background:#fff;
    border:1px solid #E5EAED;
    border-radius:18px;
    padding:13px 14px 14px;
    color:#172027;
  }}
  .tsp-countdown-label {{
    font-size:12px;
    line-height:1.25;
    font-weight:850;
    text-transform:uppercase;
    letter-spacing:.09em;
    color:#0F766E;
    margin-bottom:9px;
  }}
  .tsp-countdown-grid {{
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:8px;
  }}
  .tsp-countdown-unit {{
    min-width:0;
    text-align:center;
    background:#F7F9FA;
    border:1px solid #EDF1F3;
    border-radius:12px;
    padding:8px 3px 7px;
  }}
  .tsp-countdown-value {{
    font-size:26px;
    line-height:1;
    font-weight:900;
    letter-spacing:-.04em;
    font-variant-numeric:tabular-nums;
  }}
  .tsp-countdown-unit-label {{
    margin-top:5px;
    font-size:9px;
    line-height:1;
    font-weight:850;
    letter-spacing:.09em;
    color:#677680;
  }}
  @media (max-width:420px) {{
    .tsp-countdown-card {{ padding:12px 10px 13px; }}
    .tsp-countdown-grid {{ gap:6px; }}
    .tsp-countdown-value {{ font-size:23px; }}
    .tsp-countdown-unit-label {{ font-size:8px; }}
  }}
</style>
<script>
const target = new Date("{safe_target}").getTime();
const dayEl = document.getElementById("tsp-days");
const hourEl = document.getElementById("tsp-hours");
const minuteEl = document.getElementById("tsp-minutes");
const secondEl = document.getElementById("tsp-seconds");
function pad(value) {{ return String(value).padStart(2, "0"); }}
function tick() {{
  const diff = Math.max(0, target - Date.now());
  const total = Math.floor(diff / 1000);
  const d = Math.floor(total / 86400);
  const h = Math.floor((total % 86400) / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  dayEl.textContent = pad(d);
  hourEl.textContent = pad(h);
  minuteEl.textContent = pad(m);
  secondEl.textContent = pad(s);
}}
tick(); setInterval(tick, 1000);
</script>
        """,
        height=116,
    )


def _player_lookup(pool: list[dict]) -> dict[str, dict]:
    return {str(row["id"]): row for row in pool}


def _display_name(row: dict | None) -> str:
    return str((row or {}).get("player_name") or "—")


def _player_meta(row: dict) -> str:
    team = str(row.get("team_abbr") or "—")
    opp = str(row.get("opponent_abbr") or "—")
    kickoff = et_label(row.get("kickoff_at"), include_date=False)
    return f"{team} vs {opp} • {kickoff}" if kickoff else f"{team} vs {opp}"


def _status_badge(row: dict) -> str:
    status = safe_status(row.get("availability_status"))
    if status == "QUESTIONABLE":
        return '<span class="badge-q">⚠ QUESTIONABLE</span>'
    if status == "OUT":
        return '<span class="badge-out">OUT</span>'
    return ""


def _stable_order(player_id: str, week_id: str, position: str, rows: list[dict]) -> list[dict]:
    key = f"pool_order::{player_id}::{week_id}::{position}"
    ids = [str(r["id"]) for r in rows]
    existing = list(st.session_state.get(key) or [])
    if set(existing) != set(ids) or len(existing) != len(ids):
        existing = ids[:]
        random.SystemRandom().shuffle(existing)
        st.session_state[key] = existing
    by_id = {str(r["id"]): r for r in rows}
    return [by_id[i] for i in existing if i in by_id]


LINEUP_SNAPSHOT_TTL_SECONDS = 12.0


def _lineup_snapshot_key(week: dict, player: dict) -> str:
    return f"lineup_snapshot::{week['id']}::{player['id']}"


def _stash_lineup_snapshot(week: dict, player: dict, lineup: dict | None, picks: list[dict]) -> None:
    st.session_state[_lineup_snapshot_key(week, player)] = {
        "at": time.monotonic(),
        "lineup": dict(lineup) if lineup else None,
        "picks": [dict(p) for p in picks],
    }


def _merge_saved_pick(picks: list[dict], saved_pick: dict) -> list[dict]:
    position = str(saved_pick.get("position") or "")
    merged = [dict(p) for p in picks if str(p.get("position") or "") != position]
    merged.append(dict(saved_pick))
    return merged


def _include_preserved_selected_rows(store, week: dict, pool: list[dict], picks: list[dict]) -> list[dict]:
    """Add hidden rows referenced by saved picks for display only.

    ``position_pool(..., visible_only=True)`` still excludes these rows from
    the five choices shown to users. They are appended only so an already-saved
    starter/backup remains renderable after an OUT/schedule/Commissioner
    replacement hides it from future selection.
    """
    known = {str(row.get("id")) for row in pool if row.get("id")}
    missing = selected_pool_ids_missing_from_visible_pool(pool, picks)
    if not missing:
        return pool
    extras = store.get_pool_rows_by_ids(str(week["id"]), missing)
    return [*pool, *[row for row in extras if str(row.get("id")) not in known]]


def _load_lineup(
    store,
    week: dict,
    player: dict,
    pool: list[dict],
    *,
    snapshot_ttl_seconds: float = LINEUP_SNAPSHOT_TTL_SECONDS,
) -> tuple[dict | None, list[dict], list[dict], dict[str, dict]]:
    key = _lineup_snapshot_key(week, player)
    snapshot = st.session_state.get(key) or {}
    age = time.monotonic() - float(snapshot.get("at") or 0.0)
    if snapshot and age <= float(snapshot_ttl_seconds):
        lineup = snapshot.get("lineup")
        picks = list(snapshot.get("picks") or [])
        resolved_pool = _include_preserved_selected_rows(store, week, pool, picks)
        return lineup, picks, resolved_pool, _player_lookup(resolved_pool)

    lineup, picks = store.get_lineup_state(str(week["id"]), str(player["id"]))
    _stash_lineup_snapshot(week, player, lineup, picks)
    resolved_pool = _include_preserved_selected_rows(store, week, pool, picks)
    return lineup, picks, resolved_pool, _player_lookup(resolved_pool)


def _onboarding(store, player: dict) -> bool:
    if player.get("onboarding_completed_at"):
        return False

    st.markdown("### 🏈 How Teal's Sunday Pick'em works")
    st.caption("Five picks. One Sunday. Most fantasy points wins the week.")

    with st.container(border=True):
        st.markdown("**1 · Pick your five.**")
        st.caption("QB · RB · WR · TE · K — five weekly options at each position.")
        st.caption("Tap a player, then tap Next to save each position.")

    with st.container(border=True):
        st.markdown("**2 · Know the scoring.**")
        st.markdown(
            "**Passing:** 1 pt / 25 yds · 4 / TD · −2 / INT  \n"
            "**Rushing & receiving:** 1 pt / 10 yds · 6 / TD · +0.5 / reception  \n"
            "**Kicker:** 3 / made FG · 1 / made XP"
        )
        st.caption("Fractional points count. Fumble lost −2 · two-point conversion +2 · return TD +6 · missed kicks 0.")

    with st.container(border=True):
        st.markdown("**3 · Questionable player? Set a backup.**")
        st.caption("Pick a healthy emergency backup from the same position. It only activates if your starter is ruled OUT/inactive and does not play.")

    with st.container(border=True):
        st.markdown("**4 · Lock Sunday at 1:00 PM ET.**")
        st.caption("After lock, follow the live standings. Weekly finishes also earn points toward the season championship.")

    st.caption("You can always find the full rules later in Profile → How to Play & Scoring.")
    if st.button("Let's Play", type="primary", use_container_width=True):
        updated = store.complete_onboarding(str(player["id"]))
        st.session_state.player = updated or {**player, "onboarding_completed_at": datetime.now(UTC).isoformat()}
        st.rerun()
    return True


def _week_header(week: dict) -> None:
    label = html.escape(str(week.get("label") or f"Week {week.get('nfl_week', '')}"))
    test = bool(week.get("is_demo"))
    st.markdown(
        f"""
<div class="card">
  <div class="eyebrow">{'Build test • does not affect Week 1' if test else 'Current Sunday'}</div>
  <div class="week-title">{label}</div>
  <div class="small">Locks {html.escape(et_label(week.get('locks_at')))}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def _summary_rows(picks: list[dict], pool_by_id: dict[str, dict], *, show_backups: bool = True) -> str:
    by_pos = picks_by_position(picks)
    rows = []
    for pos in POSITIONS:
        pick = by_pos.get(pos)
        starter = pool_by_id.get(str(pick.get("pool_player_id"))) if pick else None
        if starter:
            badge = _status_badge(starter)
            backup_text = ""
            if show_backups and safe_status(starter.get("availability_status")) == "QUESTIONABLE" and pick.get("emergency_pool_player_id"):
                backup = pool_by_id.get(str(pick.get("emergency_pool_player_id")))
                if backup:
                    backup_text = f'<div class="meta">Emergency: {html.escape(_display_name(backup))}</div>'
            detail = f'<div><span class="player-name">{html.escape(_display_name(starter))}</span>{badge}<div class="meta">{html.escape(_player_meta(starter))}</div>{backup_text}</div>'
        else:
            detail = '<div class="small">Not picked yet</div>'
        rows.append(f'<div class="lineup-row"><span class="position-pill">{pos}</span>{detail}</div>')
    return "".join(rows)




def _begin_review_edit(position: str) -> None:
    """Open one position from Review My Five without an extra rerun."""
    st.session_state.builder_return_mode = "review"
    st.session_state.builder_position = position
    st.session_state.builder_mode = "pick"


def _render_review_editable_lineup(picks: list[dict], pool_by_id: dict[str, dict]) -> None:
    """Render the five review cards as direct edit targets."""
    st.caption("Tap any player to change your pick.")
    by_pos = picks_by_position(picks)
    for position in POSITIONS:
        pick = by_pos.get(position)
        starter = pool_by_id.get(str(pick.get("pool_player_id"))) if pick else None
        if not starter:
            st.button(
                f"**{position} · Not picked yet**\nTap to choose a player",
                key=f"pickbtn_review_edit_missing_{position}",
                type="secondary",
                use_container_width=True,
                on_click=_begin_review_edit,
                args=(position,),
            )
            continue

        review_row = dict(starter)
        review_row["player_name"] = f"{position} · {_display_name(starter)}"
        extra_line = ""
        if safe_status(starter.get("availability_status")) == "QUESTIONABLE" and pick and pick.get("emergency_pool_player_id"):
            backup = pool_by_id.get(str(pick.get("emergency_pool_player_id")))
            if backup:
                extra_line = f"↳ Emergency: {_display_name(backup)}"
        _render_player_card_button(
            review_row,
            key=f"review_edit_{position}",
            on_click=_begin_review_edit,
            args=(position,),
            extra_line=extra_line,
            allow_out_click=True,
        )


def _advance_builder(position: str) -> None:
    nxt = next_position(position)
    if nxt:
        st.session_state.builder_position = nxt
        st.session_state.builder_mode = "pick"
    else:
        st.session_state.builder_position = None
        st.session_state.builder_mode = "review"


def _complete_builder_step(position: str) -> None:
    return_mode = st.session_state.pop("builder_return_mode", None)
    if return_mode in {"review", "home"}:
        st.session_state.builder_position = None
        st.session_state.builder_mode = return_mode
        return
    _advance_builder(position)


def _pending_builder_key(kind: str, week: dict, player: dict, position: str) -> str:
    return f"builder_pending::{kind}::{week['id']}::{player['id']}::{position}"


def _clear_pending_builder(week: dict, player: dict, position: str) -> None:
    st.session_state.pop(_pending_builder_key("starter", week, player, position), None)
    st.session_state.pop(_pending_builder_key("backup", week, player, position), None)


def _select_starter(week: dict, player: dict, position: str, row: dict) -> None:
    """Stage a starter locally. Supabase is not touched until the user taps Next."""
    st.session_state[_pending_builder_key("starter", week, player, position)] = str(row["id"])
    # A different starter cannot inherit a previously staged emergency backup.
    st.session_state.pop(_pending_builder_key("backup", week, player, position), None)
    st.session_state.builder_position = position
    st.session_state.builder_mode = "pick"


def _select_backup(week: dict, player: dict, position: str, row: dict) -> None:
    """Stage an emergency backup locally. Starter + backup save together on Next."""
    st.session_state[_pending_builder_key("backup", week, player, position)] = str(row["id"])
    st.session_state.builder_position = position
    st.session_state.builder_mode = "backup"


def _save_selected_position(
    store,
    week: dict,
    player: dict,
    position: str,
    *,
    lineup: dict | None,
    picks: list[dict],
    pool: list[dict],
    starter_id: str,
    backup_id: str = "",
) -> tuple[dict | None, list[dict]]:
    """Persist one confirmed position exactly once, then refresh the local snapshot."""
    by_pos = picks_by_position(picks)
    current = by_pos.get(position)
    current_starter_id = str(current.get("pool_player_id") or "") if current else ""
    current_backup_id = str(current.get("emergency_pool_player_id") or "") if current else ""

    # Tapping the already-saved choice and pressing Next should not generate a
    # redundant Supabase upsert. It is navigation only.
    if current and current_starter_id == str(starter_id) and current_backup_id == str(backup_id or ""):
        _clear_pending_builder(week, player, position)
        return lineup, picks

    saved = store.save_pick(
        week_id=str(week["id"]),
        player_id=str(player["id"]),
        position=position,
        pool_player_id=str(starter_id),
        emergency_pool_player_id=str(backup_id) if backup_id else None,
        lineup_id=str(lineup["id"]) if lineup else None,
        known_week=week,
        known_pool=pool,
    )
    resolved_lineup = lineup or {
        "id": str(saved["lineup_id"]),
        "week_id": str(week["id"]),
        "player_id": str(player["id"]),
        "confirmed_at": None,
    }
    merged = _merge_saved_pick(picks, saved)
    _stash_lineup_snapshot(week, player, resolved_lineup, merged)
    _clear_pending_builder(week, player, position)
    return resolved_lineup, merged


def _markdown_escape(value: str) -> str:
    """Escape user/provider text that is inserted into a Streamlit button label."""
    text = str(value or "")
    for ch in ("\\", "`", "*", "_", "[", "]"):
        text = text.replace(ch, "\\" + ch)
    return text


def _render_player_card_button(
    row: dict,
    *,
    key: str,
    selected: bool = False,
    disabled: bool = False,
    on_click=None,
    args: tuple = (),
    extra_line: str = "",
    allow_out_click: bool = False,
) -> bool:
    """Render one real full-size button as the player card.

    Do not layer an invisible button over separate HTML. The visible card IS the
    Streamlit button, so every pixel of the card is a native tap target on
    desktop and mobile.
    """
    status = safe_status(row.get("availability_status"))
    safe_key = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in key)
    state_key = "selected_" if selected else ""
    status_key = "q_" if status == "QUESTIONABLE" else ("out_" if status == "OUT" else "")
    widget_key = f"pickbtn_{state_key}{status_key}{safe_key}"

    name = _markdown_escape(str(row.get("player_name") or "—"))
    meta = _markdown_escape(_player_meta(row))
    check = "✓ " if selected else ""
    badge = " :yellow-badge[⚠ QUESTIONABLE]" if status == "QUESTIONABLE" else (" :red-badge[OUT]" if status == "OUT" else "")
    extra = f"\n{_markdown_escape(extra_line)}" if extra_line else ""
    # The statistical strip is *inside the same native Streamlit button*, so
    # it cannot obstruct taps or create a second picker interaction.
    # Legacy button regression shape: label = f"{check}**{name}**{badge}\n{meta}{extra}"
    season_text = _markdown_escape(stats_line(row)) if "_season_stats" in row else ""
    season_strip = f"\n:gray[📊 {season_text}]" if season_text else ""
    label = f"{check}**{name}**{badge}\n{meta}{season_strip}{extra}"

    return st.button(
        label,
        key=widget_key,
        disabled=disabled or (status == "OUT" and not allow_out_click),
        type="secondary",
        width="stretch",
        wrap=True,
        on_click=on_click,
        args=args,
    )


def _picker_progress_html(picks: list[dict], current_position: str) -> str:
    """A read-only progress bar; pending taps never count as saved picks."""
    saved = {
        position for position, pick in picks_by_position(picks).items()
        if position in POSITIONS and pick.get("pool_player_id")
    }
    step = POSITIONS.index(current_position) + 1
    chips: list[str] = []
    for position in POSITIONS:
        classes = "picker-step"
        if position in saved:
            classes += " picker-step-saved"
        if position == current_position:
            classes += " picker-step-current"
        indicator = " ✓" if position in saved else ""
        current_attr = ' aria-current="step"' if position == current_position else ""
        chips.append(
            f'<span class="{classes}"{current_attr}>'
            f'{html.escape(position + indicator)}</span>'
        )
    return (
        '<div class="picker-progress" role="group"'
        f' aria-label="Step {step} of 5; {len(saved)} of 5 picks saved">'
        f'<div class="picker-progress-label">Step {step} of 5 · {len(saved)} saved</div>'
        f'<div class="picker-progress-steps">{"".join(chips)}</div>'
        '</div>'
    )


def _builder(store, week: dict, player: dict, position: str, pool: list[dict]) -> None:
    # While the builder is open, keep the already-loaded lineup snapshot warm.
    # The database remains authoritative when Next performs the actual write.
    lineup, picks, pool, pool_by_id = _load_lineup(
        store, week, player, pool, snapshot_ttl_seconds=300.0
    )
    by_pos = picks_by_position(picks)
    saved_current = by_pos.get(position)
    saved_starter_id = str(saved_current.get("pool_player_id") or "") if saved_current else ""
    saved_backup_id = str(saved_current.get("emergency_pool_player_id") or "") if saved_current else ""

    pending_starter_id = str(
        st.session_state.get(_pending_builder_key("starter", week, player, position)) or ""
    )
    current_id = pending_starter_id or saved_starter_id

    pending_backup_id = str(
        st.session_state.get(_pending_builder_key("backup", week, player, position)) or ""
    )
    if pending_backup_id:
        backup_id = pending_backup_id
    elif current_id and current_id == saved_starter_id:
        backup_id = saved_backup_id
    else:
        backup_id = ""

    rows = _stable_order(str(player["id"]), str(week["id"]), position, position_pool(pool, position))
    mode = st.session_state.get("builder_mode", "pick")

    st.markdown(_picker_progress_html(picks, position), unsafe_allow_html=True)
    st.markdown(f"### Choose your {position}")
    st.caption("Tap a player to highlight it. Your choice saves only when you tap Next.")
    if not week.get("is_demo"):
        previous_week = max(0, int(week.get("nfl_week") or 1) - 1)
        if previous_week:
            st.caption(f"Season stats through Week {previous_week} · averages per recorded game; TD, FG and XP are season totals.")
        else:
            st.caption("Season stats begin after Week 1.")

    starter = pool_by_id.get(current_id) if current_id else None
    backup = pool_by_id.get(backup_id) if backup_id else None
    backup_ready = bool(
        starter
        and backup
        and str(backup.get("id")) != str(starter.get("id"))
        and safe_status(backup.get("availability_status")) != "OUT"
    )

    if starter and not bool(starter.get("is_visible", True)):
        if safe_status(starter.get("availability_status")) == "OUT":
            st.warning(
                f"Your saved {position} pick, {_display_name(starter)}, is now OUT. "
                "Your pick was preserved. Choose a replacement if you want to change it before lock."
            )
        else:
            st.warning(
                f"Your saved {position} pick, {_display_name(starter)}, is no longer in the active five. "
                "Your pick was preserved. Choose a replacement if you want to change it before lock."
            )

    if mode == "backup":
        if not starter or safe_status(starter.get("availability_status")) != "QUESTIONABLE":
            st.session_state.builder_mode = "pick"
            st.rerun()

        st.markdown(
            f'<div class="status-warn"><strong>⚠️ {_display_name(starter)} is Questionable.</strong><br>Choose one of the other {position}s as your emergency backup.</div>',
            unsafe_allow_html=True,
        )
        st.info(
            "How the emergency backup works: If your starter is ruled OUT/inactive after the 1:00 PM ET lock "
            "and does not play, your emergency backup replaces them. If your starter plays at all, your starter counts. "
            "Your backup stays private unless it activates."
        )
        for row in rows:
            if str(row["id"]) == current_id:
                continue
            _render_player_card_button(
                row,
                key=f"backup::{position}::{row['id']}",
                selected=str(row["id"]) == backup_id,
                on_click=_select_backup,
                args=(week, player, position, row),
            )

        return_mode = st.session_state.get("builder_return_mode")
        left, right = st.columns(2)
        with left:
            if st.button("Change starter", use_container_width=True):
                st.session_state.pop(_pending_builder_key("backup", week, player, position), None)
                st.session_state.builder_mode = "pick"
                st.rerun()
        with right:
            if return_mode == "review":
                next_label = "Return to Review →"
            elif return_mode == "home":
                next_label = "Return to Lineup →"
            else:
                nxt = next_position(position)
                next_label = f"Next: {nxt} →" if nxt else "Review My Five →"
            if st.button(next_label, type="primary", use_container_width=True, disabled=not backup_ready):
                try:
                    _save_selected_position(
                        store,
                        week,
                        player,
                        position,
                        lineup=lineup,
                        picks=picks,
                        pool=pool,
                        starter_id=current_id,
                        backup_id=backup_id,
                    )
                    _complete_builder_step(position)
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        return

    for row in rows:
        _render_player_card_button(
            row,
            key=f"starter::{position}::{row['id']}",
            selected=str(row["id"]) == current_id,
            on_click=_select_starter,
            args=(week, player, position, row),
        )

    left, right = st.columns(2)
    with left:
        return_mode = st.session_state.get("builder_return_mode")
        prev = previous_position(position)
        back_disabled = prev is None and return_mode not in {"review", "home"}
        back_label = "← Review" if return_mode == "review" else ("← Lineup" if return_mode == "home" else "← Back")
        if st.button(back_label, use_container_width=True, disabled=back_disabled):
            # Back means "discard this unconfirmed tap"; only Next commits it.
            _clear_pending_builder(week, player, position)
            if return_mode in {"review", "home"}:
                st.session_state.pop("builder_return_mode", None)
                st.session_state.builder_position = None
                st.session_state.builder_mode = return_mode
            else:
                st.session_state.builder_position = prev
                st.session_state.builder_mode = "pick"
            st.rerun()
    with right:
        starter = pool_by_id.get(current_id) if current_id else None
        starter_is_questionable = bool(starter and safe_status(starter.get("availability_status")) == "QUESTIONABLE")
        starter_needs_backup = bool(starter_is_questionable and not backup_ready)
        if starter_needs_backup:
            next_label = "Choose Emergency Backup →"
        elif return_mode == "review":
            next_label = "Return to Review →"
        elif return_mode == "home":
            next_label = "Return to Lineup →"
        else:
            nxt = next_position(position)
            next_label = f"Next: {nxt} →" if nxt else "Review My Five →"

        if st.button(next_label, type="primary", use_container_width=True, disabled=not current_id):
            if starter_needs_backup:
                st.session_state.builder_position = position
                st.session_state.builder_mode = "backup"
                st.rerun()
            else:
                try:
                    _save_selected_position(
                        store,
                        week,
                        player,
                        position,
                        lineup=lineup,
                        picks=picks,
                        pool=pool,
                        starter_id=current_id,
                        backup_id=backup_id if starter_is_questionable else "",
                    )
                    _complete_builder_step(position)
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


def _render_pool_change_disclaimer() -> None:
    """Explain pre-lock pool replacements without implying saved picks can move."""
    st.caption(
        "ℹ️ Player statuses can change during the week. If a pool player is ruled OUT before "
        "Saturday at 11:59 PM ET, the app may add a replacement to the pool. "
        "**Your saved picks will never change automatically.** Check back before Sunday’s "
        "1:00 PM ET lock if one of your starters is affected."
    )


def _review(store, week: dict, player: dict, pool: list[dict]) -> None:
    lineup, picks, pool, pool_by_id = _load_lineup(store, week, player, pool)
    chosen, total = lineup_progress(picks)
    needs = required_backup_positions(picks, pool_by_id)
    unavailable = unavailable_starter_positions(picks, pool_by_id)

    st.markdown("### Review My Five")
    _render_review_editable_lineup(picks, pool_by_id)
    if not bool(week.get("is_demo")):
        _render_pool_change_disclaimer()

    if chosen < total:
        st.warning(f"Finish all five positions first. You have {chosen} of {total}.")
        if st.button("Continue Building", type="primary", use_container_width=True):
            st.session_state.pop("builder_return_mode", None)
            st.session_state.builder_position = first_incomplete_position(picks, pool_by_id) or POSITIONS[0]
            st.session_state.builder_mode = "pick"
            st.rerun()
        return
    if unavailable:
        st.warning("Replace the unavailable player at: " + ", ".join(unavailable))
        if st.button("Replace unavailable player", type="primary", use_container_width=True):
            st.session_state.builder_return_mode = "review"
            st.session_state.builder_position = unavailable[0]
            st.session_state.builder_mode = "pick"
            st.rerun()
        return
    if needs:
        st.warning("Choose a healthy emergency backup for: " + ", ".join(needs))
        if st.button("Fix injury backup", type="primary", use_container_width=True):
            st.session_state.builder_return_mode = "review"
            st.session_state.builder_position = needs[0]
            st.session_state.builder_mode = "backup"
            st.rerun()
        return

    # The five player rows themselves are now the edit controls, so the primary
    # save action can stay immediately below the lineup without a second bank
    # of Change QB/RB/WR/TE/K buttons.
    st.markdown("**Everything look right?**")
    if st.button("SAVE MY LINEUP", type="primary", use_container_width=True):
        try:
            updated_lineup = store.confirm_lineup(
                str(week["id"]),
                str(player["id"]),
                lineup_id=str(lineup["id"]) if lineup else None,
                known_week=week,
            )
            _stash_lineup_snapshot(week, player, updated_lineup, picks)
            st.session_state.builder_position = None
            st.session_state.builder_mode = "home"
            st.session_state.lineup_saved_flash = True
            st.rerun()
        except Exception as exc:
            st.error(str(exc))



def _open_home(store, week: dict, player: dict, pool: list[dict]) -> None:
    lineup, picks, pool, pool_by_id = _load_lineup(store, week, player, pool)
    chosen, total = lineup_progress(picks)
    needs = required_backup_positions(picks, pool_by_id)
    unavailable = unavailable_starter_positions(picks, pool_by_id)

    if st.session_state.pop("lineup_saved_flash", False):
        if bool(week.get("is_demo")):
            st.success("Test lineup saved. You can keep editing while the Gate 2 test week is open.")
        else:
            st.success("Lineup saved. You can make changes until Sunday at 1:00 PM ET.")

    if not bool(week.get("is_demo")):
        _render_live_prelock_status(store, week, player)

    if chosen == total and not needs and not unavailable:
        # This is the first content directly after Sunday Status on a ready
        # lineup's home screen. The Pulse is optional and must never displace
        # a required selection or injury-repair action.
        if not bool(week.get("is_demo")):
            render_pregame_pulse(store, week, player)
        st.markdown("### ✅ YOUR FIVE ARE READY")
        st.markdown(f'<div class="card">{_summary_rows(picks, pool_by_id)}</div>', unsafe_allow_html=True)
        if not bool(week.get("is_demo")):
            _render_pool_change_disclaimer()
        if bool(week.get("is_demo")):
            st.markdown('<div class="status-test"><strong>TEST WEEK • LOCK OPEN</strong><br>Build and edit freely while testing.</div>', unsafe_allow_html=True)
        if st.button("EDIT LINEUP", type="primary", use_container_width=True):
            st.session_state.pop("builder_return_mode", None)
            st.session_state.builder_position = None
            st.session_state.builder_mode = "review"
            st.rerun()
    else:
        st.markdown(
            f'<div class="card"><div class="eyebrow">Your lineup</div><div class="big-number">{chosen} of {total}</div><div class="small">picks complete</div></div>',
            unsafe_allow_html=True,
        )
        if bool(week.get("is_demo")):
            st.markdown('<div class="status-test"><strong>TEST WEEK • LOCK OPEN</strong><br>Build and edit freely while testing.</div>', unsafe_allow_html=True)
        label = "Replace Unavailable Player" if unavailable else ("Fix Injury Backup" if needs else ("Continue Building" if chosen else "Build My Five"))
        if st.button(label, type="primary", use_container_width=True):
            if needs or unavailable:
                st.session_state.builder_return_mode = "home"
            else:
                st.session_state.pop("builder_return_mode", None)
            st.session_state.builder_position = (unavailable[0] if unavailable else (needs[0] if needs else first_incomplete_position(picks, pool_by_id))) or POSITIONS[0]
            st.session_state.builder_mode = "backup" if needs and not unavailable else "pick"
            st.rerun()


def _locked_home(store, week: dict, player: dict, pool: list[dict]) -> None:
    lineup, picks, pool, pool_by_id = _load_lineup(store, week, player, pool)
    chosen, total = lineup_progress(picks)
    st.markdown("### 🔒 Picks are locked")
    st.markdown(f'<div class="card">{_summary_rows(picks, pool_by_id)}</div>', unsafe_allow_html=True)
    if chosen < total:
        st.caption(f"You locked with {chosen} of {total} positions filled. Missing positions score 0.")
    else:
        st.caption("Your five are set for Sunday. Live scoring arrives in the next build gate.")


def render_player_game(
    store,
    player: dict,
    on_sign_out=None,
    *,
    allow_demo_week: bool = False,
    skip_onboarding: bool = False,
) -> None:
    if st.session_state.get("gate4_demo"):
        render_gate4_demo(player)
        return

    if not skip_onboarding and _onboarding(store, player):
        return

    if "builder_mode" not in st.session_state:
        st.session_state.builder_mode = "home"
    if "builder_position" not in st.session_state:
        st.session_state.builder_position = None
    if "use_demo_week" not in st.session_state:
        st.session_state.use_demo_week = False

    # Gate 2's synthetic test week is Commissioner-only in production. Any
    # stale browser session left inside the old public preview is forced back
    # to the real week before rendering the normal player app.
    if not allow_demo_week and st.session_state.get("use_demo_week"):
        st.session_state.use_demo_week = False
        st.session_state.builder_mode = "home"
        st.session_state.builder_position = None
        st.session_state.pop("builder_return_mode", None)

    real_week = store.get_real_week()
    demo_week = store.get_demo_week() if allow_demo_week else None
    week = demo_week if allow_demo_week and st.session_state.use_demo_week and demo_week else real_week

    if not week:
        st.info("The next Sunday week is being prepared.")
        st.caption(f"Build {APP_VERSION}")
        return

    phase = week_phase(week)

    # Gate 2's isolated test week remains a focused lineup-builder test. The
    # normal app gets the four-tab Gate 4 navigation.
    if not bool(week.get("is_demo")):
        tab = render_nav()
        if tab == "🏆 Season":
            render_leaderboards(store, week, player, phase)
            return
        if tab == "🕘 History":
            render_history(store, int(week.get("season") or 2026))
            return
        if tab == "👤 Profile":
            render_profile(store, player, int(week.get("season") or 2026), on_sign_out)
            return

        # GitHub Actions remains the primary scheduler. On the Sunday tab only,
        # an active player can recover a launch-critical job if GitHub is late.
        # The Supabase lease keeps concurrent sessions from duplicating provider
        # work, and any recovery failure is deliberately invisible/non-fatal.
        week, _automation_recovery = maybe_recover_critical_automation(store, week)
        phase = week_phase(week)

    _week_header(week)

    if bool(week.get("is_demo")):
        st.markdown('<div class="status-test"><strong>Gate 2 test week.</strong> Picks here are isolated and never count toward Week 1.</div>', unsafe_allow_html=True)
        if st.button("Exit Gate 2 Test Week", use_container_width=True):
            st.session_state.use_demo_week = False
            st.session_state.builder_mode = "home"
            st.session_state.builder_position = None
            st.session_state.pop("builder_return_mode", None)
            if st.session_state.get("commish"):
                st.session_state.gate2_demo = False
                st.session_state.pop("gate2_demo_player_id", None)
            st.rerun()
    elif phase == "upcoming":
        label = str(week.get("label") or f"Week {week.get('nfl_week', '')}")
        st.markdown(f"### {label} opens Tuesday")
        _countdown(str(week["opens_at"]), "New picks available in")
        st.caption(et_label(week.get("opens_at")))
        return

    if phase == "locked" and not bool(week.get("is_demo")):
        maybe_render_final_celebration(store, week, player)
        render_live_sunday(store, week, player, show_storylines=True)
        return

    if phase == "open" and not bool(week.get("is_demo")):
        _lock_transition_guard(week.get("locks_at"))

    pool = store.get_week_pool(str(week["id"]), visible_only=True)

    if (phase == "open" and not bool(week.get("is_demo")) and pool_is_ready(pool)
            and st.session_state.get("builder_mode") in {"pick", "backup", "review"}):
        # All 25 visible cards + any future promoted reserves use one shared,
        # frozen snapshot. Provider failures may hide only the statistics;
        # they cannot affect the picker or any saved lineup.
        try:
            pool = attach_snapshot(pool, load_or_prepare_snapshot(store, week))
        except Exception:
            pass

    if phase == "open" and not pool_is_ready(pool):
        st.info("This week's player pool is being prepared. Picks will appear as soon as all five positions are ready.")
        return

    if phase == "locked":
        _locked_home(store, week, player, pool)
        return

    mode = str(st.session_state.get("builder_mode") or "home")
    position = st.session_state.get("builder_position")
    if mode in {"pick", "backup"} and position in POSITIONS:
        _builder(store, week, player, str(position), pool)
    elif mode == "review":
        _review(store, week, player, pool)
    else:
        _open_home(store, week, player, pool)

