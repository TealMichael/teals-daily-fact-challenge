# Teal's Daily Fact Challenge v2.24.0 — Interactive Math Questions

This cumulative release is built directly from the working v2.23.0 FULL CURRENT APP.

## New in v2.24.0
- Adds **Compare Values** as a shared question type.
  - Teacher enters the left and right values.
  - The correct `<`, `=`, or `>` symbol is calculated automatically using exact math.
  - Students tap one of the three comparison symbols.
- Adds **Order Tiles** as a shared question type.
  - Teacher enters 3–6 number tiles and chooses least-to-greatest or greatest-to-least.
  - Students drag the tiles into order.
  - Mouse, touch, and keyboard arrow-key reordering are supported.
- Both question types work in **Igniter, Quiz of the Week, Indiana Question Bank, and Monday Recovery**.
- Decimal/fraction equivalence is exact: for example, `0.50 = 0.5` and `1/2 = 0.5`.
- Order Tiles preserves teacher-entered labels and accepts either order among equivalent-value tiles.
- Quiz Back/Edit restores previously saved Order Tiles responses.
- Eight permanent bank questions now use the new interactive formats, including four Grade 5 `5.NS.1` items for current decimal comparison/ordering work.

## Setup
No new Supabase SQL is required.
No Secrets changes are required.

## Privacy
No new student identity fields are introduced. The existing anonymous Student Key / app UUID architecture remains unchanged.

## Unchanged
Daily 10, Fix Your Misses, Focus Practice, teaching models, Weekly Mystery, Top 10, Perfect Score Club, AWTRIX, Monday Recovery rules, Standards Mastery Tracker, Quiz navigation, temporary image cleanup, anonymous Skyward export, and local-only bridge workbooks remain unchanged.
