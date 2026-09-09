# Decisions

Why the prototype is built the way it is. Recorded because for a project of this size the
reasoning is more interesting than the code, and because most of these were genuinely arguable.

---

## 1. One question instead of a dashboard

**Decision.** The screen answers "what has changed?" rather than displaying every metric Junction
exposes.

**Why.** Wearable APIs make it trivial to render a lot of numbers, and hard to say which of them
matters. A page of sparklines pushes the interpretive work onto the reader. Narrowing to a single
question meant the interesting problems became "what counts as a change" and "how do we justify
it" — which are product problems rather than layout problems.

**Cost.** The app cannot answer "how did I sleep last Tuesday?". Given a day, that felt like the
right thing to give up.

---

## 2. Deterministic arithmetic, not a model

**Decision.** The insight is `(recent mean − baseline mean) / baseline mean × 100`, with a fixed
threshold. No model, no learned score.

**Why.** The product claim is not "we detected something", it is "here is what changed, and here
is the arithmetic". An unexplainable score would undermine the one feature worth building. For
anything touching health data, a figure the user can check is worth more than a figure that is
marginally more sophisticated.

**Cost.** No seasonality, no per-person variance, no multi-metric correlation. A 10% threshold is
arbitrary and is labelled as such in the UI, the README and the code.

---

## 3. A protocol between the app and Junction

**Decision.** `HealthDataSource` is a two-method `Protocol`. The live client and a deterministic
local generator both satisfy it.

**Why.** Junction's synthetic connections are sandbox-only, expire after seven days, and need
credentials. Without a seam, the app would be unrunnable after a clone and untestable in CI.
With one, the entire analysis path is exercised with no network at all, and switching to live
data is a configuration change rather than a code change.

**Why it is not just a mock.** Fixture payloads are emitted as dicts and validated through the
same pydantic models as live responses, so a fixture cannot drift away from the real schema. The
generated patient contains deliberate gaps — two days with no data, four nights with no resting
heart rate — so it exercises the awkward paths instead of flattering them.

**Cost.** Two code paths to keep honest. Mitigated by the shared models and by
`/health` reporting which source is live.

---

## 4. Missing days are gaps, not zeros

**Decision.** A day with no measurement is `None`. Means are taken over observed days only, and
coverage travels with every window.

**Why.** This is the decision most likely to have produced a wrong answer. Zero-filling two
unworn nights in a 7-day window would report roughly a 29% sleep decrease that never happened —
and it would look entirely plausible on screen. The failure mode is silent, which is what makes
it dangerous.

A recorded zero-step day is the opposite case: that is a real measurement and is kept. The
distinction is between "we measured nothing" and "we measured nothing happening".

**Consequence.** Coverage had to become part of the output rather than an implementation detail,
which is why it appears on the metric card as well as in the evidence view. A mean over 4 of 7
days should carry its caveat wherever it is shown.

---

## 5. The window is anchored on the last day with data

**Decision.** The recent window ends on the most recent day any metric has data for, not on today.

**Why.** Devices sync late. Anchoring on today means a device that last synced two days ago
contributes two empty days to the recent window, which reads as a decline in whatever is being
measured. The bug would appear and disappear depending on when the page was loaded.

**Cost.** "Recent" can mean a window ending several days ago, so the UI reports the anchor date
and separates "most recent data" from "last updated". Those are different facts and conflating
them would let a freshly computed page imply freshly measured data.

---

## 6. An ordered fallback chain for resting heart rate

**Decision.** `hr_resting` → `hr_lowest` → `hr_average` → the daily activity rollup's
`resting_bpm`. The field used is recorded per day and reported in the evidence.

**Why.** Junction normalises across 300+ devices, but normalisation is about shape, not coverage:
a Fitbit night and an Oura night do not populate the same fields. Requiring `hr_resting` would
have dropped real nights; blending the fields silently would have produced a number with no
defined meaning. `hr_average` includes waking movement and reads high, so it is used last and
always labelled.

**Consequence.** `derivations` became part of the API contract. On the generated patient the
evidence view reads `hr_resting (22d), hr_lowest (4d)` — the reader can see the substitution
rather than having to trust it.

---

## 7. Direction is never colour-coded

**Decision.** No red for a decrease, no green for an increase. Every verdict uses the same
neutral ink; the single accent colour is reserved for "worth reviewing".

**Why.** Red means bad. Colouring "sleep down 18%" red asserts that the change is harmful, which
a 10% threshold cannot support — and the same palette would have to colour a *lower* resting
heart rate green, which is a clinical claim in the other direction. Direction is carried by an
arrow, which states what happened without grading it.

