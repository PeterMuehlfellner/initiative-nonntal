#!/usr/bin/env python3
"""
Erzeugt aus den OpenStreetMap-Rohdaten (daten/osm.json, daten/poi.json) alle
Grafiken und Messwerte der Website.

    python3 daten/build.py

Ausgabe:
    assets/karten.js              Alle SVGs als JS-Strings (werden ins DOM gehaengt,
                                  damit sie per CSS mitdunkeln und interaktiv sind)
    assets/karte-*.svg            Dieselben SVGs eigenstaendig (noscript-Fallback,
                                  und zum Einfuegen in Schreiben an die Behoerde)
    daten/messwerte.json          Alle berechneten Zahlen, nachpruefbar

Alle Laengen sind aus der OSM-Geometrie gerechnet, nicht geschaetzt.
Quelle: OpenStreetMap-Mitwirkende, ODbL. Abfragen siehe daten/overpass-*.ql
"""

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")

# ---------------------------------------------------------------- Geodaesie ---
R = 111320.0  # m pro Grad Breite


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return json.load(fh)


def metres(a, b):
    """Entfernung in Metern zwischen (lat,lon)-Paaren."""
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

# ------------------------------------------------------- Korridor aufbauen ---
# Reihenfolge der OSM-Wege von der Ampelkreuzung Petersbrunnstrasse/
# Akademiestrasse (Nordost) bis in die Kurve zur Nonntaler Hauptstrasse (Sued-
# west). Die Wege-IDs stammen aus der Overpass-Abfrage und sind stabil.
# Der Korridor folgt der durchgehenden Landesstrasse L 104. Am suedwestlichen
# Ende biegt sie nach Sueden in die Nonntaler Hauptstrasse ab; der westliche
# Ast der Erzabt-Klotz-Strasse (Weg 22604725, ohne ref) ist eine Nebenstrasse
# und gehoert nicht zur durchgehenden Route.
CORRIDOR_WAYS = [25353604, 134631796, 1164458568, 134631797, 314950230, 265570933]
N_KORRIDOR_ENDE = 200577881  # unmarkierte Querung am Ende der Kurve
N_SIGNAL = 151015615  # Kreuzung Petersbrunnstr./Akademiestr., Lichtsignalanlage
N_WAESCH = 1480008790  # Einmuendung Waeschergasse
N_PEREGRIN = 151015616  # Einmuendung Peregrinstrasse, hier beginnt die Gerade
N_KURVE = 151015618  # Knick 47 Grad in die Nonntaler Hauptstrasse
N_END = 996569534  # zweiter Knotenpunkt Nonntaler Hauptstrasse

path = []
cur = N_SIGNAL
for wid in CORRIDOR_WAYS:
    nl = list(ways[wid]["nodes"])
    if nl[0] != cur:
        nl.reverse()
    assert nl[0] == cur, f"Weg {wid} schliesst nicht an Knoten {cur} an"
    path += nl if not path else nl[1:]
    cur = nl[-1]

if N_KORRIDOR_ENDE in path:
    path = path[: path.index(N_KORRIDOR_ENDE) + 1]

pts = [coord[n] for n in path]
chain = [0.0]
for i in range(len(pts) - 1):
    chain.append(chain[-1] + metres(pts[i], pts[i + 1]))
CORRIDOR_LEN = chain[-1]

LAT0 = pts[0][0]
KX = R * math.cos(LAT0 * math.pi / 180)  # m pro Grad Laenge auf dieser Breite


def en(p):
    """(lat,lon) -> lokale Meterkoordinaten (Ost, Nord) relativ zum Startpunkt."""
    return ((p[1] - pts[0][1]) * KX, (p[0] - pts[0][0]) * R)


