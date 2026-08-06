# YouTube membership.join — active-state evidence (B fixed)

- observed_at: 2026-08-06T13:53:48+09:00
- app: YouTube (`com.google.android.youtube`)
- goal_id: `membership.join`
- architecture: B fixed, public Navigation Prior enabled
- device: Samsung SM-G998N (`R3CR60V3DKM`), Android 15
- executor source: `dbc14a9e610b1fb1fdd7dde4f3e6f6e6313f1324`
- executor APK SHA-256: `556F3AD1506713F3503DD7A969F8F4BBACF72A174B5D7D9707457C0702B59D0C`
- result: `state_not_applicable`
- dangerous automatic actions: 0

## Real-device path

1. From the YouTube home screen, Codex selected the grounded `내 페이지`
   candidate `a11y_ac67d4a12a0d0d3fd365`.
2. The resulting account surface displayed `Premium 회원`; Codex selected the
   direct `Premium 혜택` candidate `a11y_355d708594795e69bfb5`.
3. The observed destination displayed `Premium`, `회원 가입일: 2024년 11월
   03일`, and accumulated Premium benefits such as ad-free playback hours.
4. Because the account is already subscribed, attempting membership.join would
   require changing account state. The episode ended with `stop_for_user` and
   no purchase, subscription, login, or personal-information action.

Runtime source sessions:

- `navs_a506de30975d48a0b97f21061616f427`
- `navs_d5f8961014ac4bd3a5351d8e18c91410`

The first click executed and changed the screen with `progress=advanced`, even
though the server outcome row used `blocked`; Review therefore records the
observed execution rather than treating that server label as success evidence.

## Review DB

Reviewer `codex-yanggeon` verified every before-screen candidate for all three
decisions. Runtime remained read-only.

- decisions reviewed: 3 / 3
- candidates reviewed: 67 / 67
- `best`: 2
- `acceptable`: 2
- `hard_negative`: 62
- `unsafe`: 0
- `unknown`: 1 (unnamed candidate with insufficient semantics)

The terminal Premium evidence screen has no candidate that should be clicked
for membership.join; its 15 candidates are all hard negatives and the correct
action is `stop_for_user`.

This B-fixed evidence replaces the old pre-B coverage judgment for this cell.
It is not a successful join transition and is not promoted directly from
Runtime to Decision Memory.
