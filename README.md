# Initiative Erzabt-Klotz-Straße

A static website about the traffic situation on Erzabt-Klotz-Straße in
Salzburg-Nonntal: 234 metres of near-straight carriageway with a 50 km/h limit,
280 metres without a secured crossing, in the middle of seven schools and two
kindergartens. A long-standing situation, measured out.

The site itself is in German, because its audience and its addressee are. The
code, the comments, the data keys and the IDs that scripts and styles hook into
are in English. The anchor fragments stay German (`#inhalt`, `#mitmachen`,
`#massnahmen`): they show up in the address bar and in shared links, so they
belong to the page, not to the code.

No build step, no dependencies, no trackers, no data collection. Opening
`index.html` in a browser is enough.

## Publishing

Put the whole folder on any webspace: GitHub Pages, Netlify, Uberspace, any
hosting plan. There is nothing to compile.

```bash
# view locally
python3 -m http.server 8000
# -> http://localhost:8000
```

Still to do before publishing under its own domain:

- [x] **Impressum** under § 25 MedienG: name, place of residence, subject and
      editorial direction are in the footer
- [ ] **E-mail addresses** in the "Mitmachen" section need checking
      (researched November 2026)

Separately, and to be sent **once** by **one** person: `data/ifg-request.md`, a
freedom-of-information request to the City of Salzburg under the
Informationsfreiheitsgesetz. It asks for the traffic volumes, speed and noise
data the site currently lacks. Four-week deadline.

## Layout

```
index.html              the page; edit the German copy here
assets/
  style.css             layout and typography (hand-written)
  app.js                legend, light/dark, e-mail draft (hand-written)
  palette.css           <- generated: colours, shared with the figures
  figures.js            <- generated: every figure as a JS string
  figure-*.svg          <- generated: the same figures standalone
media/                  photos for the letter, the press and a notice board
                        (not embedded in the website)
data/
  build.py              generates the figures and the measurements
  bundle.py             packs everything into a single HTML file
  ifg-request.md        information request to the city (send once)
  osm.json, poi.json    raw OpenStreetMap data
  overpass-*.ql         the queries that fetched it
  measurements.json     <- generated: every number on the page, checkable
single-page.html        <- generated: the whole page as one file
```

Do not hand-edit the files marked <-, they get overwritten.

### One file to pass around

```bash
python3 data/bundle.py
```

Writes `single-page.html`, the complete page including every figure in a single
file (about 110 kB). Useful as an e-mail attachment, for archiving, or as an
enclosure to a submission. Opens on a double click, no server needed.

## Regenerating the figures

```bash
python3 data/build.py
```

Needs nothing but the standard library. The script computes every length,
angle and stopping distance from the OSM geometry and writes them to
`data/measurements.json` at the same time, so every number on the page can be
traced back.

Updating the raw data (only needed when something changes on the ground):

```bash
# street network            -> data/osm.json
# schools, kindergartens... -> data/poi.json  (overpass-poi.ql)
curl -X POST https://overpass-api.de/api/interpreter \
  -H "User-Agent: initiative-erzabt-klotz-strasse/1.0" \
  --data-binary @data/overpass-network.ql -o data/osm.json
```

The public Overpass server occasionally answers "502 at capacity"; wait a
moment and retry. Check the response is valid JSON before overwriting.

## Key figures

Current values from `data/measurements.json` (OSM state 2026-10-30).

| Quantity | Value | Source |
|---|---:|---|
| Section, signal to curve | 291.0 m | OSM geometry |
| of which near-straight | 233.9 m | bearing spread ±4.6° |
| Curve into Nonntaler Hauptstraße | 74.4° | OSM geometry |
| Speed limit | 50 km/h | `maxspeed` |
| Cross section | 2 lanes + bus lane | `lanes=3`, one of them a bus lane |
| Offset between the two bus stops | 0.0 m | surveyed on site, they face each other |
| Beyond the only crossing | 280.0 m | OSM geometry |
| Bus stop to the nearest crossing | 123 m | OSM geometry |
| Stopping distance 30 / 50 / 60 km/h | 13 / 26 / 34 m | 1.0 s reaction, 8 m/s² |
| Schools for children within 600 m | 7 | OSM, deduplicated |
| Kindergartens within 600 m | 2 | OSM, deduplicated |
| Nearest facility for children | 124 m | OSM geometry |

## Reusing the figures

The three SVG files in `assets/` stand on their own and carry their own
legend, so they can be dropped straight into letters to the authority, press
enquiries or a notice board. They adapt to light and dark viewing.

## Licence and provenance

Geodata © OpenStreetMap contributors,
[ODbL](https://www.openstreetmap.org/copyright). Carry this notice when reusing
the maps; it is already printed in every figure.

This is a private residents' initiative. It is not an offering of the City of
Salzburg and is not affiliated with any political party.
