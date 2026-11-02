#!/usr/bin/env python3
"""
Builds every figure and every published number of the website from the raw
OpenStreetMap data in data/osm.json and data/poi.json.

    python3 data/build.py

Output:
    assets/figures.js             All SVGs as JS strings (injected into the DOM
                                  so they follow the colour scheme and stay
                                  interactive)
    assets/figure-*.svg           The same SVGs standalone (noscript fallback,
                                  and for pasting into letters to the authority)
    data/measurements.json        Every computed number, open to checking

All lengths are computed from the OSM geometry, never estimated.
Source: OpenStreetMap contributors, ODbL. Queries in data/overpass-*.ql
"""

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")

# ------------------------------------------------------------------ Geodesy ---
R = 111320.0  # m per degree of latitude


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return json.load(fh)


def metres(a, b):
    """Distance in metres between two (lat, lon) pairs."""
    la = (a[0] + b[0]) / 2 * math.pi / 180
    return math.hypot((b[0] - a[0]) * R, (b[1] - a[1]) * R * math.cos(la))


osm = load("osm.json")
poi = load("poi.json")

ways = {e["id"]: e for e in osm["elements"] if e["type"] == "way"}
nodes = {e["id"]: e for e in osm["elements"] if e["type"] == "node"}

coord = {}
for w in ways.values():
    for nid, g in zip(w.get("nodes", []), w.get("geometry", []) or []):
        if g:
            coord[nid] = (g["lat"], g["lon"])
for n in nodes.values():
    coord[n["id"]] = (n["lat"], n["lon"])

# ----------------------------------------------------- Assemble the corridor ---
# The OSM ways in order, from the signalised junction Petersbrunnstrasse/
# Akademiestrasse (north-east) into the curve towards Nonntaler Hauptstrasse
# (south-west). The way IDs come from the Overpass query and are stable.
# The corridor follows the continuous state road L 104. At its south-western
# end that road turns south into Nonntaler Hauptstrasse; the western arm of
# Erzabt-Klotz-Strasse (way 22604725, no ref tag) is a minor side street and
# not part of the through route.
CORRIDOR_WAYS = [25353604, 134631796, 1164458568, 134631797, 314950230, 265570933]
N_CORRIDOR_END = 200577881  # unmarked crossing at the end of the curve
N_SIGNAL = 151015615  # junction Petersbrunnstr./Akademiestr., traffic signals
N_WAESCHERGASSE = 1480008790  # mouth of Waeschergasse
N_PEREGRIN = 151015616  # mouth of Peregrinstrasse, where the straight begins
N_CURVE = 151015618  # 47 degree bend into Nonntaler Hauptstrasse
N_END = 996569534  # second junction on Nonntaler Hauptstrasse

path = []
cur = N_SIGNAL
for wid in CORRIDOR_WAYS:
    nl = list(ways[wid]["nodes"])
    if nl[0] != cur:
        nl.reverse()
    assert nl[0] == cur, f"way {wid} does not join node {cur}"
    path += nl if not path else nl[1:]
    cur = nl[-1]

if N_CORRIDOR_END in path:
    path = path[: path.index(N_CORRIDOR_END) + 1]

pts = [coord[n] for n in path]
chain = [0.0]
for i in range(len(pts) - 1):
    chain.append(chain[-1] + metres(pts[i], pts[i + 1]))
CORRIDOR_LEN = chain[-1]

LAT0 = pts[0][0]
KX = R * math.cos(LAT0 * math.pi / 180)  # m per degree of longitude here


def en(p):
    """(lat, lon) -> local metre coordinates (east, north) from the start point."""
    return ((p[1] - pts[0][1]) * KX, (p[0] - pts[0][0]) * R)


def bearing(a, b):
    la1, la2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    y = math.sin(dl) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def project_on_corridor(p):
    """Project a point onto the corridor axis.

    Returns (chainage in m, lateral offset in m, sign). A sign below zero
    means the north-western side of the road.
    """
    best = None
    pe, pn = en(p)
    for i in range(len(pts) - 1):
        ae, an = en(pts[i])
        be, bn = en(pts[i + 1])
        de, dn = be - ae, bn - an
        ll = de * de + dn * dn
        if not ll:
            continue
        t = max(0.0, min(1.0, ((pe - ae) * de + (pn - an) * dn) / ll))
        ce, cn = ae + t * de, an + t * dn
        dist = math.hypot(pe - ce, pn - cn)
        cross = de * (pn - an) - dn * (pe - ae)  # >0 = left of travel direction
        side = -1 if cross < 0 else 1
        st = chain[i] + t * math.sqrt(ll)
        if best is None or dist < best[1]:
            best = (st, dist, side)
    return best


# ------------------------------------------- Measure the straight and curve ---
i_per, i_curve = path.index(N_PEREGRIN), path.index(N_CURVE)
bearings = [bearing(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def turn(b1, b2):
    return ((b2 - b1 + 540) % 360) - 180


# The longest run whose bearings spread by at most 6 degrees in total.
# Comparing against the spread rather than against the first segment keeps the
# start of the curve from still passing as "straight".
STRAIGHT_TOLERANCE = 6.0
best_run = (0.0, 0, 0)
for i in range(len(bearings)):
    j = i + 1
    while j < len(bearings):
        window = bearings[i : j + 1]
        spread = max(
            abs(turn(a, b)) for a in window for b in window
        )
        if spread > STRAIGHT_TOLERANCE:
            break
        j += 1
    L = chain[j] - chain[i]
    if L > best_run[0]:
        best_run = (L, i, j)
STRAIGHT_LEN, si, sj = best_run
STRAIGHT_FROM, STRAIGHT_TO = chain[si], chain[sj]
STRAIGHT_SPREAD = max(
    abs(turn(bearings[si], bearings[k])) for k in range(si, sj)
)
# The change of direction is spread over several nodes, so this is an arc and
# not a kink. It is measured from the end of the straight to the corridor end.
CURVE_FROM = STRAIGHT_TO
CURVE_TO = chain[-1]
CURVE_LEN = CURVE_TO - CURVE_FROM
CURVE_ANGLE = abs(turn(bearings[sj - 1], bearings[-1]))
CURVE_RADIUS = (
    CURVE_LEN / math.radians(CURVE_ANGLE) if CURVE_ANGLE > 1 else float("inf")
)

# ------------------------------------------------- Bus stops and crossings ---
# Which platform serves which direction is taken from the OSM route relations
# (lines 5, 9, 25), not guessed:
#   platform 740435514, south-eastern side -> Hauptbahnhof, Itzling, Europark
#   platform 766861724, north-western side -> Groedig, Kommunalfriedhof
STOPS = [
    # (label, stop node, matching waiting area / platform way)
    ("Haltestelle Richtung Zentrum", (47.7918986, 13.0501196), 740435514),
    ("Haltestelle Richtung Süden", (47.7920718, 13.0506442), 766861724),
]
# Position fix: OpenStreetMap places the south-eastern platform some 56 m too
# far south-west (level with no. 29 instead of no. 25). On the ground the two
# platforms face each other, roughly level with no. 25; the side assignment in
# OSM is correct though, the shelter does stand on the north-western side.
# So the chainage of the north-western platform is used for both and the
# south-eastern one is mirrored onto it.
# TODO: fix this in OpenStreetMap, then this block can go.
STOPS_OPPOSITE = True

stops = []
for label, p, platform_way in STOPS:
    g = ways[platform_way]["geometry"]
    centre = (
        sum(q["lat"] for q in g) / len(g),
        sum(q["lon"] for q in g) / len(g),
    )
    st, _, _ = project_on_corridor(p)
    _, off, side = project_on_corridor(centre)
    stops.append(
        {
            "label": label,
            "lat": p[0],
            "lon": p[1],
            "platform_lat": centre[0],
            "platform_lon": centre[1],
            "station": round(st, 1),
            "side": "northwest" if side < 0 else "southeast",
            "side_sign": side,
            "platform_offset_m": round(off, 1),
            "position_source": "OpenStreetMap",
        }
    )

if STOPS_OPPOSITE:
    nw = next(s for s in stops if s["side_sign"] < 0)

    def point_at(station, offset):
        """Point on the axis at 'station', offset sideways, as (lat, lon)."""
        for i in range(len(pts) - 1):
            if chain[i] <= station <= chain[i + 1]:
                f = (station - chain[i]) / max(1e-9, chain[i + 1] - chain[i])
                a, b = en(pts[i]), en(pts[i + 1])
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
                cx, cy = a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])
                nx, ny = -uy, ux  # normal, pointing left of the travel direction
                ex, ny_ = cx + nx * offset, cy + ny * offset
                return (pts[0][0] + ny_ / R, pts[0][1] + ex / KX)
        return pts[-1]

    for s in stops:
        if s["side_sign"] > 0:  # the south-eastern platform gets moved
            s["platform_lat"], s["platform_lon"] = point_at(
                nw["station"], +s["platform_offset_m"]
            )
            s["lat"], s["lon"] = s["platform_lat"], s["platform_lon"]
            s["station"] = nw["station"]
            s["position_source"] = "vor Ort korrigiert (OSM-Lage abweichend)"

