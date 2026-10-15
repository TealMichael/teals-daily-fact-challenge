# Teal's Daily Fact Challenge v2.24.1 — Igniter Answer-Type Hotfix

This is a focused hotfix on top of v2.24.0 Interactive Math Questions.

## Fix
The Igniter/Warm-Up Answer type menu must include:
- Compare Values
- Order Tiles

A classroom screenshot showed the old pre-v2.24 menu sequence, proving the deployed `warmup.py` was still stale. This package re-ships the complete interactive-math file set and adds a defensive fallback in the shared teacher answer editor.

Expected menu order:
`Short answer` → `Number` → `Fraction` → `Multiple choice` → `Number + Label` → `Compare Values` → `Order Tiles` → `Expanded Form` → `Equivalent Number` → `Multi-Part — 2 answers`

No new Supabase SQL or Secrets changes are required.
