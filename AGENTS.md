# AGENTS.md – Élő szavazó webapp (workshop projekt)

Ez a fájl a projekt tartós specifikációja. Minden munkamenet elején olvasd el, és tartsd magad hozzá.
Válaszaidat magyarul írd. A kód, fájlnevek, változók, route-ok angolul; a felhasználói felület szövegei magyarul.

## 1. Mit építünk

Egy eseményre szánt, helyi hálózaton futó, valós idejű szavazó webappot. Egy laptop a szerver, a résztvevők telefonról, QR-kóddal csatlakoznak ugyanarról a Wi-Fi-ről.

**Admin felület** (csak a host laptopról):
- kérdés létrehozása válaszlehetőségekkel, típus: `single` (egy választás) vagy `multi` (több választás)
- kérdés publikálása / váltás a kérdések között (egyszerre egy aktív kérdés)
- az aktív kérdés élő, összesített eredménye (kézi frissítés nélkül)
- QR-kód a résztvevői URL-lel, kivetíthető méretben, alatta szövegesen is az URL
- reset gomb (minden kérdés és szavazat törlése, megerősítéssel)

**Résztvevői felület** (telefon, QR-ról):
- az aktuálisan publikált kérdést látja; ha nincs ilyen, „Várakozás a következő kérdésre…”
- válasz beküldése; kérdésenként egyszer szavazhat, utána „Köszönjük, a szavazatod rögzítettük”
- ha az admin új kérdést publikál, az oldal magától átvált rá (kézi frissítés nélkül)
- oldal-újratöltés után is tudja, hogy erre a kérdésre már szavazott

## 2. Acceptance criteria (ez a „kész” definíciója)

1. A szerver LAN-ról elérhető, nem csak localhostról.
2. Egy telefon QR-ról az aktuális kérdéshez jut.
3. Single- és multi-select kérdés is működik.
4. Ugyanaz a böngésző ugyanarra a kérdésre nem szavaz újra – ezt a **backend és az adatbázis** kényszeríti ki, nem csak a UI.
5. Az admin eredménye kézi frissítés nélkül változik.
6. Új publikált kérdés megjelenik a klienseken.

Prioritási sorrend, ettől ne térj el: **P0** LAN elérés → **P1** kérdés + szavazat → **P2** egyszeri szavazás → **P3** live update → **P4** polish.
Polish (animáció, szép chart, extra UX) csak akkor, ha az 1–6. mind működik. Új funkcióval soha ne kerülj meg egy hibát.

## 3. Kötött stack

- Python 3.13, `uv` (projekt: `uv init`, függőség: `uv add ...`, futtatás: `uv run ...`)
- FastAPI + Uvicorn, egyetlen processz, egyetlen port (8000)
- SQLite a stdlib `sqlite3` modullal, egy fájl: `app.db` (ORM nélkül)
- Jinja2 sablonok + vanilla JS + saját CSS, build lépés nélkül
- SSE a szerver → böngésző élő frissítéshez (böngészőben natív `EventSource`)
- `qrcode` a QR-hoz, `ifaddr` a LAN IP felderítéséhez
- Függőségek: `uv add fastapi uvicorn jinja2 qrcode ifaddr` – ennél többet ne adj hozzá indoklás és jóváhagyásom nélkül.

**Tilos:** Node/npm, bundler, Docker, külön DB-szerver, WebSocket, ORM, bármilyen CDN (JS/CSS/font), cloud/hosted szolgáltatás. Futás közben az app nem használhat internetet. Minden asset a projektben van, és ugyanaz a FastAPI szolgálja ki (`StaticFiles`).

## 4. Kötelező technikai döntések (ismert buktatók elkerülésére)

**Indítás és hálózat**
- Belépési pont: `uv run python main.py`, ami `uvicorn.run(app, host="0.0.0.0", port=8000, timeout_graceful_shutdown=1)`-et hív. (A `timeout_graceful_shutdown` azért kell, mert nyitott SSE-kapcsolatok mellett különben a Ctrl+C nem állítja le a szervert.)
- LAN IP kiválasztása `ifaddr`-rel: csak IPv4; kizárni `127.*`, `169.254.*`; kizárni a virtuális/VPN adaptereket név alapján (pl. `utun`, `tun`, `tap`, `wg`, `tailscale`, `zerotier`, `docker`, `br-`, `veth`, `vEthernet`, `VirtualBox`, `VMware`, `Hyper-V`, `bridge`); preferencia: `192.168.*` > `10.*` > `172.16–31.*`.
- Legyen felülírható: `HOST_IP` környezeti változó vagy `--host-ip` argumentum.
- Induláskor a konzolra írd ki: admin URL (`http://localhost:8000/admin`), résztvevői URL (`http://<LAN-IP>:8000/`), és az összes talált jelölt IP-t az adapter nevével.
- A QR mindig a LAN IP-s résztvevői URL-re mutasson, soha ne `localhost`-ra.
- Windows és macOS alatt is működjön: csak `pathlib`, platformfüggetlen kód, ne használj shell-specifikus dolgot a futtatáshoz.