STOP_GAP = abs(stops[0]["station"] - stops[1]["station"])
STOP_MID = (stops[0]["station"] + stops[1]["station"]) / 2

# Along the whole section there is exactly one place where Erzabt-Klotz-
# Strasse can be crossed: the pedestrian-demand signal at the junction. The
# zebra crossing at 13.048834 sits on way 138365059, that is on the western arm
# of Erzabt-Klotz-Strasse beyond Nonntaler Hauptstrasse, and does not cross
# this section. Per OSM the crossing at Peregrinstrasse crosses Peregrinstrasse
# (a side street), not the main carriageway.
CROSSINGS = [
    ("Bedarfsampel über die Erzabt-Klotz-Straße", (47.792562, 13.052117), "ampel"),
]
crossings = []
for label, p, kind in CROSSINGS:
    st, _, _ = project_on_corridor(p)
    crossings.append(
        {
            "label": label,
            "kind": kind,
            "lat": p[0],
            "lon": p[1],
            "station": round(st, 1),
        }
    )

for s in stops:
    opts = [(abs(c["station"] - s["station"]), c) for c in crossings]
    opts.sort(key=lambda t: t[0])
    s["distance_to_crossing_m"] = round(opts[0][0], 1)
    s["nearest_crossing"] = opts[0][1]["label"]
    s["detour_m"] = round(2 * opts[0][0], 1)

# --------------------------------------------- Markers for the site plan ---
# Numbered instead of labelled: the legend sits beside the map in the HTML, so
# no texts overlap and the map stays readable on any display.
MARKERS = [
    {
        "num": 1,
        "lat": coord[N_SIGNAL][0],
        "lon": coord[N_SIGNAL][1],
        "color": "danger",
        "short": "Bedarfsampel, die einzige Querung",
        "detail": "Kreuzung Petersbrunnstraße/Akademiestraße. Die Bedarfsampel "
        "über die Erzabt-Klotz-Straße ist die einzige Stelle, an der dieser "
        "Abschnitt überquert werden kann.",
    },
    {
        # The two platforms face each other; at roughly one pixel per metre
        # they could not be drawn separately without overlapping.
        "num": 2,
        "lat": point_at(stops[0]["station"], 0)[0],
        "lon": point_at(stops[0]["station"], 0)[1],
        "color": "transit",
        "short": "Bushaltestellen, hier wird gequert",
        "detail": "Die Steige der Linien 5, 9 und 25 liegen einander gegenüber, "
        "der nordwestliche mit Wartehäuschen. Gequert wird auf dieser Höhe, "
        "über die gesamte Fahrbahn und ohne Übergang.",
    },
    {
        "num": 3,
        "lat": point_at((CURVE_FROM + CURVE_TO) / 2, 0)[0],
        "lon": point_at((CURVE_FROM + CURVE_TO) / 2, 0)[1],
        "color": "danger",
        "short": "Kurve nach Süden",
        "detail": f'Am Ende der Geraden schwenkt die Landesstraße L 104 auf rund '
        f'{CURVE_LEN:.0f} Metern um {CURVE_ANGLE:.0f}° nach Süden in die '
        f'Nonntaler Hauptstraße; der Kurvenradius beträgt etwa '
        f'{CURVE_RADIUS:.0f} Meter. Der westliche Ast der Erzabt-Klotz-Straße '
        f'ist eine Nebenstraße.',
    },
    {
        "num": 4,
        "lat": 47.79290,
        "lon": 13.05385,
        "color": "school",
        "short": "Schulen, Hochschule, Unipark",
        "detail": "Mehrere Bildungseinrichtungen nordöstlich der Kreuzung; "
        "der Weg dorthin führt über diesen Abschnitt.",
    },
]

# -------------------------------------------------------- Stopping distances ---
REACTION_TIME = 1.0  # s, the usual assumption for an attentive driver
DECELERATION = 8.0  # m/s^2, emergency braking on dry asphalt


def stopping_distance(kmh):
    """Reaction distance and braking distance.

    Both parts are rounded first and only then added, so that the sum in the
    figure matches the parts shown. Otherwise the drawing reads
    8.3 + 4.3 = 12.7, and someone checks the arithmetic.
    """
    v = kmh / 3.6
    reaction = round(v * REACTION_TIME, 1)
    braking = round(v * v / (2 * DECELERATION), 1)
    return {
        "kmh": kmh,
        "reaction_distance_m": reaction,
        "braking_distance_m": braking,
        "stopping_distance_m": round(reaction + braking, 1),
    }


SPEEDS = [stopping_distance(k) for k in (30, 50, 60)]
STOP30 = SPEEDS[0]["stopping_distance_m"]


def residual_speed(kmh, distance):
    """Speed after 'distance' metres of emergency braking, in km/h."""
    v = kmh / 3.6
    if distance <= v * REACTION_TIME:
        return kmh  # still reacting, no braking yet
    s = distance - v * REACTION_TIME
    v2 = v * v - 2 * DECELERATION * s
    return round(max(0.0, math.sqrt(max(0.0, v2))) * 3.6, 1)


RESIDUAL_AT_STOP30 = {s["kmh"]: residual_speed(s["kmh"], STOP30) for s in SPEEDS}

# Travel time along the straight
TRAVEL_TIME = {
    k: round(STRAIGHT_LEN / (k / 3.6), 1) for k in (30, 50)
}
TIME_LOST = round(TRAVEL_TIME[30] - TRAVEL_TIME[50], 1)

# --------------------------------------------- Speed limits from OSM tags ---
limits = {}
for wid in CORRIDOR_WAYS:
    t = ways[wid]["tags"]
    limits[wid] = t.get("maxspeed", "–")
CROSS_SECTION = ways[314950230]["tags"]

# -------------------------------------------------- Sensitive destinations ---
# From data/poi.json. The Overpass query reaches generously within 900 m;
# filtering down to the straight-line distance to the section happens here.
# OSM lists large sites more than once, hence the deduplication below.
RADIUS_M = 600
SENSITIVE_KINDS = {
    "school",
    "kindergarten",
    "university",
    "hospital",
    "theatre",
    "playground",
    "rehearsal_studio",
    "arts_centre",
    "music_school",
    "retirement_home",
    "nursing_home",
    "assisted_living",
}


def dist_to_corridor(lat, lon):
    """Straight-line distance to the nearest point of the section."""
    return project_on_corridor((lat, lon))[1]


DESTINATIONS = []
_seen = set()
for e in poi["elements"]:
    t = e.get("tags", {})
    c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
    if not c.get("lat"):
        continue
    # social_facility=retirement_home says more than amenity does
    kind = t.get("social_facility") or t.get("amenity") or t.get("leisure")
    if kind not in SENSITIVE_KINDS:
        continue
    name = t.get("name")
    if not name:
        continue
    if dist_to_corridor(c["lat"], c["lon"]) > RADIUS_M:
        continue
    # OSM lists the same campus repeatedly; fold it into one entry
    if any(w in name for w in ("Unipark", "Universität Salzburg", "Hochschülerschaft")):
        name, kind, key = "Universitätscampus Unipark Nonntal", "university", "unipark"
    else:
        key = name.split(" ")[0].lower()
    if key in _seen:
        continue
    _seen.add(key)
    DESTINATIONS.append(
        {
            "name": name,
            "kind": kind,
            "distance_m": round(dist_to_corridor(c["lat"], c["lon"])),
        }
    )
