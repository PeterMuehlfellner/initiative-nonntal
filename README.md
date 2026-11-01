# Initiative Erzabt-Klotz-Straße

Eine statische Website zur Verkehrssituation in der Erzabt-Klotz-Straße in
Salzburg-Nonntal: 234 Meter nahezu gerade Fahrbahn mit Tempo 50 und 266 Meter ohne
Querungsmöglichkeit, zwischen zehn Bildungseinrichtungen. Eine seit Langem
bekannte Situation, nachgemessen.

Kein Build-Schritt, keine Abhängigkeiten, keine Tracker, keine Datenerhebung.
`index.html` im Browser öffnen genügt.

## Veröffentlichen

Den gesamten Ordner auf einen beliebigen Webspace legen, GitHub Pages, Netlify,
Uberspace, jeder Hosting-Tarif. Es gibt nichts zu kompilieren.

```bash
# lokal ansehen
python3 -m http.server 8000
# → http://localhost:8000
```

Vor dem Veröffentlichen unter eigener Domain bitte noch erledigen:

- [ ] **Impressum** in `index.html` ausfüllen (Platzhalter im Fußbereich,
      Pflicht nach § 5 ECG, sobald die Seite öffentlich erreichbar ist)
- [ ] **E-Mail-Adressen** im Abschnitt „Mitmachen" gegenprüfen
      (Stand der Recherche: Oktober 2026)
- [ ] **E-Mail-Adresse im Impressum** um Name und Wohnort ergänzen,
      sobald geklärt (§ 25 MedienG verlangt für natürliche Personen Name und
      Wohnort, keine Straßenanschrift)

Unabhängig davon, und nur **einmal** von **einer** Person zu senden:
`daten/ifg-anfrage.md`, ein Informationsbegehren nach dem
Informationsfreiheitsgesetz an die Stadt Salzburg. Es fragt die Verkehrsmengen,
Geschwindigkeits- und Lärmdaten ab, die auf der Seite derzeit fehlen. Vier
Wochen Frist.

## Aufbau

```
index.html              die Seite; Texte hier bearbeiten
assets/
  style.css             Layout und Typografie (von Hand)
  app.js                Legende, Hell/Dunkel, E-Mail-Entwurf (von Hand)
  palette.css           ← erzeugt: Farben, auch für die Grafiken
  karten.js             ← erzeugt: alle Grafiken als JS-Strings
  karte-*.svg           ← erzeugt: dieselben Grafiken einzeln
medien/                 Fotos für Schreiben, Presse und Aushang
                        (nicht auf der Website eingebunden)
daten/
  build.py              erzeugt Grafiken und Messwerte
  einzeldatei.py        packt alles in eine einzige HTML-Datei
  ifg-anfrage.md        Informationsbegehren an die Stadt (einmal zu senden)
  osm.json, poi.json    OpenStreetMap-Rohdaten
  overpass-*.ql         die Abfragen, mit denen sie geholt wurden
  messwerte.json        ← erzeugt: alle Zahlen der Seite, nachprüfbar
einzelseite.html        ← erzeugt: die ganze Seite als eine Datei
```

Die mit ← markierten Dateien nicht von Hand bearbeiten, sie werden überschrieben.

### Eine Datei zum Weitergeben

```bash
python3 daten/einzeldatei.py
```

Schreibt `einzelseite.html`, die vollständige Seite inklusive aller Grafiken in
einer einzigen Datei (rund 120 kB). Praktisch als E-Mail-Anhang, zum Archivieren
oder als Beilage zu einer Eingabe. Per Doppelklick im Browser zu öffnen, ohne
Server.

## Grafiken neu erzeugen

```bash
python3 daten/build.py
```

Braucht nur die Standardbibliothek. Das Skript rechnet alle Längen, Winkel und
Anhaltewege aus der OSM-Geometrie und schreibt sie zugleich nach
`daten/messwerte.json`, jede Zahl auf der Seite ist damit nachvollziehbar.

Rohdaten aktualisieren (nur nötig, wenn sich vor Ort etwas ändert):

```bash
# Straßennetz          → daten/osm.json
# Schulen, Kindergärten usw. → daten/poi.json  (overpass-poi.ql)
curl -X POST https://overpass-api.de/api/interpreter \
  -H "User-Agent: initiative-erzabt-klotz-strasse/1.0" \
  --data-binary @daten/overpass-netz.ql -o daten/osm.json
```

Der öffentliche Overpass-Server antwortet gelegentlich mit „502 at capacity" dann kurz warten und erneut versuchen. Die Antwort vor dem Überschreiben auf
gültiges JSON prüfen.

## Kernzahlen

| Größe | Wert | Herkunft |
|---|---:|---|
| Abschnitt Ampel → Kurve | 277,1 m | OSM-Geometrie |
| davon nahezu gerade | 233,9 m | Richtungsabweichung ±4,6° |
| Knick in die Nonntaler Hauptstraße | 46,9° | OSM-Geometrie |
| Tempolimit | 50 km/h | `maxspeed` |
| Querschnitt | 3 Fahrstreifen | `lanes=3`, davon eine Busspur |
| Versatz der beiden Haltestellen | 43,8 m | OSM-Geometrie |
| zwischen den nächsten Querungen | 266,1 m | OSM-Geometrie |
| Weg zur nächsten legalen Querung | 99 m / 123 m | OSM-Geometrie |
| Anhalteweg 30 / 50 / 60 km/h | 13 / 26 / 34 m | 1,0 s Reaktion, 8 m/s² |
| Schul- und Bildungsstandorte < 600 m | 10 | OSM, entdoppelt |

## Grafiken weiterverwenden

Die drei SVG-Dateien in `assets/` sind eigenständig und enthalten ihre eigene
Legende, sie lassen sich direkt in Schreiben an die Behörde, Presseanfragen
oder Aushänge einfügen. Sie passen sich hellen und dunklen Ansichten an.

## Lizenz und Herkunft

Geodaten © OpenStreetMap-Mitwirkende, [ODbL](https://www.openstreetmap.org/copyright).
Bei Weiterverwendung der Karten diesen Hinweis mitführen, er steht bereits in
jeder Grafik.

Die Seite ist eine private Anrainerinitiative, kein Angebot der Stadt Salzburg
und mit keiner Partei verbunden.
