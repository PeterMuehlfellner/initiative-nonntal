#!/usr/bin/env python3
"""
Packs index.html and the files in assets/ into one self-contained HTML file,
handy for passing around by e-mail, for archiving, or as an attachment to a
submission.

    python3 data/bundle.py

Output:
    single-page.html          the complete file, opens on a double click
    data/artifact-body.html   the same without the shell, for services that
                              embed only the page content

Prerequisite: data/build.py has been run.
"""

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def read_file(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


html = read_file("index.html")

# --- inline the stylesheets ------------------------------------------------
styles = "\n".join(read_file("assets", f) for f in ("palette.css", "style.css"))
html = html.replace(
    '<link rel="stylesheet" href="assets/palette.css">\n'
    '<link rel="stylesheet" href="assets/style.css">',
    "<style>\n" + styles + "\n</style>",
)

# --- inline the scripts ----------------------------------------------------
scripts = "\n".join(read_file("assets", f) for f in ("figures.js", "app.js"))
html = re.sub(
    r'<script src="assets/figures\.js"></script>\s*'
    r'<script src="assets/app\.js"></script>',
    "<script>\n" + scripts + "\n</script>",
    html,
)

# The SVG figures already sit inside figures.js; in a single file the noscript
# fallback would be a dead reference.
html = re.sub(
    r"(?s)<noscript><img src=\"assets/figure-[a-z-]+\.svg\".*?></noscript>", "", html
)

with open(os.path.join(ROOT, "single-page.html"), "w", encoding="utf-8") as fh:
    fh.write(html)

# --- variant without the shell ---------------------------------------------
body = html
body = re.sub(r"(?is)^.*?<head>", "", body)
body = body.replace("</head>", "").replace("</html>", "")
body = re.sub(r"(?is)<body>", "", body)
body = body.replace("</body>", "")
# Declarations that cannot be carried over into someone else's <head>
body = re.sub(r"(?i)\s*<meta[^>]*>", "", body)
# The favicon is a data URI and contains ">" itself, so strip it line by line
body = re.sub(r'(?im)^\s*<link rel="icon".*$', "", body)
# There are no neighbouring files to download here, so leave the text in place
body = re.sub(
    r'<a href="(?:assets|data)/[^"]+"[^>]*>(.*?)</a>', r"\1", body
)
body = body.strip() + "\n"

with open(os.path.join(HERE, "artifact-body.html"), "w", encoding="utf-8") as fh:
    fh.write(body)

single = os.path.getsize(os.path.join(ROOT, "single-page.html"))
print(f"single-page.html          {single/1024:7.0f} kB")
print(f"data/artifact-body.html   {len(body.encode())/1024:7.0f} kB")