# Not every OSM "school" is a school for children: colleges and training
# centres for adults are counted separately, because the StVO amendment turns
# on the surroundings of schools and kindergartens.
ADULT_EDUCATION = (
    "Pädagogische Hochschule",
    "Schule für Sozialbetreuungsberufe",
    "Universitätscampus",
    "Ausbildungszentrum",
    "Hochschülerschaft",
)
for z in DESTINATIONS:
    if z["kind"] in ("school", "kindergarten"):
        z["level"] = (
            "adults"
            if any(w in z["name"] for w in ADULT_EDUCATION)
            else "children"
        )
    elif z["kind"] == "university":
        z["level"] = "adults"
DESTINATIONS.sort(key=lambda z: z["distance_m"])
CHILD_FACILITIES = [z for z in DESTINATIONS if z.get("level") == "children"]
CHILD_SCHOOLS = [z for z in CHILD_FACILITIES if z["kind"] == "school"]
NEAREST_CHILD_FACILITY = min((z["distance_m"] for z in CHILD_FACILITIES), default=None)
COUNTS = {}
for z in DESTINATIONS:
    COUNTS[z["kind"]] = COUNTS.get(z["kind"], 0) + 1

# ================================================================= Palette ===
# The palette is drawn from the subject itself: daylight asphalt as the ground,
# the red of Austrian prohibitory signs as the signal colour, the blue of the
# street signage for public transport. The neutrals are deliberately cool,
# not cream.
PAL = {
    "paper": ("#f2f5f6", "#0f1315"),
    "ink": ("#15191c", "#e6eaec"),
    "inksoft": ("#566066", "#949ea4"),
    "bldg": ("#e3e8ea", "#191e21"),
    "bldgline": ("#d5dbde", "#20262a"),
    "green": ("#dde6de", "#152018"),
    "road": ("#ffffff", "#272e32"),
    "roadcase": ("#d4dade", "#1b2125"),
    "foot": ("#b3bbc0", "#3f474d"),
    "danger": ("#d12b1c", "#ff6a4d"),
    "dangersoft": ("#f8ddd8", "#3a1712"),
    "good": ("#0f7a6b", "#2ec4ab"),
    "goodsoft": ("#d6eae6", "#0d2a25"),
    "transit": ("#1f55c9", "#7aa6ff"),
    "school": ("#6344bd", "#ad92ff"),
    "grid": ("#dde3e6", "#232a2e"),
}
FONT = ('font-family="ui-sans-serif,system-ui,-apple-system,Segoe UI,'
        'Roboto,Helvetica Neue,Arial,sans-serif"')


def svg_style():
    """<style> block for the standalone SVG files (the fallback)."""
    light = "\n".join(f"    --k-{k}: {v[0]};" for k, v in PAL.items())
    dark = "\n".join(f"      --k-{k}: {v[1]};" for k, v in PAL.items())
    return (
        "<style>\n  svg {\n" + light + "\n  }\n"
        "  @media (prefers-color-scheme: dark) {\n    svg {\n" + dark
        + "\n    }\n  }\n</style>"
    )


def c(key):
    return f"var(--k-{key})"


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def decimal(x, n=1):
    """Number with a German decimal comma."""
    return f"{x:.{n}f}".replace(".", ",")


# ======================================================== 1. Site plan ======
# The view is derived from the content, not hard-coded: its centre is the
# centroid of what the map is about (corridor, markers, school circle).
# The view centre used to sit some 46 units west of that, which pushed the
# signalised junction out of sight on narrow displays.
SCHOOL_CIRCLE = (47.79290, 13.05385, 30.0)  # centre and radius in metres
MARGIN = 52.0  # breathing room around the highlighted content, in metres


def _content_bbox():
    """Bounding box of the highlighted content, in metres (east, north)."""
    points = [en(p) for p in pts]
    points += [en((m["lat"], m["lon"])) for m in MARKERS]
    e, n = en((SCHOOL_CIRCLE[0], SCHOOL_CIRCLE[1]))
    r = SCHOOL_CIRCLE[2]
    points += [(e - r, n - r), (e + r, n + r)]
    return (
        min(q[0] for q in points), max(q[0] for q in points),
        min(q[1] for q in points), max(q[1] for q in points),
    )


_e0, _e1, _n0, _n1 = _content_bbox()
VIEW = dict(
    lon0=pts[0][1] + (_e0 - MARGIN) / KX,
    lon1=pts[0][1] + (_e1 + MARGIN) / KX,
    lat0=pts[0][0] + (_n0 - MARGIN) / R,
    lat1=pts[0][0] + (_n1 + MARGIN) / R,
)
VW = (VIEW["lon1"] - VIEW["lon0"]) * KX
VH = (VIEW["lat1"] - VIEW["lat0"]) * R


def xy(p):
    """(lat, lon) -> site-plan SVG coordinates, 1 unit = 1 metre."""
    return ((p[1] - VIEW["lon0"]) * KX, (VIEW["lat1"] - p[0]) * R)


def d_of(geom, close=False):
    if not geom:
        return ""
    pp = [xy((g["lat"], g["lon"])) for g in geom]
    d = f"M{pp[0][0]:.1f} {pp[0][1]:.1f}" + "".join(
        f"L{x:.1f} {y:.1f}" for x, y in pp[1:]
    )
    return d + "Z" if close else d


def in_view(w, pad=60):
    b = w.get("bounds")
    if not b:
        return True
    x0, y0 = xy((b["maxlat"], b["minlon"]))
    x1, y1 = xy((b["minlat"], b["maxlon"]))
    return not (x1 < -pad or x0 > VW + pad or y1 < -pad or y0 > VH + pad)


ROAD_W = {
    "secondary": 10.0,
    "tertiary": 8.0,
    "residential": 7.0,
    "unclassified": 6.5,
    "living_street": 6.0,
    "pedestrian": 6.0,
    "service": 3.8,
}


def street_label(name, blocker, box=None, only_ways=None, font_size=9.0,
                  min_clearance=17.0):
    """Place a label along the real street geometry.

    Walks the street and picks the spot with the largest clearance from the
    markers and labels already placed. Returns (x, y, angle), or None when no
    free space is left inside the view.
    """
    half = 0.27 * font_size * len(name)  # half the text width, roughly
    candidates = []
    source = (
        [ways[w] for w in only_ways if w in ways]
        if only_ways
        else [w for w in ways.values() if w.get("tags", {}).get("name") == name]
    )
    for w in source:
        g = w.get("geometry") or []
        for i in range(len(g) - 1):
            a = xy((g[i]["lat"], g[i]["lon"]))
            b = xy((g[i + 1]["lat"], g[i + 1]["lon"]))
            seg = math.hypot(b[0] - a[0], b[1] - a[1])
            if seg < 1:
                continue
            ux, uy = (b[0] - a[0]) / seg, (b[1] - a[1]) / seg
            step = 6.0
            t = 0.0
            while t <= seg:
                candidates.append((a[0] + ux * t, a[1] + uy * t, ux, uy))
                t += step
    best = None
    for px, py, ux, uy in candidates:
        # The whole text has to sit inside the view
        samples = [
            (px + ux * s, py + uy * s) for s in (-half, -half / 2, 0, half / 2, half)
        ]
        if any(
            x < 14 or x > VW - 14 or y < 16 or y > VH - 58 for x, y in samples
        ):
            continue
        if box and any(
            box[0] - 10 < x < box[0] + box[2] + 10
            and box[1] - 10 < y < box[1] + box[3] + 10
            for x, y in samples
        ):
            continue
        clearance = min(
            math.hypot(x - bx, y - by) for x, y in samples for bx, by in blocker
        )
        if best is None or clearance > best[0]:
            best = (clearance, px, py, ux, uy)
    if not best or best[0] < min_clearance:
        return None
    _, px, py, ux, uy = best
    if ux < 0:  # keep text readable left to right
        ux, uy = -ux, -uy
    return px, py, math.degrees(math.atan2(uy, ux))


