#!/usr/bin/env python3
"""
Baut aus index.html und den Dateien in assets/ eine einzige, in sich
geschlossene HTML-Datei — praktisch zum Weitergeben per E-Mail, zum Archivieren
oder als Anhang an eine Eingabe.

    python3 daten/einzeldatei.py

Ausgabe:
    einzelseite.html            vollstaendige Datei, laeuft per Doppelklick
    daten/artefakt-koerper.html dasselbe ohne Huelle, fuer Dienste, die nur
                                den Seiteninhalt einbetten

Voraussetzung: daten/build.py wurde zuvor ausgefuehrt.
"""

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def lies(*teile):
    with open(os.path.join(ROOT, *teile), encoding="utf-8") as fh:
        return fh.read()


html = lies("index.html")

# --- Stylesheets einbetten -------------------------------------------------
stile = "\n".join(lies("assets", f) for f in ("palette.css", "style.css"))
html = html.replace(
    '<link rel="stylesheet" href="assets/palette.css">\n'
    '<link rel="stylesheet" href="assets/style.css">',
    "<style>\n" + stile + "\n</style>",
)

# --- Skripte einbetten -----------------------------------------------------
skripte = "\n".join(lies("assets", f) for f in ("karten.js", "app.js"))
html = re.sub(
    r'<script src="assets/karten\.js"></script>\s*'
    r'<script src="assets/app\.js"></script>',
    "<script>\n" + skripte + "\n</script>",
    html,
)

# Die SVG-Grafiken stecken bereits in karten.js; der noscript-Ersatz waere in
# der Einzeldatei ein toter Verweis.
html = re.sub(
    r"(?s)<noscript><img src=\"assets/karte-[a-z]+\.svg\".*?></noscript>", "", html
)

with open(os.path.join(ROOT, "einzelseite.html"), "w", encoding="utf-8") as fh:
    fh.write(html)

# --- Variante ohne Huelle --------------------------------------------------
koerper = html
koerper = re.sub(r"(?is)^.*?<head>", "", koerper)
koerper = koerper.replace("</head>", "").replace("</html>", "")
koerper = re.sub(r"(?is)<body>", "", koerper)
koerper = koerper.replace("</body>", "")
# Angaben, die in einen fremden <head> nicht uebernommen werden koennen
koerper = re.sub(r"(?i)\s*<meta[^>]*>", "", koerper)
# Das Favicon ist eine data-URI und enthaelt selbst ">" — zeilenweise entfernen
koerper = re.sub(r'(?im)^\s*<link rel="icon".*$', "", koerper)
# Downloadverweise auf Nachbardateien gibt es hier nicht — als Text belassen
koerper = re.sub(
    r'<a href="(?:assets|daten)/[^"]+"[^>]*>(.*?)</a>', r"\1", koerper
)
koerper = koerper.strip() + "\n"

with open(os.path.join(HERE, "artefakt-koerper.html"), "w", encoding="utf-8") as fh:
    fh.write(koerper)

einzel = os.path.getsize(os.path.join(ROOT, "einzelseite.html"))
print(f"einzelseite.html            {einzel/1024:7.0f} kB")
print(f"daten/artefakt-koerper.html {len(koerper.encode())/1024:7.0f} kB")
