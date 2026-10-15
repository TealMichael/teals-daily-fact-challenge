# Teal's Daily Fact Challenge v2.24.3 — Order Tiles Drag Hotfix

v2.24.3 keeps all v2.24.2 behavior and fixes the **Order Tiles** student interaction.

## What changed
- Desktop/laptop mouse dragging now uses native browser drag-and-drop.
- Touch/pen dragging uses pointer events with corrected tile hit-testing.
- Fixes the flex-row positioning bug that could make a horizontal drag appear completely stuck.
- Adds a classroom-safe fallback: tap a tile and use **← Move** / **Move →** if drag behavior is unavailable on a device.
- Physical-keyboard arrow reordering remains supported.
- The same shared widget is used by Igniter, Quiz of the Week, and Monday Recovery.

## Deployment
No Supabase SQL and no Secrets changes are required for v2.24.3. The v2.24.2 SQL constraint hotfix remains part of the cumulative build and should already have been run once.