def site_plan(standalone=False):
    o = []
    # In the standalone file the legend sits in a band below the map so that
    # it hides nothing. In the HTML page it sits beside it.
    legend_h = 132 if standalone else 0
    o.append(
        f'<svg viewBox="0 0 {VW:.0f} {VH + legend_h:.0f}" '
        f'xmlns="http://www.w3.org/2000/svg" class="diagram diagram--site" '
        f'role="img" aria-labelledby="site-title site-desc">'
    )
    o.append('<title id="site-title">Lageplan Erzabt-Klotz-Straße, Salzburg-Nonntal</title>')
    o.append(
        '<desc id="site-desc">Maßstäblicher Lageplan aus OpenStreetMap-Daten. '
        f'Hervorgehoben: der {STRAIGHT_LEN:.0f} Meter lange gerade Abschnitt der '
        'Erzabt-Klotz-Straße zwischen der Ampelkreuzung '
        'Petersbrunnstraße/Akademiestraße und der Kurve zur Nonntaler '
        'Hauptstraße, die beiden Bushaltestellen auf gegenüberliegenden '
        'Straßenseiten und die nächsten legalen Querungsstellen.</desc>'
    )
    if standalone:
        o.append(svg_style())
    o.append(
        f'<rect width="{VW:.0f}" height="{VH + legend_h:.0f}" fill="{c("paper")}"/>'
    )
    o.append(f'<clipPath id="view-clip"><rect width="{VW:.0f}" height="{VH:.0f}"/></clipPath>')
    o.append('<g clip-path="url(#view-clip)">')

    # Green space
    for w in ways.values():
        t = w.get("tags", {})
        if not in_view(w):
            continue
        if t.get("leisure") == "park" or t.get("landuse") in ("grass", "forest", "cemetery"):
            o.append(f'<path d="{d_of(w.get("geometry"), True)}" fill="{c("green")}"/>')

    # Buildings
    o.append(f'<g fill="{c("bldg")}" stroke="{c("bldgline")}" stroke-width="0.6">')
    for w in ways.values():
        t = w.get("tags", {})
        if "building" in t and in_view(w):
            o.append(f'<path d="{d_of(w.get("geometry"), True)}"/>')
    o.append("</g>")

    # Footways
    o.append(
        f'<g fill="none" stroke="{c("foot")}" stroke-width="1.5" '
        f'stroke-dasharray="3 2.5" stroke-linecap="round" opacity="0.75">'
    )
    for w in ways.values():
        t = w.get("tags", {})
        if t.get("highway") in ("footway", "path", "steps", "cycleway") and in_view(w):
            o.append(f'<path d="{d_of(w.get("geometry"))}"/>')
    o.append("</g>")

    # Carriageways: kerb line first, then the surface
    roads = [
        w
        for w in ways.values()
        if w.get("tags", {}).get("highway") in ROAD_W and in_view(w)
    ]
    roads.sort(key=lambda w: ROAD_W[w["tags"]["highway"]])
    for pas in ("case", "fill"):
        o.append('<g fill="none" stroke-linecap="round" stroke-linejoin="round">')
        for w in roads:
            hw = w["tags"]["highway"]
            wd = ROAD_W[hw] + (2.2 if pas == "case" else 0)
            col = c("roadcase") if pas == "case" else c("road")
            o.append(
                f'<path d="{d_of(w.get("geometry"))}" stroke="{col}" '
                f'stroke-width="{wd:.1f}"/>'
            )
        o.append("</g>")

    # The section in question
    corridor_d = f"M{xy(pts[0])[0]:.1f} {xy(pts[0])[1]:.1f}" + "".join(
        f"L{xy(p)[0]:.1f} {xy(p)[1]:.1f}" for p in pts[1:]
    )
    # Just one quiet band. An extra dashed line on top of it, and the crossing
    # line that used to run between the platforms, both ran almost parallel to
    # the road and looked like a drawing error. The crossing diagram shows that
    # crossing far more clearly anyway.
    o.append(
        f'<path d="{corridor_d}" fill="none" stroke="{c("danger")}" '
        f'stroke-width="12.5" opacity="0.26" stroke-linecap="butt"/>'
    )
    o.append(
        f'<path d="{corridor_d}" fill="none" stroke="{c("danger")}" '
        f'stroke-width="1.6" opacity="0.55"/>'
    )

    o.append("</g>")  # end clip

    # ---- Tint behind the cluster of schools
    school_centre = (47.79290, 13.05385)
    sx, sy = xy(school_centre)
    o.append(
        f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="30" fill="{c("school")}" '
        f'opacity="0.15"/>'
    )

    # ---- Place the labels along the real geometry
    box = None  # the legend no longer covers the map
    blocker = [xy((mk["lat"], mk["lon"])) for mk in MARKERS]
    blocker.append((sx, sy))  # circle around the schools

    def place(txt, font_size, color, weight, spacing, **kw):
        # Try a comfortable clearance first. Only when that leaves no room at
        # all, move in closer rather than drop the label altogether.
        pos = street_label(txt, blocker, box, font_size=font_size, **kw)
        if not pos:
            pos = street_label(
                txt, blocker, box, font_size=font_size, min_clearance=11.0, **kw
            )
        if not pos:
            return ""
        x, y, rot = pos
        # A placed label blocks the ones that follow, over its whole length.
        # It used to be just three points 20 units apart; with long names such
        # as "Nonntaler Hauptstrasse" the ends stayed unprotected and the next
        # label was laid on top of them.
        half = 0.27 * font_size * len(txt)
        ux = math.cos(math.radians(rot))
        uy = math.sin(math.radians(rot))
        blocker.extend(
            (x + ux * t, y + uy * t)
            for t in (-half, -half / 2, 0.0, half / 2, half)
        )
        return (
            f'<text x="{x:.1f}" y="{y:.1f}" '
            f'transform="rotate({rot:.1f} {x:.1f} {y:.1f})" text-anchor="middle" '
            f'{FONT} font-size="{font_size}" font-weight="{weight}" '
            f'letter-spacing="{spacing}" fill="{color}" paint-order="stroke" '
            f'stroke="{c("paper")}" stroke-width="3.2" stroke-linejoin="round">'
            f'{esc(txt)}</text>'
        )

    o.append(
        place("Erzabt-Klotz-Straße", 9.0, c("inksoft"), 600, 0.3,
              only_ways=[314950230, 134631797])
    )
    for street in (
        "Nonntaler Hauptstraße",
        "Petersbrunnstraße",
        "Akademiestraße",
        "Fürstenallee",
        "Wäschergasse",
    ):
        o.append(place(street, 9.0, c("inksoft"), 600, 0.3))

    # ---- Numbered markers; the legend sits beside them in the HTML
    o.append('<g class="markers">')
    for mk in MARKERS:
        x, y = xy((mk["lat"], mk["lon"]))
        col = c(mk["color"])
        o.append(
            f'<g class="marker" data-num="{mk["num"]}" tabindex="0" role="listitem" '
            f'aria-label="{esc(str(mk["num"]))}. {esc(mk["short"])}">'
            f'<circle class="marker__halo" cx="{x:.1f}" cy="{y:.1f}" r="9" '
            f'fill="{col}" opacity="0"/>'
            f'<circle class="marker__ring" cx="{x:.1f}" cy="{y:.1f}" r="9" '
            f'fill="{c("paper")}" stroke="{col}" stroke-width="2.6"/>'
            f'<text class="marker__num" x="{x:.1f}" y="{y + 3.6:.1f}" '
            f'text-anchor="middle" {FONT} font-size="10.5" font-weight="700" '
            f'fill="{col}">{mk["num"]}</text></g>'
        )
    o.append("</g>")

    # ---- North arrow, scale bar, attribution
    # Bottom right: since the view is centred on the content, the corridor runs
    # into the bottom-left corner and collided with both of them there.
    o.append(
        f'<g opacity="0.8"><path d="M{VW-26} {VH-54:.0f} L{VW-26} {VH-76:.0f} '
        f'M{VW-31} {VH-69:.0f} L{VW-26} {VH-76:.0f} L{VW-21} {VH-69:.0f}" fill="none" '
        f'stroke="{c("ink")}" stroke-width="1.6" stroke-linecap="round" '
        f'stroke-linejoin="round"/>'
        f'<text x="{VW-26}" y="{VH-41:.0f}" text-anchor="middle" {FONT} font-size="9" '
        f'font-weight="700" fill="{c("ink")}">N</text></g>'
    )
    o.append(
        f'<g><path d="M{VW-190} {VH-46:.0f} h100" stroke="{c("ink")}" stroke-width="2.4"/>'
        f'<path d="M{VW-190} {VH-51:.0f} v10 M{VW-140} {VH-50:.0f} v8 M{VW-90} {VH-51:.0f} v10" '
        f'stroke="{c("ink")}" stroke-width="1.4"/>'
        f'<text x="{VW-190}" y="{VH-54:.0f}" {FONT} font-size="9" font-weight="600" '
        f'fill="{c("ink")}">0</text>'
        f'<text x="{VW-90}" y="{VH-54:.0f}" text-anchor="middle" {FONT} font-size="9" '
        f'font-weight="600" fill="{c("ink")}">100 m</text></g>'
    )
    o.append(
        f'<text x="20" y="{VH-8:.0f}" {FONT} font-size="8" fill="{c("inksoft")}">'
        f'Geometrie: OpenStreetMap-Mitwirkende (ODbL) · Darstellung: data/build.py'
        f'</text>'
    )

    # ---- Legend band below the map (standalone file only)
    if standalone:
        o.append(
            f'<path d="M0 {VH:.0f} H{VW:.0f}" stroke="{c("grid")}" '
            f'stroke-width="1.4"/>'
        )
        for i, mk in enumerate(MARKERS):
            band_col, band_row = divmod(i, 4)
            lx = 24 + band_col * (VW - 48) / 2
            ly = VH + 30 + band_row * 25
            o.append(
                f'<circle cx="{lx + 9:.0f}" cy="{ly - 4:.0f}" r="8.4" fill="none" '
                f'stroke="{c(mk["color"])}" stroke-width="2.2"/>'
                f'<text x="{lx + 9:.0f}" y="{ly - 0.6:.0f}" text-anchor="middle" '
                f'{FONT} font-size="10" font-weight="700" '
                f'fill="{c(mk["color"])}">{mk["num"]}</text>'
                f'<text x="{lx + 26:.0f}" y="{ly:.0f}" {FONT} font-size="11" '
                f'fill="{c("ink")}">{esc(mk["short"])}</text>'
            )
    o.append("</svg>")
    return "".join(o)