**Cost.** A less immediately punchy screen. That is the correct trade for a prototype that must
not imply a diagnosis.

---

## 8. All wording in one module, tested

**Decision.** Insight phrasing lives in `app/domain/narrative.py`, and a test asserts the
generated sentences contain none of a list of clinical or advisory terms.

**Why.** "Not a diagnostic tool" is easy to state in a README and easy to undermine one helpful
sentence at a time. Keeping the language in one place makes it reviewable; asserting on it makes
the intent something CI enforces rather than a convention that quietly erodes.

---

## 9. `/api/pulse` is one call

**Decision.** The dashboard is served by a single endpoint returning metrics, headline, evidence
and trends together, rather than one endpoint per card.

**Why.** The figures and the evidence explaining them must come from one computation. Fetching
them separately would let the headline and its justification be computed from different snapshots
and quietly disagree. Per-metric endpoints exist as well, for inspection, but the UI uses the
single call.

**Cost.** A larger payload than strictly needed. At this size, irrelevant.

---

## 10. Response schemas separate from domain types

**Decision.** `app/api/schemas.py` translates domain dataclasses into pydantic wire models rather
than serialising the domain directly.

**Why.** The domain should be free to change shape. The wire format is a contract the frontend is
typed against. With a translation layer, a domain refactor breaks one obvious file; without one,
it breaks the UI silently at runtime.

**Cost.** Some duplication between the two representations, which is the point.

---

## 11. Fail loudly when misconfigured

**Decision.** In `live` mode, a missing key or user id raises `ConfigurationError` rather than
falling back to fixtures. Only `auto` mode falls back.

**Why.** Silently serving simulated numbers to someone who believes they are looking at Junction
data is the worst available outcome. The fallback is useful for a first run, so it is kept — but
it has to be the mode you are in by default, not something that can happen without your knowing.

Relatedly, generated data is never labelled "via Junction". `SourceDescriptor` renders it as
"Simulated Fitbit data", and the patient's connection status reads "Demo data" rather than
"Connected".

---

## 12. What running against the live sandbox changed

The prototype was built against Junction's documented schema with a local
generator standing in for the sandbox. Pointing it at a real EU sandbox key
afterwards changed three things, which is the argument for doing it rather than
stopping at a green test suite.

**`short_sleep` does not mean "nap".** Fitbit's demo data returns sessions of
6.5-8.5 hours under that label. It was in the nap-exclusion set, so the evidence
view reported "nap sessions only" for half the patient's nights, and any date
carrying both a `long_sleep` and a `short_sleep` record would have dropped the
latter from the nightly total in silence. Naps are now decided by duration,
because the label's meaning varies by provider. Four regression tests came from
this one observation.

**`hr_resting` is never populated.** It is null on every Fitbit sleep record,
and the daily activity rollup's `heart_rate` object is null on all thirty
activity records. Resting heart rate exists in this app only because of the
fallback to `hr_lowest`. The chain was written defensively from the schema;
live data turned it into the thing holding the metric up.

**Coverage is genuinely sparse, and the guard fired.** The sandbox backfills
thirty days of activity but only eleven nights of sleep — 3 of the last 7 days,
7 of the 21 baseline days. Sleep and resting heart rate therefore report "not
enough data" rather than a percentage, while activity computes normally. That
is the correct answer, and it is worth more than a tidy screen: a 33% baseline
should not produce a confident comparison. It is also the one result that could
not have been faked, since the generated patient was built with enough coverage
to pass.

**The headline was overclaiming.** With nothing above threshold it read "every
tracked metric is within 10% of its baseline" — but two of the three had too
few recorded days to compare at all, so the sentence asserted a comparison that
had not happened. It now names what it could not assess. This is the failure
this project was specifically meant to avoid, and it survived until real data
produced the combination that exposed it.

**Isolated measurements were invisible.** The chart drew a line with no point
markers, so a day whose neighbours are missing had no segment to appear in.
Five of the eleven recorded nights were isolated, so roughly a third of the
real data was not being displayed at all.

**And the two summary reads were sequential.** Having something real to measure
showed a request costing the sum of both round trips rather than the longer of
them, about 240ms against 135ms. They are independent, so they now run
concurrently.

Two smaller notes. Junction returns sleep records newest-first; nothing here
depends on order, because series are keyed by calendar date and then densified.
And an `sk_eu_` key against the US host returns 401 "invalid token" — identical
to the error for a bad key, which makes a region mismatch easy to misdiagnose.
