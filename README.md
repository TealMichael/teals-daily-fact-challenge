# Teal's Daily Fact Challenge

A classroom-first multiplication fact fluency game built for a shared 10-fact Daily Challenge, accuracy-first class competition, and visual Practice teaching.

## Student experience

- **One shared Daily 10**: every class receives the same 10 facts in the same order each day.
- **Balanced facts**: 2s-10s are the core. A Daily may include one 11/12 fact, but never more than one, and many days include none.
- **Fair ranking**: accuracy ranks first; total timed-sprint time breaks ties.
- **Fact 1 starts the game**: Fact 1 counts toward accuracy but is untimed. The clock begins the instant Fact 1 is submitted, then Facts 2-10 appear one at a time with no Streamlit page-load delay added between facts.
- **No Daily spoilers**: students do not see right/wrong feedback until all 10 are finished. A Back button lets them fix a typo while the timer keeps running, and an in-browser resume preserves the same timed run after an accidental refresh on that device.
- **Top 10 only**: students see only their class Top 10. Lower exact ranks are intentionally private.
- **Daily review**: completed players can review all 10 and get array-based teaching for missed facts.
- **Practice**: students choose Mixed or a specific 2s-12s family and receive immediate feedback, a multiplication array, repeated addition, and a simple strategy tip.

There is intentionally **no social sharing feature**. This app is designed for in-class use.

## Teacher Dashboard

The password-protected Teacher Dashboard supports roughly 90 students across multiple classes and includes:

- create and manage classes;
- paste a batch of nicknames and automatically generate private 4-digit PINs;
- download the newly generated nickname/PIN sheet immediately;
- view full class completion, accuracy, and timing data that students cannot see;
- preview the day's balanced 10 facts;
- rename student nicknames;
- reset student PINs;
- deactivate/reactivate student accounts;
- reset today's Daily attempt when a technology problem or accidental start requires a fresh run;
- export class rosters without PINs.

The app does not require student emails, school IDs, or full legal names. Public class leaderboards use teacher-assigned nicknames only.

## Daily fact design

The deterministic generator is versioned as `TDFC-DAILY-v1`.

Each Daily contains exactly 10 unique multiplication decisions, with commutative mirrors treated as the same fact so a set cannot contain both `6 × 7` and `7 × 6`.

Core days contain:

- 3 easier retrieval facts;
- 4 medium facts;
- 3 harder facts.

On an extension day, one harder slot is replaced by exactly one 11/12 fact. Extension days occur deterministically on roughly 40% of dates.

Consecutive Daily Challenges are intentionally selected from rotating pools so the underlying facts do not repeat from one day to the next.

## Data and privacy

Persistence uses a separate Supabase project and the server-side `SUPABASE_SECRET_KEY`.

- Student PINs are stored only as salted scrypt hashes.
- Supabase Row Level Security is enabled on every app table with no public browser policies.
- Students cannot query the database directly.
- One Daily attempt exists per student per date unless the teacher explicitly resets it.
- Class leaderboards are isolated by class.

## Streamlit Secrets

```toml
SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
SUPABASE_SECRET_KEY = "YOUR-SERVER-SECRET-KEY"
TEACHER_PASSWORD = "CHOOSE-A-PRIVATE-TEACHER-PASSWORD"
```

If `SUPABASE_URL` is accidentally pasted with `/rest/v1`, the app automatically normalizes it for the Python client.

## Version notes

### v1.0.0 — Full classroom beta

First complete release of **Teal's Daily Fact Challenge**.

Includes the balanced shared Daily 10, Fact-1 timing start, accuracy-first Top 10 class leaderboard, hidden feedback until completion, array-based review, unlimited focus-family Practice, student nickname/PIN accounts, three-class/90-student-ready teacher tools, Supabase persistence, teacher attempt resets, and classroom-safe privacy defaults.

See `DEPLOYMENT_STEPS.txt` for the one-time setup.
