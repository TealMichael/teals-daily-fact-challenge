# Teal's Daily Fact Challenge v2.24.2 — Interactive Math Save Constraint Hotfix

v2.24.2 keeps all v2.24.1 behavior and fixes Supabase answer-table constraints for the two v2.24 interactive question types:
- **Compare Values**
- **Order Tiles**

Run `RUN_THIS_ONCE_IN_SUPABASE_v2_24_2.sql` once in the production Supabase SQL Editor before relying on these types with students. It only broadens existing `question_type` CHECK constraints for Igniter, Quiz of the Week, and Monday Recovery.

No Secrets changes and no privacy architecture changes.
