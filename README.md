<p align="center">
  <a href="https://roxyapi.com">
    <img src="https://raw.githubusercontent.com/RoxyAPI/astrology-api-benchmark/main/assets/hero.png" alt="Open accuracy benchmark for any astrology API. Public dataset, runnable Python, verified against NASA JPL Horizons DE441." width="100%">
  </a>
</p>

# Astrology API Accuracy Benchmark

> **Median deviation 1.5 arcseconds (0.0004 degrees) across 210 planet positions and 21 birth charts vs NASA JPL Horizons. Maximum deviation 16.6 arcseconds (0.0046 degrees).** All 210 reference points within tolerance. See the [latest run](#latest-run) below, and [run history](#run-history) for how that compares to the first published run.

Reproducible accuracy benchmark for any astrology API. Open dataset of birth charts, runnable Python, deviation measured per planet against NASA JPL Horizons DE441.

[![Free trial key](https://img.shields.io/badge/Free_Trial_Key-Request-14b8a6?style=for-the-badge&logo=key&logoColor=white)](https://roxyapi.com/contact)
[![API Sandbox](https://img.shields.io/badge/API_Sandbox-Try_Live-22c55e?style=for-the-badge&logo=swagger&logoColor=white)](https://roxyapi.com/api-reference)
[![Methodology](https://img.shields.io/badge/Methodology-NASA_JPL_verified-f59e0b?style=for-the-badge&logo=nasa&logoColor=white)](https://roxyapi.com/methodology)
[![More starters](https://img.shields.io/badge/More_Starters-RoxyAPI-ec4899?style=for-the-badge&logo=github&logoColor=white)](https://roxyapi.com/starters)
[![License](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)

## Why this exists

Astrology APIs make accuracy claims, but almost none publish a reproducible benchmark. The reader is asked to trust a methodology page or a tolerance number with no way to verify it. This repo flips that: a public dataset of chart inputs, expected planet longitudes pulled directly from [NASA JPL Horizons](https://ssd.jpl.nasa.gov/horizons/) (the authoritative ephemeris reference for solar system bodies), and a Python script that anyone can run against any astrology API to see the actual deviation.

It is also vendor-agnostic. The default target is RoxyAPI, but swapping `--base-url` and `--natal-path` points the same script at any HTTP API that returns planet longitudes for a natal chart.

## Quick start

```bash
git clone https://github.com/RoxyAPI/astrology-api-benchmark.git
cd astrology-api-benchmark

export API_KEY=your_roxyapi_key   # https://roxyapi.com/contact for a free test key

python3 benchmark.py
```

Two ways to test free:

- [roxyapi.com/api-reference](https://roxyapi.com/api-reference) lets you test the API live in the browser sandbox without signing up.
- [roxyapi.com/contact](https://roxyapi.com/contact) accepts free test key requests.

The benchmark script uses Python 3 standard library only, no `pip install` required.

## What this benchmark validates

This benchmark validates two specific layers of any astrology API.

**1. Timezone conversion layer.** Given a local birth time and a decimal timezone offset, does the API resolve the same UTC moment that NASA JPL Horizons resolves? Wrong timezone math is the most common silent failure in astrology APIs, and it produces wrong planet positions even when the underlying ephemeris is correct.

**2. Ephemeris layer.** For the correct UTC moment, does the API compute geocentric ecliptic planet longitudes that match NASA JPL Horizons DE441, the authoritative reference for solar system body positions?

### How the test runs

For every chart in `charts.csv`:

1. Read the local birth time, latitude, longitude, and decimal timezone offset.
2. Convert local time plus offset to a UTC moment using standard datetime math.
3. Query NASA JPL Horizons for the geocentric ecliptic longitude of each body at that UTC moment. These are the reference values written to `expected.csv`.
4. POST the original local-time inputs to the target astrology API. The API performs its own timezone conversion and ephemeris computation.
5. Compare the API output to the JPL reference for each body. Compute the angular deviation in arcseconds and degrees, with 0/360 wraparound handled correctly.

### Worked example: Obama natal chart

| Step | Value |
|------|-------|
| Local birth | 1961-08-04 19:24:00, Honolulu HI, timezone -10 |
| UTC moment | 1961-08-05 05:24:00 UTC |
| JPL Horizons Sun longitude | 132.5479 degrees (Leo 12.5479) |
| RoxyAPI Sun longitude | 132.5477 degrees |
| Deviation | 0.86 arcseconds (0.0002 degrees), within the 0.01 degree tolerance |

### Tolerance bands

| Body | Tolerance | Why |
|------|-----------|-----|
| Sun, Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune, Pluto | 0.01° (36 arcsec) | Roughly 2x headroom over the tightest observed run. Wide enough for the legitimate arcsecond-level disagreement between two good ephemeris implementations, tight enough to fail an API using a geometric rather than an apparent ephemeris |
| Moon | 0.02° (72 arcsec) | The Moon moves about 13°/day, so this absorbs a couple of minutes of birth-time interpretation. Still 20x the observed maximum |

**These bands are a vendor-neutral pass bar, not a regression guard.** Tightened 2026-07-30 from 0.05° and 0.20°. They are deliberately NOT set to any one implementation's measured worst case: a band sized to one engine is a bar only that engine clears, which would make a benchmark that invites you to point it at a competitor dishonest. The bar catches the class of defect that matters, wrong timezone resolution, a geometric ephemeris, a wrong-epoch element set. For regressions, read the per-body table in the latest run: a body drifting from 1 to 20 arcseconds still passes a 36 arcsecond bar.

### What this benchmark does not validate

The benchmark tests the foundational planet-position layer. It deliberately does not validate:

- **House cusps** (Placidus, Koch, Whole Sign, Equal). Observer-frame angles computed from sidereal time and obliquity, not body positions. JPL does not publish them.
- **Ascendant and Midheaven.** Same reason as house cusps. Sensitive to exact birth-time precision.
- **Ayanamsa and sidereal zodiac.** Domain-specific transforms applied above the planet layer.
- **Aspects, dashas, doshas, interpretations.** Derived calculations layered above raw positions.

Validation for those layers lives in the broader RoxyAPI test suite documented at [roxyapi.com/methodology](https://roxyapi.com/methodology), verified against domain-specific authorities.

### Why the chart names matter

JPL Horizons does not know who anyone is. Feed it `(date, time, latitude, longitude, timezone)`, it returns geocentric ecliptic longitudes. The chart label is human metadata. We use named AA-rated celebrity charts so any reader can cross-check our birth-time inputs against the same [astro-databank](https://www.astro.com/astro-databank) entries we sourced them from. If our chart inputs disagree with the public record, our credibility falls regardless of internal mathematical consistency.

The synthetic edge-case charts (DST transitions, polar latitudes, pre-1900 dates, half-hour offsets, calendar-skip days) are explicitly labeled as test fixtures designed to exercise specific timezone-handling conditions. Their value is coverage, not celebrity provenance.

### Reference dataset

Reference values are pulled from [NASA JPL Horizons DE441](https://ssd.jpl.nasa.gov/horizons/) for 21 charts: 8 named celebrity charts plus 13 synthetic edge-case scenarios. Rodden Ratings cite the [astro-databank](https://www.astro.com/astro-databank) data-quality system.

| Chart | Birth | Rodden |
|-------|-------|--------|
| Barack Obama | Aug 4, 1961, 7:24 PM, Honolulu HI | AA |
| Beyonce Knowles | Sep 4, 1981, 9:47 PM, Houston TX | AA |
| Albert Einstein | Mar 14, 1879, 11:30 AM, Ulm Germany (LMT) | AA |
| Marilyn Monroe | Jun 1, 1926, 9:30 AM, Los Angeles CA | AA |
| Steve Jobs | Feb 24, 1955, 7:15 PM, San Francisco CA | AA |
| Princess Diana | Jul 1, 1961, 7:45 PM, Sandringham UK | A |
| John F Kennedy | May 29, 1917, 3:00 PM, Brookline MA | A |
| Elon Musk | Jun 28, 1971, 7:30 AM, Pretoria South Africa | B |

Plus 13 synthetic charts covering Reykjavik (64°N), Tromsø (70°N), Anchorage (61°N), Ushuaia (-55°S), Sydney AEDT, Tokyo JST, Mumbai IST half-hour offset, Quito on the equator, New York DST spring-forward + fall-back, Boston 1900 pre-WW1 era, Greenwich Y2K rollover, Samoa post-2011 calendar skip.

That is 210 reference points (10 planets × 21 charts). Adding more charts is one-line work in `charts.csv` plus a re-run of `regenerate_expected.py` against JPL Horizons. See [Adding charts](#adding-charts) below.

## Latest run

<!-- BENCHMARK:BEGIN - generated by benchmark.py --update-readme, do not hand-edit -->

**Run 2026-07-30.** 210 reference points, 210 within tolerance.

| Metric | Arcseconds | Degrees |
|--------|-----------:|--------:|
| Median | 1.48 | 0.0004 |
| Mean | 2.74 | 0.0008 |
| p95 | 11.20 | 0.0031 |
| Max | 16.55 | 0.0046 |

Per-body maximum across all charts. **Read this table, not just the pass count:** the pass
bar is a vendor-neutral floor, so a single body drifting well above its usual value can still
pass. Per-body is where a regression shows up first.

| Body | Max deviation | Worst-case chart |
|------|--------------:|------------------|
| Neptune | 16.55 arcsec | Sydney AEDT summer |
| Uranus | 11.42 arcsec | Tromso midnight sun |
| Saturn | 9.35 arcsec | Boston year 1900 |
| Mars | 6.21 arcsec | Elon Musk |
| Jupiter | 6.03 arcsec | Quito autumn equinox |
| Pluto | 5.61 arcsec | Albert Einstein |
| Mercury | 5.40 arcsec | Quito autumn equinox |
| Moon | 3.30 arcsec | Boston year 1900 |
| Venus | 2.22 arcsec | Steve Jobs |
| Sun | 0.94 arcsec | Sydney AEDT summer |

<!-- BENCHMARK:END -->

The committed [`results.csv`](results.csv) is the snapshot from this run, one row per reference point.

Highlights:

- **Every one of the 210 points is inside 17 arcseconds**, across charts spanning 1879 to 2011, six continents, both hemispheres, the equator, three high-latitude locations above 60 degrees, half-hour timezone offsets, two DST edge cases, the Samoa 2011 calendar skip, and the Y2K rollover.
- **The Sun and the Moon are the tightest bodies.** The Moon result is the direct evidence that the timezone-conversion layer is correct: it moves about 13 degrees per day, so any drift in the resolved UTC moment would show up here first, and it does not.
- **The residual is concentrated in the two slowest outer planets.** Neptune and Uranus are the whole top of the table. Drop them and the max across the other eight bodies is 9.35 arcsec. Both are far below anything that could move a body into a different sign.
- **Pre-1900 charts** (Einstein 1879 on LMT, Boston 1900), **DST edge cases** (New York 2005 spring-forward into the non-existent 0230 hour, fall-back into the ambiguous 0130 hour) and **high-latitude charts** (Reykjavik 64N, Tromso 70N, Anchorage 61N, Ushuaia 55S) are all inside 17 arcseconds.
- The remaining deviation is the arcsecond-level difference between DE441 and an analytical ephemeris, not a methodology gap. Numbers reproduce on every run within the precision JPL Horizons publishes, which is 4 decimal degrees, or about 0.36 arcseconds. **That 0.36 arcseconds is this benchmark's resolution floor**, so treat anything below roughly 1 arcsecond as at-the-floor rather than as a meaningful difference.

Reproduce it with your own key, and keep the block above honest at the same time:

```bash
python3 benchmark.py --update-readme
```

## Run history

Every run this repo has published, oldest first. Kept deliberately: a benchmark that silently replaces its numbers gives you no way to tell a real improvement from a quiet re-tune. Dataset and script are the same across all rows, so they are directly comparable.

| Run | Median | Max | Pass | Notes |
|-----|-------:|----:|------|-------|
| 2026-04-28 | 16.0 arcsec | 32.4 arcsec | 210 / 210 | First published run. Tolerance bands were 0.05 deg planets, 0.20 deg Moon. |
| 2026-07-30 | 1.48 arcsec | 16.55 arcsec | 210 / 210 | Accuracy update to the positions engine deployed 2026-07-29. Median improved about 11x, max about 2x. Tolerance bands tightened to 0.01 deg planets, 0.02 deg Moon. |

Per-body change across those two runs. The 2026-04-28 column is the arcminute figure published at the time multiplied by 60, so it inherits that rounding (the second decimal of an arcminute is 0.6 arcseconds):

| Body | Max, 2026-04-28 | Max, 2026-07-30 |
|------|----------------:|----------------:|
| Neptune | 32.4 arcsec | 16.55 arcsec |
| Saturn | 29.4 arcsec | 9.35 arcsec |
| Jupiter | 25.2 arcsec | 6.03 arcsec |
| Uranus | 24.6 arcsec | 11.42 arcsec |
| Mars | 24.6 arcsec | 6.21 arcsec |
| Mercury | 22.8 arcsec | 5.40 arcsec |
| Pluto | 22.2 arcsec | 5.61 arcsec |
| Sun | 21.6 arcsec | 0.94 arcsec |
| Venus | 21.0 arcsec | 2.22 arcsec |
| Moon | 3.0 arcsec | 3.30 arcsec |

Every body improved except the Moon, which was already at the resolution floor and stayed there (3.0 to 3.30 arcseconds is within one 0.36 arcsecond quantization step, so the two are the same measurement). All 210 points were inside tolerance on both runs, so this is a precision improvement rather than a correctness one: no chart changed a sign, and none was ever outside the published band.

## Run against a different API

The script speaks plain HTTP. Anything that accepts `{ date, time, latitude, longitude, timezone }` as JSON and returns a `{ planets: [{ name, sign, degree | longitude }] }` shape will work.

```bash
python3 benchmark.py \
  --base-url https://example-api.com/api \
  --natal-path /astrology/natal-chart
```

If the response shape differs, adapt `extract_body_longitude` in `benchmark.py`. The function is 25 lines and the only place that knows about response structure.

## Adding charts

Two steps per chart:

1. Append a row to `charts.csv` with `chart_id,name,date,time,latitude,longitude,timezone,rodden_rating,description`. Use AA-rated birth data (timed and verified) when possible. C-rated and lower data is too noisy for accuracy benchmarks.
2. Run `python3 regenerate_expected.py`. It queries JPL Horizons for every body at the exact moment of every chart and rewrites `expected.csv`.

The regeneration script is rate-limited at 1 query/second to stay courteous to the JPL Horizons API. 10 bodies per chart, so a fresh chart adds about 10 seconds of regeneration time.

```bash
python3 regenerate_expected.py
```

Roadmap for the dataset itself:

- DST boundary births (spring forward, fall back, both ambiguous and non-existent times)
- Pre-1970 dates (LMT and colonial offset edge cases)
- High and polar latitudes (above 66° N/S, where Placidus degenerates)
- Southern hemisphere births
- Vedic / sidereal extension (separate `expected-vedic.csv` referenced against [DrikPanchang](https://www.drikpanchang.com))

PRs that grow the dataset along any of these axes are welcome.

## How this fits with RoxyAPI

This is the reproducible companion to the [828 gold-standard tests methodology](https://roxyapi.com/blogs/how-we-test-astrology-api-accuracy-828-gold-standard-tests) and the [/methodology](https://roxyapi.com/methodology) page. The methodology page describes how RoxyAPI verifies its own calculations. This repo turns that into something anyone can run, fork, extend, or point at a different API.

RoxyAPI gives you natal charts, kundli, daily horoscopes, tarot, numerology, human design, forecast, biorhythm, I Ching, crystals, dreams, and angel numbers behind one API key. Verified against NASA JPL Horizons. Try the [API sandbox](https://roxyapi.com/api-reference) without signing up, request a [free trial key](https://roxyapi.com/contact), or see [pricing](https://roxyapi.com/pricing).

## Contributing

PRs welcome for:

- Additional AA-rated chart fixtures (with adversarial coverage from the roadmap above)
- Vedic / sidereal extension (separate `expected-vedic.csv` against DrikPanchang)
- Adapters for response shapes other than the default
- Visualization scripts (deviation histograms, per-body box plots)

## License

[MIT](LICENSE). Birth data is publicly known. Reference values are pulled from JPL Horizons DE441 and cited per row in `expected.csv`.
