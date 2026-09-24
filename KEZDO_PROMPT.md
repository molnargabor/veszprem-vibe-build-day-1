# Kezdő prompt – OpenCode + Big Pickle

## Előkészítés (0:00–0:15)

1. Üres mappa, bele az `AGENTS.md`. (Az OpenCode automatikusan betölti a projekt gyökeréből.)
2. `uv python install 3.13`, majd a mappában `opencode`.
3. `/models` → **Big Pickle**.
4. **Tab** → váltás a **Plan** agentre (ez csak tervez, nem ír fájlt). Ide jön az 1. prompt.

---

## 1. prompt – terv (Plan módban)

```
Olvasd el az AGENTS.md-t, ez a projekt specifikációja és a szabályai.

Még ne írj kódot. Készíts rövid implementációs tervet:
1. Fájlszerkezet (fájlonként 1 sor, mi van benne).
2. Adatbázis-séma (CREATE TABLE-ök).
3. Route-lista: metódus, útvonal, mit csinál, admin-only-e.
4. SSE események: melyik stream, milyen eseménytípus, milyen JSON.
5. Fázisok az AGENTS.md prioritási sorrendje szerint (P0–P3), mindegyiknél:
   mi készül el, és hogyan ellenőrzöd (konkrét curl parancsok).
6. Minden, ami a specifikációban nem egyértelmű, vagy amiben el akarsz
   térni tőle – ezeket kérdésként írd le, ne feltételezd.

Tömören, felsorolásokkal. Magyarul.
```

Nézd át a tervet. Ha a séma nem tartalmazza a `UNIQUE(question_id, voter_id)`-t, a host `0.0.0.0` helyett más, vagy CDN/WebSocket/extra csomag bukkan fel – szólj rá, mielőtt továbblépsz.

---

## 2. prompt – P0: LAN sanity check (Tab → **Build** mód)

```
A terv jó, kezdjük az 1. fázissal, és csak azzal:
- uv projekt Python 3.13-mal, függőségek az AGENTS.md szerint
- main.py: uvicorn 0.0.0.0:8000, LAN IP felderítés ifaddr-rel a szabályok
  szerint, HOST_IP felülírással, indításkor kiírja az URL-eket és a
  jelölt IP-ket
- "/" egy egyszerű magyar teszt oldal ("A szerver elérhető")
- "/admin" localhost-only, rajta a résztvevői URL QR-kódja SVG-ben és
  szövegesen

Indítsd el, ellenőrizd curl-lel a localhost és a LAN IP címen is, hogy a
/admin LAN IP-ről 403-at ad, majd állítsd le. A végén írd le, pontosan
milyen paranccsal indítsam, és mit teszteljek telefonról.
```

**Itt állj meg, és teszteld le kézzel:** másik ember telefonja, ugyanaz a Wi-Fi, QR beolvasás → megnyílik az oldal. Amíg ez nem megy, nem fejlesztünk tovább (tűzfal, rossz IP, kliens-izoláció).

---

## 3. prompt – P1–P3: core

```
A telefon eléri a szervert, P0 kész. Most építsd meg a core-t a terv
szerint, ebben a sorrendben, minden lépés után curl-lel ellenőrizve:

P1 – admin: kérdés létrehozása (single/multi, opciók), publikálás,
     kérdésváltás; résztvevő: aktív kérdés megjelenítése, szavazat
     beküldése, "várakozás" állapot, ha nincs aktív kérdés.
P2 – egyszeri szavazás: voter_id cookie, UNIQUE constraint, 409 duplikátumra,
     backend validálás (aktív kérdés, opciók, single=1 / multi>=1).
     Újratöltés után a résztvevő lássa, hogy már szavazott.
P3 – SSE: admin eredmény élőben frissül; új publikált kérdés megjelenik a
     telefonokon kézi frissítés nélkül. Az AGENTS.md state_version mintáját
     használd.

Plusz: reset gomb az adminon megerősítéssel, és rövid README.md.

A végén menj végig az AGENTS.md 1–6. acceptance criteriáján, és mindegyiknél
írd le: automatikusan ellenőrizted (hogyan), vagy nekem kell kézzel
(mit és hogyan). Polish-t még ne csinálj.
```

---

## Hasznos folytató promptok

**Hibajelentés** (konkrét jelenség, ne új funkció):
```
Hiba: [mit csináltam] → [mit vártam] → [mi történt].
Eszköz/böngésző: [pl. iPhone Safari]. Konzol/szerver log: [bemásolva].
Először reprodukáld és mondd meg az okát, utána javíts. Mást ne változtass.
```

**Feature freeze (1:25):**
```
Feature freeze. Új funkció nincs. Menj végig az AGENTS.md 1–6. pontján,
indítsd a szervert, és ellenőrizz mindent, amit gépen tudsz. Listázd, mi
zöld, mi nem, és csak a nem zöldeket javítsd.
```

**Polish (csak ha minden zöld):**
```
Minden acceptance criteria zöld. Polish: [pl. animált oszlopok, nagyobb
QR kivetítéshez, szavazatszám az adminon, sötét téma]. Külső asset/CDN
továbbra sem lehet. Minden változtatás után ellenőrizd, hogy a core nem
tört el.
```