# ============================================== 2. Crossing diagram (band) ====
QW, QH = 980, 322
QX0 = 70          # left margin
QRAND = 48        # right margin, for the "Meter" caption
QSC = (QW - QX0 - QRAND) / CORRIDOR_LEN  # pixels per metre, adapts
Y_TOP, Y_BOT = 86.0, 138.0  # top / bottom edge of the carriageway
WALK_W = 10.0  # pavement width


def qx(station):
    return QX0 + station * QSC


def crossing_diagram(standalone=False):
    o = []
    o.append(
        f'<svg viewBox="0 0 {QW} {QH}" xmlns="http://www.w3.org/2000/svg" '
        f'class="diagram diagram--crossings" role="img" aria-labelledby="cross-title cross-desc">'
    )
    o.append('<title id="cross-title">Querungsmöglichkeiten im Längsschnitt</title>')
    o.append(
        '<desc id="cross-desc">Die Erzabt-Klotz-Straße gerade ausgerichtet, '
        'maßstäblich gestationiert. Die beiden Bushaltestellen liegen '
        f'auf gegenüberliegenden Straßenseiten. Zwischen '
        'ihnen gibt es keine Querungsmöglichkeit; die nächsten legalen Übergänge '
        f'liegen {stops[0]["distance_to_crossing_m"]:.0f} und '
        f'{stops[1]["distance_to_crossing_m"]:.0f} Meter entfernt.</desc>'
    )
    if standalone:
        o.append(svg_style())
    o.append(f'<rect width="{QW}" height="{QH}" fill="{c("paper")}"/>')

    top, bot = Y_TOP, Y_BOT
    xl, xr = qx(0), qx(CORRIDOR_LEN)
    o.append(
        f'<defs><marker id="cross-arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse">'
        f'<path d="M0 0 L10 5 L0 10 z" fill="{c("danger")}"/></marker>'
        f'<marker id="measure-arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
        f'<path d="M0 0 L10 5 L0 10 z" fill="{c("inksoft")}"/></marker></defs>'
    )

    # ---- Name the two ends
    o.append(
        f'<path d="M{xl:.0f} 32 V{bot + WALK_W + 4:.0f}" stroke="{c("inksoft")}" '
        f'stroke-width="1.4" stroke-dasharray="5 4" opacity="0.7"/>'
    )
    o.append(
        f'<text x="{xl:.0f}" y="26" {FONT} font-size="11" font-weight="700" '
        f'fill="{c("inksoft")}">Ampelkreuzung</text>'
    )
    o.append(
        f'<text x="{xr:.0f}" y="26" text-anchor="end" {FONT} font-size="11" '
        f'font-weight="700" fill="{c("inksoft")}">'
        f'Kurve nach Süden</text>'
    )

    # ---- Dimension line for the straight
    ym = 58
    xs1, xs2 = qx(STRAIGHT_FROM), qx(STRAIGHT_TO)
    o.append(
        f'<path d="M{xs1:.0f} {ym} H{xs2:.0f}" stroke="{c("inksoft")}" '
        f'stroke-width="1.2" marker-start="url(#measure-arrow)" marker-end="url(#measure-arrow)"/>'
    )
    for x in (xs1, xs2):
        o.append(
            f'<path d="M{x:.0f} {ym-5} v10" stroke="{c("inksoft")}" stroke-width="1.2"/>'
        )
    o.append(
        f'<text x="{(xs1+xs2)/2:.0f}" y="{ym-8}" text-anchor="middle" {FONT} '
        f'font-size="11.5" font-weight="700" fill="{c("ink")}" '
        f'paint-order="stroke" stroke="{c("paper")}" stroke-width="4" '
        f'stroke-linejoin="round">{STRAIGHT_LEN:.0f} m nahezu gerade · '
        f'Richtungsabweichung ±{decimal(STRAIGHT_SPREAD)}°</text>'
    )

    # ---- Pavements and carriageway
    for y in (top - WALK_W, bot):
        o.append(
            f'<rect x="{xl:.0f}" y="{y:.1f}" width="{xr-xl:.0f}" height="{WALK_W}" '
            f'fill="{c("bldg")}" stroke="{c("bldgline")}" stroke-width="0.8"/>'
        )
    o.append(
        f'<rect x="{xl:.0f}" y="{top:.1f}" width="{xr-xl:.0f}" '
        f'height="{bot-top:.0f}" fill="{c("road")}" stroke="{c("roadcase")}" '
        f'stroke-width="1.2"/>'
    )
    o.append(
        f'<rect x="{xs1:.0f}" y="{top:.1f}" width="{xs2-xs1:.0f}" '
        f'height="{bot-top:.0f}" fill="{c("danger")}" opacity="0.1"/>'
    )
    # three marked lanes (lanes=3: one each way plus the bus lane)
    for k in (1, 2):
        y = top + (bot - top) * k / 3
        o.append(
            f'<path d="M{xl:.0f} {y:.1f} H{xr:.0f}" stroke="{c("roadcase")}" '
            f'stroke-width="1" stroke-dasharray="10 8"/>'
        )
    o.append(
        f'<text x="{xl-12:.0f}" y="{(top+bot)/2:.0f}" text-anchor="middle" '
        f'transform="rotate(-90 {xl-12:.0f} {(top+bot)/2:.0f})" {FONT} '
        f'font-size="8.5" font-weight="600" fill="{c("inksoft")}">'
        f'2 Fahrstreifen + Busspur</text>'
    )

    # ---- Crossings
    for cr in crossings:
        x = qx(cr["station"])
        o.append(
            f'<path d="M{x:.0f} {top:.1f} V{bot:.1f}" stroke="{c("good")}" '
            f'stroke-width="3.4" stroke-dasharray="5 3.5"/>'
        )
        o.append(
            f'<circle cx="{x:.0f}" cy="{top-WALK_W-11:.0f}" r="7" fill="{c("paper")}" '
            f'stroke="{c("good")}" stroke-width="2.2"/>'
            f'<text x="{x:.0f}" y="{top-WALK_W-7.6:.0f}" text-anchor="middle" {FONT} '
            f'font-size="8" font-weight="700" fill="{c("good")}">A</text>'
        )

    # ---- Bus stops on the pavements
    for s in stops:
        x = qx(s["station"])
        on_top = s["side_sign"] < 0
        y = top - WALK_W if on_top else bot
        o.append(
            f'<rect x="{x-15:.0f}" y="{y:.1f}" width="30" height="{WALK_W}" '
            f'rx="1.5" fill="{c("transit")}"/>'
        )
        o.append(
            f'<text x="{x:.0f}" y="{y - 7 if on_top else y + WALK_W + 14:.0f}" '
            f'text-anchor="middle" {FONT} font-size="10" font-weight="700" '
            f'fill="{c("transit")}">{esc(s["label"].replace("Haltestelle ", "Bus "))}'
            f'</text>'
        )

    # ---- People cross square to the carriageway, level with the bus stops.
    # With both platforms facing each other, one line is enough.
    for x in sorted({round(qx(s["station"])) for s in stops}):
        o.append(
            f'<path d="M{x:.0f} {bot - 1:.0f} V{top + 1:.0f}" '
            f'stroke="{c("danger")}" stroke-width="2.8" stroke-dasharray="2.5 4.5" '
            f'stroke-linecap="round" marker-end="url(#cross-arrow)" '
            f'marker-start="url(#cross-arrow)"/>'
        )
    xm = (qx(stops[0]["station"]) + qx(stops[1]["station"])) / 2
    ly = bot + WALK_W + 36
    o.append(
        f'<path d="M{qx(stops[1]["station"]):.0f} {bot + WALK_W + 2:.0f} '
        f'L{xm - 6:.0f} {ly - 11:.0f}" stroke="{c("danger")}" stroke-width="0.9" '
        f'opacity="0.6" fill="none"/>'
    )
    o.append(
        f'<text x="{xm:.0f}" y="{ly:.0f}" text-anchor="middle" {FONT} '
        f'font-size="11" font-weight="700" fill="{c("danger")}">'
        f'Auf Höhe der Haltestellen wird gequert</text>'
    )
    o.append(
        f'<text x="{xm:.0f}" y="{ly+14:.0f}" text-anchor="middle" {FONT} '
        f'font-size="10" fill="{c("danger")}">über die gesamte Fahrbahn, '
        f'ohne Übergang</text>'
    )

    # ---- Detour brackets
    def bracket(x1, x2, y, text):
        return (
            f'<path d="M{x1:.0f} {y-6:.0f} V{y:.0f} H{x2:.0f} V{y-6:.0f}" '
            f'fill="none" stroke="{c("danger")}" stroke-width="1.4"/>'
            f'<text x="{(x1+x2)/2:.0f}" y="{y+14:.0f}" text-anchor="middle" {FONT} '
            f'font-size="11" font-weight="700" fill="{c("danger")}">{esc(text)}</text>'
        )

    y_bracket = 244
    gap = CORRIDOR_LEN - crossings[0]["station"]
    o.append(
        bracket(qx(crossings[0]["station"]), qx(CORRIDOR_LEN), y_bracket,
                f'{gap:.0f} m ohne gesicherte Querung')
    )

    # ---- Chainage
    o.append(f'<g {FONT} font-size="8.5" fill="{c("inksoft")}">')
    s = 0
    while s <= CORRIDOR_LEN:
        o.append(
            f'<path d="M{qx(s):.1f} 268 v6" stroke="{c("grid")}" stroke-width="1.2"/>'
        )
        o.append(f'<text x="{qx(s):.1f}" y="286" text-anchor="middle">{s:.0f}</text>')
        s += 50
    o.append(f'<path d="M{xl:.0f} 268 H{xr:.0f}" stroke="{c("grid")}" stroke-width="1.2"/>')
    o.append(f'<text x="{xr+12:.0f}" y="286">Meter</text>')
    o.append("</g>")

    o.append(
        f'<text x="{QW/2:.0f}" y="{QH-8:.0f}" text-anchor="middle" {FONT} '
        f'font-size="9" fill="{c("inksoft")}">Alle Längen aus der '
        f'OpenStreetMap-Geometrie berechnet · data/build.py</text>'
    )
    o.append("</svg>")
    return "".join(o)