def bearing(a, b):
    la1, la2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    y = math.sin(dl) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def project_on_corridor(p):
    """Punkt auf die Korridorachse projizieren.

    Rueckgabe: (Stationierung in m, seitlicher Abstand in m, Vorzeichen).
    Vorzeichen < 0 bedeutet nordwestliche Strassenseite.
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
        cross = de * (pn - an) - dn * (pe - ae)  # >0 = links der Fahrtrichtung
        side = -1 if cross < 0 else 1
        st = chain[i] + t * math.sqrt(ll)
        if best is None or dist < best[1]:
            best = (st, dist, side)
    return best


# ------------------------------------------------- Gerade und Kurve messen ---
i_per, i_kur = path.index(N_PEREGRIN), path.index(N_KURVE)
bearings = [bearing(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def turn(b1, b2):
    return ((b2 - b1 + 540) % 360) - 180


# Laengster Abschnitt, dessen Richtungen insgesamt um hoechstens 6 Grad
# streuen. Der Vergleich gegen die Spannweite statt gegen das erste Segment
# verhindert, dass der Beginn der Kurve noch als "gerade" durchgeht.
GERADE_TOLERANZ = 6.0
best_run = (0.0, 0, 0)
for i in range(len(bearings)):
    j = i + 1
    while j < len(bearings):
        fenster = bearings[i : j + 1]
        spanne = max(
            abs(turn(a, b)) for a in fenster for b in fenster
        )
        if spanne > GERADE_TOLERANZ:
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
# Die Richtungsaenderung verteilt sich auf mehrere Knoten, ist also ein Bogen
# und kein Knick. Gemessen wird ab dem Ende der Geraden bis zum Korridorende.
KURVE_VON = STRAIGHT_TO
KURVE_BIS = chain[-1]
KURVE_LAENGE = KURVE_BIS - KURVE_VON
KURVE_WINKEL = abs(turn(bearings[sj - 1], bearings[-1]))
KURVE_RADIUS = (
    KURVE_LAENGE / math.radians(KURVE_WINKEL) if KURVE_WINKEL > 1 else float("inf")
)

# ------------------------------------------------- Haltestellen, Querungen ---
# Welcher Steig welche Richtung bedient, ist aus den Routenrelationen in OSM
# bestimmt (Linien 5, 9, 25), nicht geschaetzt:
#   Steig 740435514, suedoestliche Seite -> Hauptbahnhof, Itzling, Europark
#   Steig 766861724, nordwestliche Seite -> Groedig, Kommunalfriedhof
STOPS = [
    # (Bezeichnung, Haltestellenknoten, zugehoeriger Wartebereich/Steig)
    ("Haltestelle Richtung Zentrum", (47.7918986, 13.0501196), 740435514),
    ("Haltestelle Richtung Süden", (47.7920718, 13.0506442), 766861724),
]
# Ortskorrektur: OpenStreetMap verortet den suedoestlichen Steig rund 56 m zu
# weit suedwestlich (auf Hoehe Nr. 29 statt Nr. 25). Vor Ort liegen beide
# Steige einander gegenueber, etwa auf Hoehe Nr. 25; die Seitenzuordnung in
# OSM stimmt dagegen, das Wartehaeuschen steht auf der nordwestlichen Seite.
# Deshalb wird die Stationierung des nordwestlichen Steigs fuer beide
# uebernommen und der suedoestliche spiegelbildlich daraufgelegt.
# TODO: in OpenStreetMap korrigieren, dann kann dieser Block entfallen.
GEGENUEBER = True

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
            "steig_lat": centre[0],
            "steig_lon": centre[1],
            "station": round(st, 1),
            "seite": "nordwest" if side < 0 else "suedost",
            "seite_sign": side,
            "steig_abstand_m": round(off, 1),
            "quelle_lage": "OpenStreetMap",
        }
    )

if GEGENUEBER:
    nw = next(s for s in stops if s["seite_sign"] < 0)

    def punkt_an(station, seitlich):
        """Punkt auf der Achse bei 'station', seitlich versetzt, als (lat, lon)."""
        for i in range(len(pts) - 1):
            if chain[i] <= station <= chain[i + 1]:
                f = (station - chain[i]) / max(1e-9, chain[i + 1] - chain[i])
                a, b = en(pts[i]), en(pts[i + 1])
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
                cx, cy = a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])
                nx, ny = -uy, ux  # Normale, zeigt nach links der Fahrtrichtung
                ex, ny_ = cx + nx * seitlich, cy + ny * seitlich
                return (pts[0][0] + ny_ / R, pts[0][1] + ex / KX)
        return pts[-1]

    for s in stops:
        if s["seite_sign"] > 0:  # der suedoestliche Steig wird versetzt
            s["steig_lat"], s["steig_lon"] = punkt_an(
                nw["station"], +s["steig_abstand_m"]
            )
            s["lat"], s["lon"] = s["steig_lat"], s["steig_lon"]
            s["station"] = nw["station"]
            s["quelle_lage"] = "vor Ort korrigiert (OSM-Lage abweichend)"

STOP_GAP = abs(stops[0]["station"] - stops[1]["station"])
STOP_MID = (stops[0]["station"] + stops[1]["station"]) / 2

# Im gesamten Abschnitt gibt es genau eine Stelle, an der die Erzabt-Klotz-
# Strasse gequert werden kann: die Bedarfsampel an der Kreuzung. Der
# Zebrastreifen bei 13.048834 liegt auf Weg 138365059, also auf dem westlichen
# Ast der Erzabt-Klotz-Strasse jenseits der Nonntaler Hauptstrasse, und quert
# diesen Abschnitt nicht. Die Querung bei der Peregrinstrasse quert laut OSM
# die Peregrinstrasse (Nebenstrasse), nicht die Hauptfahrbahn.
CROSSINGS = [
    ("Bedarfsampel über die Erzabt-Klotz-Straße", (47.792562, 13.052117), "ampel"),
]
crossings = []
for label, p, kind in CROSSINGS:
    st, _, _ = project_on_corridor(p)
    crossings.append(
        {
            "label": label,
            "art": kind,
            "lat": p[0],
            "lon": p[1],
            "station": round(st, 1),
        }
    )

for s in stops:
    opts = [(abs(c["station"] - s["station"]), c) for c in crossings]
    opts.sort(key=lambda t: t[0])
    s["weg_zur_naechsten_querung_m"] = round(opts[0][0], 1)
    s["naechste_querung"] = opts[0][1]["label"]
    s["umweg_hin_und_zurueck_m"] = round(2 * opts[0][0], 1)

# ------------------------------------------------- Marken fuer die Lagekarte ---
# Nummeriert statt beschriftet: die Legende steht daneben im HTML, dadurch
# ueberlagern sich keine Texte und die Karte bleibt auf jedem Display lesbar.
MARKEN = [
    {
        "nr": 1,
        "lat": coord[N_SIGNAL][0],
        "lon": coord[N_SIGNAL][1],
        "farbe": "danger",
        "kurz": "Bedarfsampel, die einzige Querung",
        "lang": "Kreuzung Petersbrunnstraße/Akademiestraße. Die Bedarfsampel "
        "über die Erzabt-Klotz-Straße ist die einzige Stelle, an der dieser "
        "Abschnitt überquert werden kann.",
    },
    {
        # Beide Steige liegen einander gegenueber; bei rund einem Pixel je
        # Meter liessen sie sich nicht ohne Ueberlappung einzeln eintragen.
        "nr": 2,
        "lat": punkt_an(stops[0]["station"], 0)[0],
        "lon": punkt_an(stops[0]["station"], 0)[1],
        "farbe": "transit",
        "kurz": "Bushaltestellen, hier wird gequert",
        "lang": "Die Steige der Linien 5, 9 und 25 liegen einander gegenüber, "
        "der nordwestliche mit Wartehäuschen. Gequert wird auf dieser Höhe, "
        "über die gesamte Fahrbahn und ohne Übergang.",
    },
    {
        "nr": 3,
        "lat": punkt_an((KURVE_VON + KURVE_BIS) / 2, 0)[0],
        "lon": punkt_an((KURVE_VON + KURVE_BIS) / 2, 0)[1],
        "farbe": "danger",
        "kurz": "Kurve nach Süden",
        "lang": f'Am Ende der Geraden schwenkt die Landesstraße L 104 auf rund '
        f'{KURVE_LAENGE:.0f} Metern um {KURVE_WINKEL:.0f}° nach Süden in die '
        f'Nonntaler Hauptstraße; der Kurvenradius beträgt etwa '
        f'{KURVE_RADIUS:.0f} Meter. Der westliche Ast der Erzabt-Klotz-Straße '
        f'ist eine Nebenstraße.',
    },
    {
        "nr": 4,
        "lat": 47.79290,
        "lon": 13.05385,
        "farbe": "school",
        "kurz": "Schulen, Hochschule, Unipark",
        "lang": "Mehrere Bildungseinrichtungen nordöstlich der Kreuzung; "
        "der Weg dorthin führt über diesen Abschnitt.",
    },
]

# -------------------------------------------------------------- Anhaltewege ---
REAKTIONSZEIT = 1.0  # s, uebliche Annahme fuer aufmerksame Lenker
VERZOEGERUNG = 8.0  # m/s^2, Gefahrenbremsung auf trockenem Asphalt


def anhalteweg(kmh):
    """Reaktions- und Bremsweg.

    Beide Teilwerte werden zuerst gerundet und erst dann addiert, damit die
    Summe in der Grafik zu den angezeigten Teilstrecken passt. Sonst steht in
    der Zeichnung 8,3 + 4,3 = 12,7, und jemand rechnet nach.
    """
    v = kmh / 3.6
    reak = round(v * REAKTIONSZEIT, 1)
    brems = round(v * v / (2 * VERZOEGERUNG), 1)
    return {
        "kmh": kmh,
        "reaktionsweg_m": reak,
        "bremsweg_m": brems,
        "anhalteweg_m": round(reak + brems, 1),
    }


SPEEDS = [anhalteweg(k) for k in (30, 50, 60)]
A30 = SPEEDS[0]["anhalteweg_m"]


def restgeschwindigkeit(kmh, weg):
    """Geschwindigkeit nach 'weg' Metern bei Gefahrenbremsung, in km/h."""
    v = kmh / 3.6
    if weg <= v * REAKTIONSZEIT:
        return kmh  # noch in der Reaktionsphase, ungebremst
    s = weg - v * REAKTIONSZEIT
    v2 = v * v - 2 * VERZOEGERUNG * s
    return round(max(0.0, math.sqrt(max(0.0, v2))) * 3.6, 1)


REST_BEI_A30 = {s["kmh"]: restgeschwindigkeit(s["kmh"], A30) for s in SPEEDS}

# Fahrzeit ueber die Gerade
FAHRZEIT = {
    k: round(STRAIGHT_LEN / (k / 3.6), 1) for k in (30, 50)
}
ZEITGEWINN = round(FAHRZEIT[30] - FAHRZEIT[50], 1)

# ------------------------------------------- Tempolimits aus den OSM-Tags ---
limits = {}
for wid in CORRIDOR_WAYS:
    t = ways[wid]["tags"]
    limits[wid] = t.get("maxspeed", "–")
QUERSCHNITT = ways[314950230]["tags"]

# ------------------------------------------------ Schutzbeduerftige Ziele ---
# Aus daten/poi.json. Die Overpass-Abfrage holt grosszuegig im Umkreis von
# 900 m; gefiltert wird hier auf die Luftlinie zur Mitte des Abschnitts.
# OSM fuehrt grosse Standorte teils mehrfach, deshalb die Entdopplung unten.
UMKREIS_M = 600
SCHUTZARTEN = {
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


def dist_korridor(lat, lon):
    """Luftlinie zum naechstgelegenen Punkt des betroffenen Abschnitts."""
    return project_on_corridor((lat, lon))[1]


ZIELE = []
_seen = set()
for e in poi["elements"]:
    t = e.get("tags", {})
    c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
    if not c.get("lat"):
        continue
    # social_facility=retirement_home ist aussagekraeftiger als amenity
    kind = t.get("social_facility") or t.get("amenity") or t.get("leisure")
    if kind not in SCHUTZARTEN:
        continue
    name = t.get("name")
    if not name:
        continue
    if dist_korridor(c["lat"], c["lon"]) > UMKREIS_M:
        continue
    # OSM fuehrt denselben Campus mehrfach; zu einem Eintrag zusammenfassen
    if any(w in name for w in ("Unipark", "Universität Salzburg", "Hochschülerschaft")):
        name, kind, key = "Universitätscampus Unipark Nonntal", "university", "unipark"
    else:
        key = name.split(" ")[0].lower()
    if key in _seen:
        continue
    _seen.add(key)
    ZIELE.append(
        {
            "name": name,
            "art": kind,
            "entfernung_m": round(dist_korridor(c["lat"], c["lon"])),
        }
    )
# Nicht jede OSM-"school" ist eine Schule fuer Kinder: Hochschulen und
# Ausbildungsstaetten fuer Erwachsene werden getrennt gezaehlt, weil die
# StVO-Novelle auf das Umfeld von Schulen und Kindergaerten abstellt.
ERWACHSENENBILDUNG = (
    "Pädagogische Hochschule",
    "Schule für Sozialbetreuungsberufe",
    "Universitätscampus",
    "Ausbildungszentrum",
    "Hochschülerschaft",
)
for z in ZIELE:
    if z["art"] in ("school", "kindergarten"):
        z["stufe"] = (
            "erwachsene"
            if any(w in z["name"] for w in ERWACHSENENBILDUNG)
            else "kinder"
        )
    elif z["art"] == "university":
        z["stufe"] = "erwachsene"
ZIELE.sort(key=lambda z: z["entfernung_m"])
KINDER_EINRICHTUNGEN = [z for z in ZIELE if z.get("stufe") == "kinder"]
KINDER_SCHULEN = [z for z in KINDER_EINRICHTUNGEN if z["art"] == "school"]
KINDER_NAECHSTE = min((z["entfernung_m"] for z in KINDER_EINRICHTUNGEN), default=None)
ANZAHL = {}
for z in ZIELE:
    ANZAHL[z["art"]] = ANZAHL.get(z["art"], 0) + 1

# ================================================================= Palette ===
# Die Palette ist aus der Welt des Gegenstands abgeleitet: Asphalt bei
# Tageslicht als Grund, das Rot der oesterreichischen Verbotszeichen als
# Signalfarbe, das Blau der Strassentafeln fuer den oeffentlichen Verkehr.
# Die Neutraltoene sind bewusst kuehl, nicht cremefarben.
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
    """<style>-Block fuer die eigenstaendigen SVG-Dateien (Fallback)."""
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


def de(x, n=1):
    """Zahl mit deutschem Dezimalkomma."""
    return f"{x:.{n}f}".replace(".", ",")


# ======================================================== 1. Lagekarte ======
VIEW = dict(lat0=47.79070, lat1=47.79400, lon0=13.04700, lon1=13.05470)
VW = (VIEW["lon1"] - VIEW["lon0"]) * KX
VH = (VIEW["lat1"] - VIEW["lat0"]) * R


def xy(p):
    """(lat,lon) -> SVG-Koordinaten der Lagekarte, 1 Einheit = 1 Meter."""
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


def strassenlabel(name, blocker, box=None, nur_wege=None, schrift=9.0):
    """Beschriftung entlang der echten Strassengeometrie platzieren.

    Sucht auf dem Strassenverlauf die Stelle mit dem groessten Abstand zu den
    bereits gesetzten Marken und Beschriftungen. Liefert (x, y, winkel) oder
    None, wenn im Kartenausschnitt kein freier Platz bleibt.
    """
    halb = 0.27 * schrift * len(name)  # halbe Textbreite, grob geschaetzt
    kandidaten = []
    quelle = (
        [ways[w] for w in nur_wege if w in ways]
        if nur_wege
        else [w for w in ways.values() if w.get("tags", {}).get("name") == name]
    )
    for w in quelle:
        g = w.get("geometry") or []
        for i in range(len(g) - 1):
            a = xy((g[i]["lat"], g[i]["lon"]))
            b = xy((g[i + 1]["lat"], g[i + 1]["lon"]))
            seg = math.hypot(b[0] - a[0], b[1] - a[1])
            if seg < 1:
                continue
            ux, uy = (b[0] - a[0]) / seg, (b[1] - a[1]) / seg
            schritt = 6.0
            t = 0.0
            while t <= seg:
                kandidaten.append((a[0] + ux * t, a[1] + uy * t, ux, uy))
                t += schritt
    bestes = None
    for px, py, ux, uy in kandidaten:
        # Der gesamte Text muss im Ausschnitt liegen
        proben = [
            (px + ux * s, py + uy * s) for s in (-halb, -halb / 2, 0, halb / 2, halb)
        ]
        if any(
            x < 14 or x > VW - 14 or y < 16 or y > VH - 58 for x, y in proben
        ):
            continue
        if box and any(
            box[0] - 10 < x < box[0] + box[2] + 10
            and box[1] - 10 < y < box[1] + box[3] + 10
            for x, y in proben
        ):
            continue
        abstand = min(
            math.hypot(x - bx, y - by) for x, y in proben for bx, by in blocker
        )
        if bestes is None or abstand > bestes[0]:
            bestes = (abstand, px, py, ux, uy)
    if not bestes or bestes[0] < 17:
        return None
    _, px, py, ux, uy = bestes
    if ux < 0:  # Text immer von links nach rechts lesbar
        ux, uy = -ux, -uy
    return px, py, math.degrees(math.atan2(uy, ux))


def lagekarte(standalone=False):
    o = []
    # In der eigenstaendigen Datei steht die Legende in einem Band unter der
    # Karte, damit sie nichts verdeckt. Im HTML steht sie daneben.
    legende_h = 132 if standalone else 0
    o.append(
        f'<svg viewBox="0 0 {VW:.0f} {VH + legende_h:.0f}" '
        f'xmlns="http://www.w3.org/2000/svg" class="karte karte--geo" '
        f'role="img" aria-labelledby="geo-titel geo-desc">'
    )
    o.append('<title id="geo-titel">Lageplan Erzabt-Klotz-Straße, Salzburg-Nonntal</title>')
    o.append(
        '<desc id="geo-desc">Maßstäblicher Lageplan aus OpenStreetMap-Daten. '
        f'Hervorgehoben: der {STRAIGHT_LEN:.0f} Meter lange gerade Abschnitt der '
        'Erzabt-Klotz-Straße zwischen der Ampelkreuzung '
        'Petersbrunnstraße/Akademiestraße und der Kurve zur Nonntaler '
        'Hauptstraße, die beiden Bushaltestellen auf gegenüberliegenden '
        'Straßenseiten und die nächsten legalen Querungsstellen.</desc>'
    )
    if standalone:
        o.append(svg_style())
    o.append(
        f'<rect width="{VW:.0f}" height="{VH + legende_h:.0f}" fill="{c("paper")}"/>'
    )
    o.append(f'<clipPath id="kv"><rect width="{VW:.0f}" height="{VH:.0f}"/></clipPath>')
    o.append('<g clip-path="url(#kv)">')

    # Gruenflaechen
    for w in ways.values():
        t = w.get("tags", {})
        if not in_view(w):
            continue
        if t.get("leisure") == "park" or t.get("landuse") in ("grass", "forest", "cemetery"):
            o.append(f'<path d="{d_of(w.get("geometry"), True)}" fill="{c("green")}"/>')

    # Gebaeude
    o.append(f'<g fill="{c("bldg")}" stroke="{c("bldgline")}" stroke-width="0.6">')
    for w in ways.values():
        t = w.get("tags", {})
        if "building" in t and in_view(w):
            o.append(f'<path d="{d_of(w.get("geometry"), True)}"/>')
    o.append("</g>")

    # Fusswege
    o.append(
        f'<g fill="none" stroke="{c("foot")}" stroke-width="1.5" '
        f'stroke-dasharray="3 2.5" stroke-linecap="round" opacity="0.75">'
    )
    for w in ways.values():
        t = w.get("tags", {})
        if t.get("highway") in ("footway", "path", "steps", "cycleway") and in_view(w):
            o.append(f'<path d="{d_of(w.get("geometry"))}"/>')
    o.append("</g>")

    # Fahrbahnen: erst Bordkante, dann Fahrbahn
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

    # Der betroffene Abschnitt
    corridor_d = f"M{xy(pts[0])[0]:.1f} {xy(pts[0])[1]:.1f}" + "".join(
        f"L{xy(p)[0]:.1f} {xy(p)[1]:.1f}" for p in pts[1:]
    )
    # Nur ein ruhiges Band. Eine zusaetzliche gestrichelte Linie darueber und
    # die frueher eingezeichnete Querungslinie zwischen den Steigen liefen fast
    # parallel zur Strasse und sahen wie ein Zeichenfehler aus. Die Querung
    # zeigt ohnehin das Querungsdiagramm deutlicher.
    o.append(
        f'<path d="{corridor_d}" fill="none" stroke="{c("danger")}" '
        f'stroke-width="12.5" opacity="0.26" stroke-linecap="butt"/>'
    )
    o.append(
        f'<path d="{corridor_d}" fill="none" stroke="{c("danger")}" '
        f'stroke-width="1.6" opacity="0.55"/>'
    )

    o.append("</g>")  # clip

    # ---- Schulcluster hinterlegen
    schul = (47.79290, 13.05385)
    sx, sy = xy(schul)
    o.append(
        f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="30" fill="{c("school")}" '
        f'opacity="0.15"/>'
    )

    # ---- Beschriftungen entlang der echten Geometrie platzieren
    box = None  # die Legende verdeckt die Karte nicht mehr
    blocker = [xy((mk["lat"], mk["lon"])) for mk in MARKEN]
    blocker.append((sx, sy))  # Schulcluster-Kreis

    def setze(txt, schrift, farbe, gewicht, spacing, **kw):
        pos = strassenlabel(txt, blocker, box, schrift=schrift, **kw)
        if not pos:
            return ""
        x, y, rot = pos
        # Die gesetzte Beschriftung blockiert nachfolgende
        blocker.extend(
            [(x, y), (x - 20 * math.cos(math.radians(rot)),
                      y - 20 * math.sin(math.radians(rot))),
             (x + 20 * math.cos(math.radians(rot)),
              y + 20 * math.sin(math.radians(rot)))]
        )
        return (
            f'<text x="{x:.1f}" y="{y:.1f}" '
            f'transform="rotate({rot:.1f} {x:.1f} {y:.1f})" text-anchor="middle" '
            f'{FONT} font-size="{schrift}" font-weight="{gewicht}" '
            f'letter-spacing="{spacing}" fill="{farbe}" paint-order="stroke" '
            f'stroke="{c("paper")}" stroke-width="3.2" stroke-linejoin="round">'
            f'{esc(txt)}</text>'
        )

    o.append(
        setze("Erzabt-Klotz-Straße", 9.0, c("inksoft"), 600, 0.3,
              nur_wege=[314950230, 134631797])
    )
    for strasse in (
        "Nonntaler Hauptstraße",
        "Petersbrunnstraße",
        "Akademiestraße",
        "Fürstenallee",
        "Wäschergasse",
    ):
        o.append(setze(strasse, 9.0, c("inksoft"), 600, 0.3))

    # ---- Nummerierte Marken; die Legende steht im HTML daneben
    o.append('<g class="marken">')
    for mk in MARKEN:
        x, y = xy((mk["lat"], mk["lon"]))
        col = c(mk["farbe"])
        o.append(
            f'<g class="marke" data-nr="{mk["nr"]}" tabindex="0" role="listitem" '
            f'aria-label="{esc(str(mk["nr"]))}. {esc(mk["kurz"])}">'
            f'<circle class="marke__halo" cx="{x:.1f}" cy="{y:.1f}" r="9" '
            f'fill="{col}" opacity="0"/>'
            f'<circle class="marke__ring" cx="{x:.1f}" cy="{y:.1f}" r="9" '
            f'fill="{c("paper")}" stroke="{col}" stroke-width="2.6"/>'
            f'<text class="marke__nr" x="{x:.1f}" y="{y + 3.6:.1f}" '
            f'text-anchor="middle" {FONT} font-size="10.5" font-weight="700" '
            f'fill="{col}">{mk["nr"]}</text></g>'
        )
    o.append("</g>")

    # ---- Nordpfeil, Massstab, Quellenangabe
    o.append(
        f'<g opacity="0.8"><path d="M26 {VH-54:.0f} L26 {VH-76:.0f} '
        f'M21 {VH-69:.0f} L26 {VH-76:.0f} L31 {VH-69:.0f}" fill="none" '
        f'stroke="{c("ink")}" stroke-width="1.6" stroke-linecap="round" '
        f'stroke-linejoin="round"/>'
        f'<text x="26" y="{VH-41:.0f}" text-anchor="middle" {FONT} font-size="9" '
        f'font-weight="700" fill="{c("ink")}">N</text></g>'
    )
    o.append(
        f'<g><path d="M62 {VH-46:.0f} h100" stroke="{c("ink")}" stroke-width="2.4"/>'
        f'<path d="M62 {VH-51:.0f} v10 M112 {VH-50:.0f} v8 M162 {VH-51:.0f} v10" '
        f'stroke="{c("ink")}" stroke-width="1.4"/>'
        f'<text x="62" y="{VH-54:.0f}" {FONT} font-size="9" font-weight="600" '
        f'fill="{c("ink")}">0</text>'
        f'<text x="162" y="{VH-54:.0f}" text-anchor="middle" {FONT} font-size="9" '
        f'font-weight="600" fill="{c("ink")}">100 m</text></g>'
    )
    o.append(
        f'<text x="20" y="{VH-8:.0f}" {FONT} font-size="8" fill="{c("inksoft")}">'
        f'Geometrie: OpenStreetMap-Mitwirkende (ODbL) · Darstellung: daten/build.py'
        f'</text>'
    )

    # ---- Legendenband unter der Karte (nur in der eigenstaendigen Datei)
    if standalone:
        o.append(
            f'<path d="M0 {VH:.0f} H{VW:.0f}" stroke="{c("grid")}" '
            f'stroke-width="1.4"/>'
        )
        for i, mk in enumerate(MARKEN):
            spalte, zeile = divmod(i, 4)
            lx = 24 + spalte * (VW - 48) / 2
            ly = VH + 30 + zeile * 25
            o.append(
                f'<circle cx="{lx + 9:.0f}" cy="{ly - 4:.0f}" r="8.4" fill="none" '
                f'stroke="{c(mk["farbe"])}" stroke-width="2.2"/>'
                f'<text x="{lx + 9:.0f}" y="{ly - 0.6:.0f}" text-anchor="middle" '
                f'{FONT} font-size="10" font-weight="700" '
                f'fill="{c(mk["farbe"])}">{mk["nr"]}</text>'
                f'<text x="{lx + 26:.0f}" y="{ly:.0f}" {FONT} font-size="11" '
                f'fill="{c("ink")}">{esc(mk["kurz"])}</text>'
            )
    o.append("</svg>")
    return "".join(o)


# ============================================ 2. Querungsdiagramm (Band) ====
QW, QH = 980, 322
QX0 = 70          # linker Rand
QRAND = 48        # rechter Rand fuer die Beschriftung "Meter"
QSC = (QW - QX0 - QRAND) / CORRIDOR_LEN  # Pixel pro Meter, passt sich an
Y_TOP, Y_BOT = 86.0, 138.0  # Fahrbahnoberkante / -unterkante
GEH = 10.0  # Gehsteigbreite


def qx(station):
    return QX0 + station * QSC


def querungsdiagramm(standalone=False):
    o = []
    o.append(
        f'<svg viewBox="0 0 {QW} {QH}" xmlns="http://www.w3.org/2000/svg" '
        f'class="karte karte--quer" role="img" aria-labelledby="qd-titel qd-desc">'
    )
    o.append('<title id="qd-titel">Querungsmöglichkeiten im Längsschnitt</title>')
    o.append(
        '<desc id="qd-desc">Die Erzabt-Klotz-Straße gerade ausgerichtet, '
        'maßstäblich gestationiert. Die beiden Bushaltestellen liegen '
        f'auf gegenüberliegenden Straßenseiten. Zwischen '
        'ihnen gibt es keine Querungsmöglichkeit; die nächsten legalen Übergänge '
        f'liegen {stops[0]["weg_zur_naechsten_querung_m"]:.0f} und '
        f'{stops[1]["weg_zur_naechsten_querung_m"]:.0f} Meter entfernt.</desc>'
    )
    if standalone:
        o.append(svg_style())
    o.append(f'<rect width="{QW}" height="{QH}" fill="{c("paper")}"/>')

    top, bot = Y_TOP, Y_BOT
    xl, xr = qx(0), qx(CORRIDOR_LEN)
    o.append(
        f'<defs><marker id="qpfeil" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse">'
        f'<path d="M0 0 L10 5 L0 10 z" fill="{c("danger")}"/></marker>'
        f'<marker id="qmass" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
        f'<path d="M0 0 L10 5 L0 10 z" fill="{c("inksoft")}"/></marker></defs>'
    )

    # ---- Enden benennen
    o.append(
        f'<path d="M{xl:.0f} 32 V{bot + GEH + 4:.0f}" stroke="{c("inksoft")}" '
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

    # ---- Massband fuer die Gerade
    ym = 58
    xs1, xs2 = qx(STRAIGHT_FROM), qx(STRAIGHT_TO)
    o.append(
        f'<path d="M{xs1:.0f} {ym} H{xs2:.0f}" stroke="{c("inksoft")}" '
        f'stroke-width="1.2" marker-start="url(#qmass)" marker-end="url(#qmass)"/>'
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
        f'Richtungsabweichung ±{de(STRAIGHT_SPREAD)}°</text>'
    )

    # ---- Gehsteige und Fahrbahn
    for y in (top - GEH, bot):
        o.append(
            f'<rect x="{xl:.0f}" y="{y:.1f}" width="{xr-xl:.0f}" height="{GEH}" '
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
    # drei Fahrstreifen (lanes=3: je ein Fahrstreifen plus Busspur)
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

    # ---- Querungen
    for cr in crossings:
        x = qx(cr["station"])
        o.append(
            f'<path d="M{x:.0f} {top:.1f} V{bot:.1f}" stroke="{c("good")}" '
            f'stroke-width="3.4" stroke-dasharray="5 3.5"/>'
        )
        o.append(
            f'<circle cx="{x:.0f}" cy="{top-GEH-11:.0f}" r="7" fill="{c("paper")}" '
            f'stroke="{c("good")}" stroke-width="2.2"/>'
            f'<text x="{x:.0f}" y="{top-GEH-7.6:.0f}" text-anchor="middle" {FONT} '
            f'font-size="8" font-weight="700" fill="{c("good")}">A</text>'
        )

    # ---- Haltestellen auf den Gehsteigen
    for s in stops:
        x = qx(s["station"])
        oben = s["seite_sign"] < 0
        y = top - GEH if oben else bot
        o.append(
            f'<rect x="{x-15:.0f}" y="{y:.1f}" width="30" height="{GEH}" '
            f'rx="1.5" fill="{c("transit")}"/>'
        )
        o.append(
            f'<text x="{x:.0f}" y="{y - 7 if oben else y + GEH + 14:.0f}" '
            f'text-anchor="middle" {FONT} font-size="10" font-weight="700" '
            f'fill="{c("transit")}">{esc(s["label"].replace("Haltestelle ", "Bus "))}'
            f'</text>'
        )

    # ---- Gequert wird quer zur Fahrbahn, auf Hoehe der Haltestellen.
    # Liegen beide Steige einander gegenueber, genuegt eine Linie.
    for x in sorted({round(qx(s["station"])) for s in stops}):
        o.append(
            f'<path d="M{x:.0f} {bot - 1:.0f} V{top + 1:.0f}" '
            f'stroke="{c("danger")}" stroke-width="2.8" stroke-dasharray="2.5 4.5" '
            f'stroke-linecap="round" marker-end="url(#qpfeil)" '
            f'marker-start="url(#qpfeil)"/>'
        )
    xm = (qx(stops[0]["station"]) + qx(stops[1]["station"])) / 2
    ly = bot + GEH + 36
    o.append(
        f'<path d="M{qx(stops[1]["station"]):.0f} {bot + GEH + 2:.0f} '
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

    # ---- Umwegklammern
    def klammer(x1, x2, y, text):
        return (
            f'<path d="M{x1:.0f} {y-6:.0f} V{y:.0f} H{x2:.0f} V{y-6:.0f}" '
            f'fill="none" stroke="{c("danger")}" stroke-width="1.4"/>'
            f'<text x="{(x1+x2)/2:.0f}" y="{y+14:.0f}" text-anchor="middle" {FONT} '
            f'font-size="11" font-weight="700" fill="{c("danger")}">{esc(text)}</text>'
        )

    yk = 244
    luecke = CORRIDOR_LEN - crossings[0]["station"]
    o.append(
        klammer(qx(crossings[0]["station"]), qx(CORRIDOR_LEN), yk,
                f'{luecke:.0f} m ohne gesicherte Querung')
    )

    # ---- Stationierung
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
        f'OpenStreetMap-Geometrie berechnet · daten/build.py</text>'
    )
    o.append("</svg>")
    return "".join(o)


# ============================================== 3. Anhaltewege vergleichen ==
AW, AH = 980, 352
ASC = 22.0  # Pixel pro Meter
AX0 = 150


def anhaltediagramm(standalone=False):
    o = []
    o.append(
        f'<svg viewBox="0 0 {AW} {AH}" xmlns="http://www.w3.org/2000/svg" '
        f'class="karte karte--halt" role="img" aria-labelledby="ad-titel ad-desc">'
    )
    o.append('<title id="ad-titel">Anhaltewege bei 30, 50 und 60 km/h</title>')
    desc = "; ".join(
        f'{s["kmh"]} km/h: {s["anhalteweg_m"]:.0f} Meter' for s in SPEEDS
    )
    o.append(
        f'<desc id="ad-desc">Vergleich der Anhaltewege: {desc}. An der Stelle, '
        f'an der ein Fahrzeug mit 30 km/h bereits steht, hat ein Fahrzeug mit '
        f'50 km/h die Bremsung noch nicht begonnen.</desc>'
    )
    if standalone:
        o.append(svg_style())
    o.append(f'<rect width="{AW}" height="{AH}" fill="{c("paper")}"/>')

    rows = [68, 140, 212]
    bh = 30

    # Meterraster
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
        wr = s["reaktionsweg_m"] * ASC
        wb = s["bremsweg_m"] * ASC
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
            f'font-weight="700" fill="{col}">{s["anhalteweg_m"]:.0f} m</text>'
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

    # Die Linie, an der das 30er-Fahrzeug steht
    xs = AX0 + A30 * ASC
    yb = rows[-1] + bh
    o.append(
        f'<path d="M{xs:.1f} 44 V{yb+26:.0f}" stroke="{c("ink")}" '
        f'stroke-width="2" stroke-dasharray="6 4"/>'
    )
    # Fussgaengersymbol auf der Haltelinie
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
        f'{REST_BEI_A30[50]:.0f} km/h.</text>'
    )
    o.append(
        f'<text x="{AW/2:.0f}" y="{AH-10:.0f}" text-anchor="middle" {FONT} '
        f'font-size="9" fill="{c("inksoft")}">Annahmen: Reaktionszeit '
        f'{de(REAKTIONSZEIT)} s, Gefahrenbremsung {VERZOEGERUNG:.0f} m/s² '
        f'(trockener Asphalt) · Rechenweg in daten/build.py</text>'
    )
    o.append("</svg>")
    return "".join(o)


# ================================================================ Schreiben ==
def js_string(s):
    return s.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


karten = {
    "KARTE_GEO": lagekarte,
    "KARTE_QUER": querungsdiagramm,
    "KARTE_HALT": anhaltediagramm,
}

js = [
    "/* Automatisch erzeugt von daten/build.py, nicht von Hand bearbeiten. */",
    "/* Geometrie: OpenStreetMap-Mitwirkende, ODbL. */",
]
for name, fn in karten.items():
    js.append(f"const {name} = `{js_string(fn(standalone=False))}`;")
js.append(
    "window.KARTEN = { geo: KARTE_GEO, quer: KARTE_QUER, halt: KARTE_HALT };"
)
# Legende der Lagekarte: eine Quelle fuer SVG und HTML
js.append(
    "window.MARKEN = "
    + json.dumps(
        [
            {k: mk[k] for k in ("nr", "farbe", "kurz", "lang")}
            for mk in MARKEN
        ],
        ensure_ascii=False,
    )
    + ";"
)
# Schutzbeduerftige Ziele fuer die Tabelle auf der Seite
ARTEN = {
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
    "window.ZIELE = "
    + json.dumps(
        [
            {"name": z["name"], "art": ARTEN.get(z["art"], z["art"]),
             "m": z["entfernung_m"]}
            for z in ZIELE
        ],
        ensure_ascii=False,
    )
    + ";"
)
with open(os.path.join(ASSETS, "karten.js"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(js) + "\n")

# Farbpalette als CSS, damit Seite und Grafiken nie auseinanderlaufen
def _vars(i, einzug):
    return "\n".join(f"{einzug}--k-{k}: {v[i]};" for k, v in PAL.items())


with open(os.path.join(ASSETS, "palette.css"), "w", encoding="utf-8") as fh:
    fh.write(
        "/* Automatisch erzeugt von daten/build.py, nicht von Hand bearbeiten. */\n"
        "/* Dieselben Farben verwenden die SVG-Grafiken in karten.js. */\n\n"
        ":root {\n" + _vars(0, "  ") + "\n  color-scheme: light dark;\n}\n\n"
        "@media (prefers-color-scheme: dark) {\n"
        "  :root:not([data-theme=\"light\"]) {\n" + _vars(1, "    ") + "\n  }\n}\n\n"
        ":root[data-theme=\"dark\"] {\n" + _vars(1, "  ") + "\n}\n\n"
        ":root[data-theme=\"light\"] {\n" + _vars(0, "  ") + "\n}\n"
    )

for fname, fn in [
    ("karte-geo.svg", lagekarte),
    ("karte-querung.svg", querungsdiagramm),
    ("karte-anhalteweg.svg", anhaltediagramm),
]:
    with open(os.path.join(ASSETS, fname), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n' + fn(standalone=True) + "\n")

# ------------------------------------------------- Bebauung am Korridor ---
# Belegt, dass hier eine dreistreifige Hauptstrasse durch ein Wohngebiet
# fuehrt. Kleine Nebengebaeude (Wartehaeuschen, Trafo, Schuppen) werden ueber
# die Grundflaeche ausgeschlossen - das OSM-Objekt mit dem geringsten Abstand
# ist ein 7 m2 grosses "roof", naemlich das Wartehaeuschen der Haltestelle.
WOHNARTEN = {"residential", "apartments", "house", "detached", "terrace", "yes"}
MIN_FLAECHE = 60  # m2, darunter als Nebengebaeude gewertet

anrainer = []
for w in ways.values():
    t = w.get("tags", {})
    if t.get("building") not in WOHNARTEN:
        continue
    g = w.get("geometry") or []
    if not g:
        continue
    e_pts = [en((q["lat"], q["lon"])) for q in g]
    flaeche = abs(
        sum(
            e_pts[i][0] * e_pts[i + 1][1] - e_pts[i + 1][0] * e_pts[i][1]
            for i in range(len(e_pts) - 1)
        )
    ) / 2
    if flaeche < MIN_FLAECHE:
        continue
    # nach Abstand suchen, nicht nach Stationierung
    nah = min(
        (project_on_corridor((q["lat"], q["lon"])) for q in g),
        key=lambda r: r[1],
    )
    abstand, station = nah[1], nah[0]
    if abstand < 45:
        anrainer.append(
            {
                "abstand_achse_m": round(abstand, 1),
                "station_m": round(station),
                "art": t.get("building"),
                "grundflaeche_m2": round(flaeche),
                "geschosse": t.get("building:levels"),
                "adresse": " ".join(
                    x for x in (t.get("addr:street"), t.get("addr:housenumber")) if x
                ) or None,
            }
        )
anrainer.sort(key=lambda a: a["abstand_achse_m"])
# Fuer die Aussage "naechstes Wohnhaus" nur eindeutig Wohnliches heranziehen;
# das generische building=yes bleibt dabei aussen vor.
EINDEUTIG_WOHNEN = {"residential", "apartments", "house", "detached", "terrace"}
_wohn = [a for a in anrainer if a["art"] in EINDEUTIG_WOHNEN]
NAECHSTES_WOHNHAUS = _wohn[0] if _wohn else None
# Fahrbahnhalbbreite grob aus der Fahrstreifenzahl (3 x rund 3,3 m)
FAHRBAHN_B = 3 * 3.3
RAND_BIS_FASSADE = (
    round(NAECHSTES_WOHNHAUS["abstand_achse_m"] - FAHRBAHN_B / 2, 1)
    if NAECHSTES_WOHNHAUS else None
)

# ----------------------------------------------- Fotostandorte ableiten ---
# Damit eigene Aufnahmen zu den Diagrammen passen, werden Standort und
# Blickrichtung aus der Korridorgeometrie gerechnet statt geschaetzt.
BLICK_NO = bearings[sj - 1] - 180  # entlang der Geraden nach Nordosten
BLICK_NO = BLICK_NO % 360
BLICK_SW = (BLICK_NO + 180) % 360
BLICK_SO = (BLICK_NO + 90) % 360  # quer ueber die Fahrbahn
BLICK_NW = (BLICK_NO + 270) % 360

STANDORTE = [
    ("Ampelkreuzung, Blick nach Südwesten", coord[N_SIGNAL], BLICK_SW,
     "Der gesamte gerade Abschnitt in einem Bild, bis zur Kurve."),
    (f'{stops[1]["label"]}, quer über die Fahrbahn',
     (stops[1]["steig_lat"], stops[1]["steig_lon"]), BLICK_SO,
     "Die Querung, die hier täglich stattfindet: drei Fahrstreifen, kein Übergang."),
    (f'{stops[1]["label"]}, Blick nach Nordosten',
     (stops[1]["steig_lat"], stops[1]["steig_lon"]), BLICK_NO,
     f'Zeigt, wie weit die Bedarfsampel entfernt ist '
     f'({stops[1]["weg_zur_naechsten_querung_m"]:.0f} m).'),
    (f'{stops[0]["label"]}, quer über die Fahrbahn',
     (stops[0]["steig_lat"], stops[0]["steig_lon"]), BLICK_NW,
     "Dieselbe Situation von der anderen Seite."),
    ("Kurve, Blick nach Nordosten", coord[N_KURVE], BLICK_NO,
     "Die Gerade vom südwestlichen Ende aus, die Sicht der Zufahrenden."),
    ("Bedarfsampel an der Kreuzung",
     (crossings[0]["lat"], crossings[0]["lon"]), BLICK_SW,
     "Drucktaster und Wartesituation; mit sichtbarer Uhr als Beleg der Wartezeit."),
]


def streetview(p, heading):
    return (f"https://www.google.com/maps/@?api=1&map_action=pano"
            f"&viewpoint={p[0]:.5f},{p[1]:.5f}&heading={heading:.0f}&pitch=0&fov=80")


zeilen = [
    "# Fotostandorte",
    "",
    "Automatisch erzeugt von `daten/build.py`. Standort und Blickrichtung sind",
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
for i, (titel, p, head, zweck) in enumerate(STANDORTE, 1):
    zeilen += [
        f"## {i}. {titel}",
        "",
        f"- **Standort:** `{p[0]:.5f}, {p[1]:.5f}`",
        f"- **Blickrichtung:** {head:.0f}° ({'Nordost' if head < 90 else 'Südost' if head < 180 else 'Südwest' if head < 270 else 'Nordwest'})",
        f"- **Zeigt:** {zweck}",
        f"- [In Street View ansehen]({streetview(p, head)})",
        "",
    ]
zeilen += [
    "---",
    "",
    "Beste Zeit für den Schulweg: werktags 7:15–8:00 Uhr und 12:00–13:30 Uhr.",
    "Querformat, und bitte ohne erkennbare Gesichter und Kennzeichen; Hinweise",
    "dazu in `medien/README.md`.",
    "",
]
with open(os.path.join(ROOT, "medien", "standorte.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(zeilen))

messwerte = {
    "quelle": "OpenStreetMap-Mitwirkende (ODbL), Abfragen in daten/overpass-*.ql",
    "fotostandorte": [
        {"titel": t, "lat": p[0], "lon": p[1], "blickrichtung_grad": round(h),
         "zweck": z}
        for t, p, h, z in STANDORTE
    ],
    "stand_osm": osm.get("osm3s", {}).get("timestamp_osm_base"),
    "korridor": {
        "beschreibung": "Erzabt-Klotz-Straße von der Ampelkreuzung "
        "Petersbrunnstraße/Akademiestraße bis in die Kurve zur Nonntaler Hauptstraße",
        "laenge_m": round(CORRIDOR_LEN, 1),
        "gerade_laenge_m": round(STRAIGHT_LEN, 1),
        "gerade_von_station_m": round(STRAIGHT_FROM, 1),
        "gerade_bis_station_m": round(STRAIGHT_TO, 1),
        "gerade_richtungsabweichung_grad": round(STRAIGHT_SPREAD, 1),
        "kurvenwinkel_grad": round(KURVE_WINKEL, 1),
        "tempolimit_osm": {str(k): v for k, v in limits.items()},
        "fahrstreifen": QUERSCHNITT.get("lanes"),
        "querschnitt_tags": {
            k: v
            for k, v in QUERSCHNITT.items()
            if k in ("lanes", "lanes:forward", "lanes:backward",
                     "lanes:psv:backward", "cycleway:left", "cycleway:right",
                     "sidewalk", "maxspeed", "ref", "trolley_wire")
        },
    },
    "haltestellen": stops,
    "versatz_der_haltestellen_m": round(STOP_GAP, 1),
    "querungen": crossings,
    "kartenmarken": MARKEN,
    "anhaltewege": {
        "annahmen": {
            "reaktionszeit_s": REAKTIONSZEIT,
            "verzoegerung_m_s2": VERZOEGERUNG,
            "hinweis": "Gefahrenbremsung auf trockenem Asphalt",
        },
        "werte": SPEEDS,
        "restgeschwindigkeit_bei_anhalteweg_30_kmh": REST_BEI_A30,
    },
    "fahrzeit_ueber_die_gerade_s": FAHRZEIT,
    "zeitverlust_durch_tempo_30_s": ZEITGEWINN,
    "bebauung": {
        "hinweis": "Wohngebäude mit mehr als 60 m² Grundfläche, Abstand zur Straßenachse unter 45 m",
        "anzahl_gebaeude": len(anrainer),
        "anzahl_wohngebaeude": len(_wohn),
        "naechstes_wohngebaeude": NAECHSTES_WOHNHAUS,
        "fahrbahnbreite_geschaetzt_m": FAHRBAHN_B,
        "fahrbahnrand_bis_naechster_fassade_m": RAND_BIS_FASSADE,
        "liste": anrainer,
    },
    "schutzbeduerftige_ziele_im_umkreis_600m": ZIELE,
    "anzahl_nach_art": ANZAHL,
    "bildung_nach_stufe": {
        "schulen_fuer_kinder": len(KINDER_SCHULEN),
        "kindergaerten": len([z for z in KINDER_EINRICHTUNGEN
                              if z["art"] == "kindergarten"]),
        "erwachsenenbildung": len([z for z in ZIELE
                                   if z.get("stufe") == "erwachsene"]),
        "naechste_kindereinrichtung_m": KINDER_NAECHSTE,
    },
}
with open(os.path.join(HERE, "messwerte.json"), "w", encoding="utf-8") as fh:
    json.dump(messwerte, fh, ensure_ascii=False, indent=2)

# ------------------------------------------------------------------ Bericht ---
print(f"Korridor Ampel → Kurve            {CORRIDOR_LEN:7.1f} m")
print(f"  davon gerade (±{STRAIGHT_SPREAD:.1f}°)         {STRAIGHT_LEN:7.1f} m"
      f"  (Station {STRAIGHT_FROM:.0f}–{STRAIGHT_TO:.0f})")
print(f"  Knick in die Nonntaler Hauptstr.  {KURVE_WINKEL:5.1f}°")
print(f"  Tempolimit Korridor               {sorted(set(limits.values()))}")
print(f"Haltestellenversatz               {STOP_GAP:7.1f} m")
for s in stops:
    print(f"  {s['label']:28s} Station {s['station']:6.1f} m, {s['seite']:8s}"
          f" → {s['weg_zur_naechsten_querung_m']:5.1f} m zur nächsten Querung")
print(f"Anhaltewege  " + "   ".join(
    f"{s['kmh']}:{s['anhalteweg_m']:.1f}m" for s in SPEEDS))
print(f"  Resttempo bei {A30:.1f} m        " + "  ".join(
    f"{k}→{v:.0f}" for k, v in REST_BEI_A30.items()))
print(f"Fahrzeit über die Gerade          "
      f"50: {FAHRZEIT[50]:.1f} s   30: {FAHRZEIT[30]:.1f} s"
      f"   Differenz {ZEITGEWINN:.1f} s")
print(f"Schutzbedürftige Ziele <600 m     {ANZAHL}")
print(f"  davon Schulen für Kinder        {len(KINDER_SCHULEN)}, nächste Kindereinrichtung {KINDER_NAECHSTE} m")
print(f"Wohngebäude < 45 m                {len(anrainer)}; nächstes "
      f"{NAECHSTES_WOHNHAUS['abstand_achse_m']} m "
      f"({NAECHSTES_WOHNHAUS['adresse']}), "
      f"rund {RAND_BIS_FASSADE} m ab Fahrbahnrand")
print()
print("geschrieben: assets/karten.js, assets/karte-*.svg, daten/messwerte.json")
