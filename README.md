<p align="center">
  <a href="https://roxyapi.com">
    <img src="https://raw.githubusercontent.com/RoxyAPI/astrology-api-benchmark/main/assets/hero.png" alt="Open accuracy benchmark for any astrology API. Public dataset, runnable Python, verified against NASA JPL Horizons DE441." width="100%">
  </a>
</p>

# Astrology API Accuracy Benchmark

> **Median deviation 0.27 arcmin (16 arcseconds) across 210 planet positions and 21 birth charts vs NASA JPL Horizons. Maximum deviation 0.54 arcmin.** All 210 reference points within tolerance. See the [baseline run](#baseline-run-2026-04-28) below.

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
5. Compare the API output to the JPL reference for each body. Compute the angular deviation in degrees and arcminutes, with 0/360 wraparound handled correctly.

### Worked example: Obama natal chart

| Step | Value |
|------|-------|
| Local birth | 1961-08-04 19:24:00, Honolulu HI, timezone -10 |
| UTC moment | 1961-08-05 05:24:00 UTC |
| JPL Horizons Sun longitude | 132.5479 degrees (Leo 12.5479) |
| RoxyAPI Sun longitude | 132.5533 degrees |
| Deviation | 0.0054 degrees (0.32 arcmin), within the 0.05 degree tolerance |

### Tolerance bands

| Body | Tolerance | Why |
|------|-----------|-----|
| Sun, Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune, Pluto | 0.05° (3 arcmin) | DE441 is the modern authoritative ephemeris; production APIs land an order of magnitude tighter |
| Moon | 0.20° (12 arcmin) | Moon moves about 13°/day; small input timing differences amplify |

### What this benchmark does not validate

The benchmark tests the foundational planet-position layer. It deliberately does not validate:

- **House cusps** (Placidus, Koch, Whole Sign, Equal). Observer-frame angles computed from sidereal time and obliquity, not body positions. JPL does not publish them.
- **Ascendant and Midheaven.** Same reason as house cusps. Sensitive to exact birth-time precision.
- **Ayanamsa and sidereal zodiac.** Domain-specific transforms applied above the planet layer.
- **Aspects, dashas, doshas, interpretations.** Derived calculations layered above raw positions.

Validation for those layers lives in the broader RoxyAPI test suite documented at [roxyapi.com/methodology](https://roxyapi.com/methodology), verified against domain-specific authorities like [DrikPanchang](https://www.drikpanchang.com), onlinejyotish.com, and timeanddate.com.

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

## Baseline run (2026-04-28)

```
fetched obama (Barack Obama)
fetched beyonce (Beyonce Knowles)
fetched diana (Princess Diana)
fetched einstein (Albert Einstein)
fetched jobs (Steve Jobs)
fetched musk (Elon Musk)
fetched monroe (Marilyn Monroe)
fetched jfk (John F Kennedy)
fetched reykjavik_summer (Reykjavik summer solstice)
fetched ushuaia_winter (Ushuaia winter solstice)
fetched quito_equinox (Quito autumn equinox)
fetched ny_dst_spring (New York DST spring-forward)
fetched ny_dst_fall (New York DST fall-back)
fetched tromso_midnight_sun (Tromso midnight sun)
fetched mumbai_2000 (Mumbai canonical IST)
fetched sydney_2010 (Sydney AEDT summer)
fetched tokyo_1990 (Tokyo JST)
fetched boston_1900 (Boston year 1900)
fetched greenwich_y2k (Greenwich Y2K rollover)
fetched samoa_skipped_day (Samoa post calendar skip)
fetched anchorage_winter (Anchorage winter solstice)

Total reference points : 210
Within tolerance       : 210
Outside tolerance      : 0
Missing in API response: 0

Mean deviation : 0.0041 deg (0.25 arcmin)
Median         : 0.0046 deg (0.27 arcmin)
Max            : 0.0090 deg (0.54 arcmin)
p95            : 0.0068 deg (0.41 arcmin)

Detailed results written to results.csv
```

The committed [`results.csv`](results.csv) is the snapshot from this run. Per-body max deviation across all 21 charts:

| Body | Max deviation | Worst-case chart |
|------|--------------:|------------------|
| Neptune | 0.54 arcmin | Musk |
| Saturn | 0.49 arcmin | Boston 1900 |
| Jupiter | 0.42 arcmin | NY DST spring-forward |
| Uranus | 0.41 arcmin | Reykjavik summer |
| Mars | 0.41 arcmin | NY DST fall-back |
| Mercury | 0.38 arcmin | Monroe |
| Pluto | 0.37 arcmin | Boston 1900 |
| Sun | 0.36 arcmin | Sydney 2010 |
| Venus | 0.35 arcmin | Anchorage winter |
| **Moon** | **0.05 arcmin (3 arcseconds)** | Boston 1900 |

Highlights:

- **All 210 points sub-arcminute against JPL Horizons** across charts spanning 1879 to 2011, six continents, both hemispheres, equator, three high-latitude locations above 60°, half-hour timezone offsets, two DST edge cases, the Samoa 2011 calendar skip, and the Y2K rollover.
- **Moon at 0.05 arcmin max (3 arcseconds)** is the tightest in the catalog, surprising for a body that moves about 13 degrees per day. This is direct evidence that the timezone-conversion layer is correct: any small UTC-moment drift would amplify into Moon-position drift, and we are not seeing that.
- **Pre-1900 charts** (Einstein 1879 with LMT timezone, Boston 1900) all sub-arcminute. Validates correct LMT decimal-offset handling.
- **DST edge cases** (NY 2005 spring-forward 0230 non-existent hour, NY 2005 fall-back 0130 ambiguous hour) all sub-arcminute.
- **High-latitude charts** (Reykjavik 64°N, Tromsø 70°N, Anchorage 61°N, Ushuaia -55°S) all sub-arcminute.
- The deviation is driven by DE441 vs analytical-ephemeris arcsecond-level differences, not by methodology gaps. Numbers reproduce on every run within the precision JPL Horizons publishes.

Run `python3 benchmark.py` against your own key to regenerate `results.csv`.

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

RoxyAPI gives you natal charts, kundli, daily horoscopes, tarot, numerology, biorhythm, I Ching, crystals, dreams, and angel numbers behind one API key. Verified against NASA JPL Horizons. Try the [API sandbox](https://roxyapi.com/api-reference) without signing up, request a [free trial key](https://roxyapi.com/contact), or see [pricing](https://roxyapi.com/pricing).

## Contributing

PRs welcome for:

- Additional AA-rated chart fixtures (with adversarial coverage from the roadmap above)
- Vedic / sidereal extension (separate `expected-vedic.csv` against DrikPanchang)
- Adapters for response shapes other than the default
- Visualization scripts (deviation histograms, per-body box plots)

## License

[MIT](LICENSE). Birth data is publicly known. Reference values are pulled from JPL Horizons DE441 and cited per row in `expected.csv`.
