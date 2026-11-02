# Fotos von der Stelle

Auf der Website selbst sind keine Fotos eingebunden; sie ist bewusst kurz
gehalten. Aufnahmen sind trotzdem nützlich, nämlich als Beilage zum Schreiben
an die Stadt, für Presseanfragen und für einen Aushang im Haus. Ein Foto der
Querungssituation sagt dort mehr als jede Längenangabe.

`locations.md` in diesem Ordner nennt sechs Standorte mit Koordinaten und
Blickrichtung, aus der Straßengeometrie gerechnet. Wer sich daran hält,
bekommt Aufnahmen, die zu den Diagrammen in `assets/` passen.

## Was sich gut eignet

| Aufnahme | Warum sie wirkt |
|---|---|
| Querende Menschen auf Höhe der Haltestellen | zeigt die Situation, um die es geht |
| Wartende an der Bedarfsampel, mit sichtbarer Uhr | belegt die Wartezeit |
| Die Gerade aus Fußgängerperspektive | macht die 234 Meter begreifbar |
| Schulweg am Morgen, 7:30 bis 8:00 Uhr | zeigt, wer hier unterwegs ist |

Querformat, und möglichst bei Tageslicht.

## Personenbezug entfernen

Vor dem Weitergeben: **Kennzeichen und Gesichter unkenntlich machen.** Am
einfachsten so aufnehmen, dass beides gar nicht erst erkennbar ist, aus
größerem Abstand, von hinten, oder mit Blick auf die Fahrbahn statt auf
Menschen.

```bash
# Videos auf eine handliche Größe bringen (ffmpeg)
ffmpeg -i original.mp4 -vf "scale=1280:-2" -c:v libx264 -crf 28 -an kurz.mp4
#   -an entfernt die Tonspur: nebenbei gesprochene Worte gehören nicht weiter

# EXIF-Daten aus Fotos entfernen (Ort, Gerät, Uhrzeit)
exiftool -all= -overwrite_original *.jpg
```

Für das Verpixeln einzelner Bereiche reicht jedes Bildbearbeitungsprogramm;
für Videos leistet **Shotcut** (Filter „Größe, Position, Drehen" plus
„Weichzeichnen: Pixel") dasselbe ohne Kommandozeile.

## Rechtlicher Hinweis

Filmen im öffentlichen Raum ist in Österreich grundsätzlich zulässig; die
Veröffentlichung erkennbarer Personen ist es nicht ohne Weiteres. Im Zweifel
unkenntlich machen oder weglassen. Die Argumentation trägt auch ohne
Bildmaterial, die Zahlen stammen aus offenen Geodaten. Dies ist eine
praktische Empfehlung und keine Rechtsberatung.