# ========================================= 3. Compare stopping distances ==
AW, AH = 980, 352
ASC = 22.0  # pixels per metre
AX0 = 150


def stopping_diagram(standalone=False):
    o = []
    o.append(
        f'<svg viewBox="0 0 {AW} {AH}" xmlns="http://www.w3.org/2000/svg" '
        f'class="diagram diagram--stopping" role="img" aria-labelledby="stop-title stop-desc">'
    )
    o.append('<title id="stop-title">Anhaltewege bei 30, 50 und 60 km/h</title>')
    desc = "; ".join(
        f'{s["kmh"]} km/h: {s["stopping_distance_m"]:.0f} Meter' for s in SPEEDS
    )
    o.append(
        f'<desc id="stop-desc">Vergleich der Anhaltewege: {desc}. An der Stelle, '
        f'an der ein Fahrzeug mit 30 km/h bereits steht, hat ein Fahrzeug mit '
        f'50 km/h die Bremsung noch nicht begonnen.</desc>'
    )
    if standalone:
        o.append(svg_style())
    o.append(f'<rect width="{AW}" height="{AH}" fill="{c("paper")}"/>')

    rows = [68, 140, 212]
    bh = 30

    # Metre grid
    o.append(f'<g {FONT} font-size="8.5" fill="{c("inksoft")}">')
    for m in range(0, 41, 5):
        x = AX0 + m * ASC
        o.append(
            f'<path d="M{x:.0f} 44 V{rows[-1]+bh+10:.0f}" stroke="{c("grid")}" '
            f'stroke-width="1"/>'
        )
        o.append(f'<text x="{x:.0f}" y="36" text-anchor="middle">{m}</text>')
    o.append(f'<text x="{AX0 + 40*ASC + 16:.0f}" y="36">Meter</text>')
    o.append("</g>")

    for s, y in zip(SPEEDS, rows):
        xr = AX0
        wr = s["reaction_distance_m"] * ASC
        wb = s["braking_distance_m"] * ASC
        col = c("good") if s["kmh"] == 30 else c("danger")
        o.append(
            f'<text x="{AX0-18:.0f}" y="{y+20:.0f}" text-anchor="end" {FONT} '
            f'font-size="17" font-weight="700" fill="{col}">{s["kmh"]} km/h</text>'
        )
        o.append(
            f'<rect x="{xr:.0f}" y="{y:.0f}" width="{wr:.1f}" height="{bh}" '
            f'fill="{col}" opacity="0.25" rx="1"/>'
        )
        o.append(
            f'<rect x="{xr+wr:.1f}" y="{y:.0f}" width="{wb:.1f}" height="{bh}" '
            f'fill="{col}" opacity="0.8" rx="1"/>'
        )
        o.append(
            f'<text x="{xr+wr+wb+10:.1f}" y="{y+20:.0f}" {FONT} font-size="13" '
            f'font-weight="700" fill="{col}">{s["stopping_distance_m"]:.0f} m</text>'
        )
        if s["kmh"] == 30:
            o.append(
                f'<text x="{xr+4:.0f}" y="{y-5:.0f}" {FONT} font-size="9" '
                f'fill="{c("inksoft")}">Reaktion</text>'
            )
            o.append(
                f'<text x="{xr+wr+4:.0f}" y="{y-5:.0f}" {FONT} font-size="9" '
                f'fill="{c("inksoft")}">Bremsung</text>'
            )

    # The line where the vehicle doing 30 has come to a stop
    xs = AX0 + STOP30 * ASC
    yb = rows[-1] + bh
    o.append(
        f'<path d="M{xs:.1f} 44 V{yb+26:.0f}" stroke="{c("ink")}" '
        f'stroke-width="2" stroke-dasharray="6 4"/>'
    )
    # Pedestrian symbol on the stop line
    o.append(
        f'<g transform="translate({xs:.1f} {yb+48:.0f})" fill="{c("ink")}">'
        f'<circle cx="0" cy="-19" r="3.6"/>'
        f'<path d="M0 -15 V-6 M0 -12 L-5.5 -8 M0 -12 L5.5 -8 M0 -6 L-5 2.5 '
        f'M0 -6 L5 2.5" stroke="{c("ink")}" stroke-width="2.1" fill="none" '
        f'stroke-linecap="round"/></g>'
    )
    o.append(
        f'<text x="{xs+16:.1f}" y="{yb+40:.0f}" {FONT} font-size="11.5" '
        f'font-weight="700" fill="{c("ink")}">Bei 30 km/h steht das Fahrzeug '
        f'an dieser Stelle.</text>'
    )
    o.append(
        f'<text x="{xs+16:.1f}" y="{yb+56:.0f}" {FONT} font-size="11.5" '
        f'fill="{c("ink")}">Bei 50 km/h ist die Bremsung hier noch nicht '
        f'eingeleitet: Die Reaktionszeit allein dauert länger.</text>'
    )
    o.append(
        f'<text x="{xs+16:.1f}" y="{yb+72:.0f}" {FONT} font-size="11" '
        f'fill="{c("inksoft")}">Die Aufprallgeschwindigkeit betrüge '
        f'{RESIDUAL_AT_STOP30[50]:.0f} km/h.</text>'
    )
    o.append(
        f'<text x="{AW/2:.0f}" y="{AH-10:.0f}" text-anchor="middle" {FONT} '
        f'font-size="9" fill="{c("inksoft")}">Annahmen: Reaktionszeit '
        f'{decimal(REACTION_TIME)} s, Gefahrenbremsung {DECELERATION:.0f} m/s² '
        f'(trockener Asphalt) · Rechenweg in data/build.py</text>'
    )
    o.append("</svg>")
    return "".join(o)


