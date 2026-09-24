# Élő szavazó webapp (workshop projekt)

Valós idejű, helyi hálózaton futó szavazó alkalmazás eseményekre.
Egy laptop a szerver, a résztvevők telefonról QR-kóddal csatlakoznak
ugyanarról a Wi-Fi-ről.

## Telepítés

```bash
uv python install 3.13        # ha még nincs 3.13-as Python
uv sync                       # függőségek (fastapi, uvicorn, jinja2, qrcode, ifaddr)
```

## Indítás

```bash
uv run python main.py
```

Induláskor a konzol kiírja:

- az **admin URL-t**: `http://localhost:8000/admin` (csak a host gépről érhető el)
- a **résztvevői URL-t**: `http://<LAN-IP>:8000/` (telefonról, QR-ról nyitható)
- a talált jelölt LAN IP-ket az adapter nevével

Az admin oldalon van a kivetíthető QR-kód. Az adatbázis (`app.db`)
újraindításkor megmarad; törlés csak az admin reset gombjával.

## Felülírás rossz/ektikus hálózat esetén

```bash
HOST_IP=192.168.1.42 uv run python main.py
# vagy
uv run python main.py --host-ip 192.168.1.42
```

## Gyakori hibák

- **macOS/Windows tűzfal**: az első indításkor engedélyt kér a bejövő
  kapcsolatokra – engedélyezni kell (Windowson privát hálózatra).
- **A telefon nem éri el az oldalt**: ellenőrizd, hogy a telefon ugyanazon
  a Wi-Fi-n van, mint a laptop.
- **Kliens-izolált Wi-Fi**: ha a hálózat nem engedi, hogy két eszköz
  egymással kommunikáljon (pl. vendég-hálózat), a telefon sosem éri el a
  laptopot – ilyenkor saját AP/router kell.
- **Rossz LAN IP**: VPN/virtuális adapter is ellőzheti a választást –
  ilyenkor állítsd be a `HOST_IP`-t a laptop valódi LAN címére.