"""Egyszeri segédszkript: Space Grotesk + JetBrains Mono woff2 letöltése
a Google Fontsról a static/fonts könyvtárba (csak latin + latin-ext).
Nem része a futó alkalmazásnak – csak a dizájnhoz készült asset.
"""

import pathlib
import re
import urllib.request

FONT_DIR = pathlib.Path(__file__).resolve().parent.parent / "static" / "fonts"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
CSS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Space+Grotesk:wght@400;500;600;700"
    "&family=JetBrains+Mono:wght@400;500;600&display=swap"
)

req = urllib.request.Request(CSS_URL, headers={"User-Agent": UA})
css = urllib.request.urlopen(req, timeout=30).read().decode()

FONT_DIR.mkdir(parents=True, exist_ok=True)

# A css2 válasz blokkjai:  /* latin */  @font-face { ... }
blocks = re.findall(r"/\*\s*([\w-]+)\s*\*/\s*@font-face\s*\{([^}]+)\}", css)
saved = []
for subset, body in blocks:
    if subset not in ("latin", "latin-ext"):
        continue
    family = re.search(r"font-family:\s*'([^']+)'", body).group(1)
    weight = re.search(r"font-weight:\s*(\d+)", body).group(1)
    url = re.search(r"url\((\S+?)\)\s+format\('woff2'\)", body).group(1)
    famfile = family.replace(" ", "")
    fname = f"{famfile}-{weight}-{subset}.woff2"
    dest = FONT_DIR / fname
    if not dest.exists():
        urllib.request.urlretrieve(url, dest)
    saved.append((family, weight, subset, fname))

for family, weight, subset, fname in saved:
    print(f"@font-face {family} {weight} [{subset}] -> static/fonts/{fname}")

print("fájlok:", ", ".join(p.name for p in FONT_DIR.iterdir()))