# =================================================================== Write ==
def js_string(s):
    return s.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


figures = {
    "FIGURE_SITE": site_plan,
    "FIGURE_CROSSINGS": crossing_diagram,
    "FIGURE_STOPPING": stopping_diagram,
}

js = [
    "/* Generated by data/build.py. Do not edit by hand. */",
    "/* Geometry: OpenStreetMap contributors, ODbL. */",
]
for name, fn in figures.items():
    js.append(f"const {name} = `{js_string(fn(standalone=False))}`;")
js.append(
    "window.FIGURES = { site: FIGURE_SITE, crossings: FIGURE_CROSSINGS, "
    "stopping: FIGURE_STOPPING };"
)
# Site-plan legend: one source for both the SVG and the HTML
js.append(
    "window.MARKERS = "
    + json.dumps(
        [
            {k: mk[k] for k in ("num", "color", "short", "detail")}
            for mk in MARKERS
        ],
        ensure_ascii=False,
    )
    + ";"
)
# Sensitive destinations, for the table on the page
KIND_LABELS = {
    "school": "Schule",
    "kindergarten": "Kindergarten",
    "university": "Hochschule",
    "hospital": "Krankenhaus",
    "retirement_home": "Seniorenheim",
    "theatre": "Theater",
    "rehearsal_studio": "Probenhaus",
    "arts_centre": "Kulturzentrum",
    "music_school": "Musikschule",
    "playground": "Spielplatz",
}
js.append(
    "window.DESTINATIONS = "
    + json.dumps(
        [
            {"name": z["name"], "kind": KIND_LABELS.get(z["kind"], z["kind"]),
             "m": z["distance_m"]}
            for z in DESTINATIONS
        ],
        ensure_ascii=False,
    )
    + ";"
)
with open(os.path.join(ASSETS, "figures.js"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(js) + "\n")

# The palette as CSS, so page and figures can never drift apart
def _vars(i, indent):
    return "\n".join(f"{indent}--k-{k}: {v[i]};" for k, v in PAL.items())


with open(os.path.join(ASSETS, "palette.css"), "w", encoding="utf-8") as fh:
    fh.write(
        "/* Generated by data/build.py. Do not edit by hand. */\n"
        "/* The SVG figures in figures.js use these same colours. */\n\n"
        ":root {\n" + _vars(0, "  ") + "\n  color-scheme: light dark;\n}\n\n"
        "@media (prefers-color-scheme: dark) {\n"
        "  :root:not([data-theme=\"light\"]) {\n" + _vars(1, "    ") + "\n  }\n}\n\n"
        ":root[data-theme=\"dark\"] {\n" + _vars(1, "  ") + "\n}\n\n"
        ":root[data-theme=\"light\"] {\n" + _vars(0, "  ") + "\n}\n"
    )

for fname, fn in [
    ("figure-site-plan.svg", site_plan),
    ("figure-crossings.svg", crossing_diagram),
    ("figure-stopping-distance.svg", stopping_diagram),
]:
    with open(os.path.join(ASSETS, fname), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n' + fn(standalone=True) + "\n")

# ------------------------------------------- Buildings along the corridor ---
# Evidence that a three-lane main road runs through a residential area here.
# Small outbuildings (bus shelter, transformer, shed) are excluded by footprint
# area: the OSM object with the smallest distance is a 7 m2 "roof", namely the
# shelter at the bus stop.
RESIDENTIAL_KINDS = {"residential", "apartments", "house", "detached", "terrace", "yes"}
MIN_AREA = 60  # m2; below this it counts as an outbuilding

adjacent = []
for w in ways.values():
    t = w.get("tags", {})
    if t.get("building") not in RESIDENTIAL_KINDS:
        continue
    g = w.get("geometry") or []
    if not g:
        continue
    e_pts = [en((q["lat"], q["lon"])) for q in g]
    area = abs(
        sum(
            e_pts[i][0] * e_pts[i + 1][1] - e_pts[i + 1][0] * e_pts[i][1]
            for i in range(len(e_pts) - 1)
        )
    ) / 2
    if area < MIN_AREA:
        continue
    # search by distance, not by chainage
    nearest = min(
        (project_on_corridor((q["lat"], q["lon"])) for q in g),
        key=lambda r: r[1],
    )
    offset, station = nearest[1], nearest[0]
    if offset < 45:
        adjacent.append(
            {
                "distance_to_axis_m": round(offset, 1),
                "station_m": round(station),
                "kind": t.get("building"),
                "footprint_m2": round(area),
                "levels": t.get("building:levels"),
                "address": " ".join(
                    x for x in (t.get("addr:street"), t.get("addr:housenumber")) if x
                ) or None,
            }
        )
adjacent.sort(key=lambda a: a["distance_to_axis_m"])
# For the claim "nearest home" only count what is unambiguously residential;
# the generic building=yes stays out of it.
CLEARLY_RESIDENTIAL = {"residential", "apartments", "house", "detached", "terrace"}
_homes = [a for a in adjacent if a["kind"] in CLEARLY_RESIDENTIAL]
NEAREST_HOME = _homes[0] if _homes else None
# Half the carriageway width, roughly, from the lane count (3 x about 3.3 m)
CARRIAGEWAY_W = 3 * 3.3
KERB_TO_FACADE = (
    round(NEAREST_HOME["distance_to_axis_m"] - CARRIAGEWAY_W / 2, 1)
    if NEAREST_HOME else None
)

# --------------------------------------------- Derive the photo positions ---
# So that our own photographs match the figures, position and view direction
# are computed from the corridor geometry rather than estimated.
VIEW_NE = bearings[sj - 1] - 180  # along the straight, towards the north-east
VIEW_NE = VIEW_NE % 360
VIEW_SW = (VIEW_NE + 180) % 360
VIEW_SE = (VIEW_NE + 90) % 360  # square across the carriageway
VIEW_NW = (VIEW_NE + 270) % 360

PHOTO_SPOTS = [
    ("Ampelkreuzung, Blick nach Südwesten", coord[N_SIGNAL], VIEW_SW,
     "Der gesamte gerade Abschnitt in einem Bild, bis zur Kurve."),
    (f'{stops[1]["label"]}, quer über die Fahrbahn',
     (stops[1]["platform_lat"], stops[1]["platform_lon"]), VIEW_SE,
     "Die Querung, die hier täglich stattfindet: drei Fahrstreifen, kein Übergang."),
    (f'{stops[1]["label"]}, Blick nach Nordosten',
     (stops[1]["platform_lat"], stops[1]["platform_lon"]), VIEW_NE,
     f'Zeigt, wie weit die Bedarfsampel entfernt ist '
     f'({stops[1]["distance_to_crossing_m"]:.0f} m).'),
    (f'{stops[0]["label"]}, quer über die Fahrbahn',
     (stops[0]["platform_lat"], stops[0]["platform_lon"]), VIEW_NW,
     "Dieselbe Situation von der anderen Seite."),
    ("Kurve, Blick nach Nordosten", coord[N_CURVE], VIEW_NE,
     "Die Gerade vom südwestlichen Ende aus, die Sicht der Zufahrenden."),
    ("Bedarfsampel an der Kreuzung",
     (crossings[0]["lat"], crossings[0]["lon"]), VIEW_SW,
     "Drucktaster und Wartesituation; mit sichtbarer Uhr als Beleg der Wartezeit."),
]


def streetview(p, heading):
    return (f"https://www.google.com/maps/@?api=1&map_action=pano"
            f"&viewpoint={p[0]:.5f},{p[1]:.5f}&heading={heading:.0f}&pitch=0&fov=80")


lines = [
    "# Fotostandorte",
    "",
    "Automatisch erzeugt von `data/build.py`. Standort und Blickrichtung sind",
    "aus der Straßengeometrie gerechnet. Die Aufnahmen sind für das Schreiben",
    "an die Stadt, für Presseanfragen und für einen Aushang gedacht; auf der",
    "Website selbst sind keine Fotos eingebunden.",
    "",
    "Die Links öffnen Google Street View an der jeweiligen Stelle mit der",
    "richtigen Blickrichtung, zum Vorabschauen, was dort zu sehen ist. Die",
    "Panoramen selbst dürfen nicht weiterverwendet werden; die Fotos für die",
    "Seite müssen selbst aufgenommen werden.",
    "",
]
for i, (title, p, head, purpose) in enumerate(PHOTO_SPOTS, 1):
    lines += [
        f"## {i}. {title}",
        "",
        f"- **Standort:** `{p[0]:.5f}, {p[1]:.5f}`",
        f"- **Blickrichtung:** {head:.0f}° ({'Nordost' if head < 90 else 'Südost' if head < 180 else 'Südwest' if head < 270 else 'Nordwest'})",
        f"- **Zeigt:** {purpose}",
        f"- [In Street View ansehen]({streetview(p, head)})",
        "",
    ]
lines += [
    "---",
    "",
    "Beste Zeit für den Schulweg: werktags 7:15–8:00 Uhr und 12:00–13:30 Uhr.",
    "Querformat, und bitte ohne erkennbare Gesichter und Kennzeichen; Hinweise",
    "dazu in `media/README.md`.",
    "",
]
with open(os.path.join(ROOT, "media", "locations.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))

measurements = {
    "source": "OpenStreetMap-Mitwirkende (ODbL), Abfragen in data/overpass-*.ql",
    "photo_spots": [
        {"title": t, "lat": p[0], "lon": p[1], "bearing_deg": round(h),
         "purpose": z}
        for t, p, h, z in PHOTO_SPOTS
    ],
    "osm_timestamp": osm.get("osm3s", {}).get("timestamp_osm_base"),
    "corridor": {
        "description": "Erzabt-Klotz-Straße von der Ampelkreuzung "
        "Petersbrunnstraße/Akademiestraße bis in die Kurve zur Nonntaler Hauptstraße",
        "length_m": round(CORRIDOR_LEN, 1),
        "straight_length_m": round(STRAIGHT_LEN, 1),
        "straight_from_chainage_m": round(STRAIGHT_FROM, 1),
        "straight_to_chainage_m": round(STRAIGHT_TO, 1),
        "straight_bearing_spread_deg": round(STRAIGHT_SPREAD, 1),
        "curve_angle_deg": round(CURVE_ANGLE, 1),
        "maxspeed_osm": {str(k): v for k, v in limits.items()},
        "lanes": CROSS_SECTION.get("lanes"),
        "cross_section_tags": {
            k: v
            for k, v in CROSS_SECTION.items()
            if k in ("lanes", "lanes:forward", "lanes:backward",
                     "lanes:psv:backward", "cycleway:left", "cycleway:right",
                     "sidewalk", "maxspeed", "ref", "trolley_wire")
        },
    },
    "bus_stops": stops,
    "bus_stop_offset_m": round(STOP_GAP, 1),
    "crossings": crossings,
    "map_markers": MARKERS,
    "stopping_distances": {
        "assumptions": {
            "reaction_time_s": REACTION_TIME,
            "deceleration_m_s2": DECELERATION,
            "note": "Gefahrenbremsung auf trockenem Asphalt",
        },
        "values": SPEEDS,
        "residual_speed_at_stop30_kmh": RESIDUAL_AT_STOP30,
    },
    "travel_time_on_straight_s": TRAVEL_TIME,
    "time_lost_at_30_s": TIME_LOST,
    "development": {
        "note": "Wohngebäude mit mehr als 60 m² Grundfläche, Abstand zur Straßenachse unter 45 m",
        "building_count": len(adjacent),
        "home_count": len(_homes),
        "nearest_home": NEAREST_HOME,
        "carriageway_width_est_m": CARRIAGEWAY_W,
        "kerb_to_nearest_facade_m": KERB_TO_FACADE,
        "list": adjacent,
    },
    "sensitive_destinations_600m": DESTINATIONS,
    "counts_by_kind": COUNTS,
    "education_by_level": {
        "schools_for_children": len(CHILD_SCHOOLS),
        "kindergartens": len([z for z in CHILD_FACILITIES
                              if z["kind"] == "kindergarten"]),
        "adult_education": len([z for z in DESTINATIONS
                                   if z.get("level") == "adults"]),
        "nearest_child_facility_m": NEAREST_CHILD_FACILITY,
    },
}
with open(os.path.join(HERE, "measurements.json"), "w", encoding="utf-8") as fh:
    json.dump(measurements, fh, ensure_ascii=False, indent=2)

# ------------------------------------------------------------------- Report ---
print(f"corridor signal -> curve           {CORRIDOR_LEN:7.1f} m")
print(f"  of which straight (+/-{STRAIGHT_SPREAD:.1f} deg) {STRAIGHT_LEN:7.1f} m"
      f"  (chainage {STRAIGHT_FROM:.0f}-{STRAIGHT_TO:.0f})")
print(f"  bend into Nonntaler Hauptstr.     {CURVE_ANGLE:5.1f} deg")
print(f"  speed limit along corridor        {sorted(set(limits.values()))}")
print(f"bus stop offset                   {STOP_GAP:7.1f} m")
for s in stops:
    print(f"  {s['label']:28s} chainage {s['station']:6.1f} m, {s['side']:9s}"
          f" -> {s['distance_to_crossing_m']:5.1f} m to nearest crossing")
print(f"stopping distances  " + "   ".join(
    f"{s['kmh']}:{s['stopping_distance_m']:.1f}m" for s in SPEEDS))
print(f"  residual speed after {STOP30:.1f} m " + "  ".join(
    f"{k}->{v:.0f}" for k, v in RESIDUAL_AT_STOP30.items()))
print(f"travel time along the straight    "
      f"50: {TRAVEL_TIME[50]:.1f} s   30: {TRAVEL_TIME[30]:.1f} s"
      f"   difference {TIME_LOST:.1f} s")
print(f"sensitive destinations <600 m     {COUNTS}")
print(f"  of which schools for children   {len(CHILD_SCHOOLS)}, nearest child facility {NEAREST_CHILD_FACILITY} m")
print(f"homes within 45 m                 {len(adjacent)}; nearest "
      f"{NEAREST_HOME['distance_to_axis_m']} m "
      f"({NEAREST_HOME['address']}), "
      f"about {KERB_TO_FACADE} m from the kerb")
print()
print("written: assets/figures.js, assets/figure-*.svg, data/measurements.json")