**Admin védelem**
- Nincs login. Az `/admin` oldalak és admin API-k csak localhostról (`127.0.0.1`, `::1`) érhetők el; máshonnan 403.

**QR**
- SVG-ként generáld szerveroldalon (`qrcode.image.svg`), így nem kell Pillow.

**Adatbázis**
- Séma-irány (a pontos neveket te választod): `questions` (id, text, type, created_at), `options` (id, question_id, text, position), `votes` (id, question_id, voter_id, created_at, **UNIQUE(question_id, voter_id)**), `vote_options` (vote_id, option_id). Az aktív kérdés egy `settings`/`state` táblában vagy egy `is_active` mezőben.
- Egy szavazat = egy `votes` sor; multi-selectnél több `vote_options` sor ugyanahhoz. Egy tranzakcióban írd.
- Kérésenként nyiss kapcsolatot (vagy `check_same_thread=False` + zár), `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`.
- Az adatbázis újraindítás után megmarad (nem törlődik indításkor). Törlés csak a reset gombbal.

**Szavazat validálás a backenden**
- Csak az aktuálisan publikált kérdésre lehet szavazni.
- A megadott opciók ehhez a kérdéshez tartoznak; `single`: pontosan 1, `multi`: legalább 1, ismétlés nélkül.
- Duplikált szavazat: a UNIQUE megsértését (`sqlite3.IntegrityError`) kapd el, és adj vissza 409-et érthető üzenettel.

**Voter ID**
- A szerver adja: ha nincs `voter_id` cookie, generálj `uuid4`-et, és állítsd be (`httponly`, `samesite=lax`, max_age kb. 30 nap). Ez anonim, workshop-szintű duplaszavazás-gátlás, nem hitelesítés.
- A résztvevői állapot-lekérés adja vissza, hogy ez a voter szavazott-e már az aktív kérdésre.

**Élő frissítés (SSE)**
- A szavazat és az admin műveletek sima HTTP POST-ok. Az SSE csak szerver → böngésző irányú.
- Robusztus, egyszerű minta: memóriában egy `state_version` számláló, amit minden változás (szavazat, publikálás, reset) növel. Az SSE generátor kb. 0,5 mp-enként megnézi, és ha változott, eseményt küld a friss állapottal (JSON). 15 mp-enként keepalive comment (`: ping`). A generátor lépjen ki, ha a kliens lecsatlakozott (`await request.is_disconnected()`).
- Használhatod a FastAPI natív SSE támogatását, ha a telepített verzióban elérhető; ha nem, `StreamingResponse(media_type="text/event-stream")` – külön SSE csomag nem kell.
- Fejlécek: `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- Két stream (vagy egy stream eseménytípusokkal): résztvevőknek az aktív kérdés változása, adminnak az eredmények. A résztvevő alapból nem látja az eredményt.
- Kliens oldalon az `EventSource` újracsatlakozik magától; újracsatlakozáskor kérje le a teljes friss állapotot.

**Frontend**
- Mobilra optimalizált résztvevői oldal (nagy gombok, `viewport` meta), single-nél radio, multi-nél checkbox.
- Admin eredmény: saját CSS/SVG oszlopdiagram, darabszám és százalék; külső chart library nincs.

## 5. Munkamódszer

- Kis lépésekben haladj, minden fázis végén futtasd a szervert, és ellenőrizd `curl`-lel vagy rövid Python szkripttel (SSE-t pl. `curl -N`-nel).
- Minden fázis végén röviden írd le: mi készült, hogyan teszteltem, mit kell nekem kézzel kipróbálni (böngésző, telefon).
- Ha valamit nem tudsz a gépen ellenőrizni (telefon, tűzfal, Wi-Fi), mondd meg pontosan, mit nézzek meg.
- Tűzfal: első indításkor macOS/Windows engedélyt kérhet a bejövő kapcsolatokra – ezt engedélyezni kell (Windowson privát hálózatra).
- Ne írj át működő részt „szépítés” miatt, amíg a core nincs kész. Ne vezess be új függőséget vagy architektúrát kérés nélkül.
- Legyen egy rövid `README.md`: telepítés, indítás, gyakori hibák (tűzfal, rossz IP, kliens-izolált Wi-Fi, `HOST_IP` felülírás).

## 6. Nem cél

Authentikáció, csalásbiztos azonosítás, publikus internetes biztonság, export, history, több párhuzamos aktív kérdés, felhasználói fiókok.
