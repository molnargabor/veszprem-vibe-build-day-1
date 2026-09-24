"""Belépési pont – indítás: uv run python main.py

Uvicorn 0.0.0.0:8000-on figyel (LAN), a résztvevői URL-hez LAN IP-t
derít fel ifaddr-rel. HOST_IP környezeti változó vagy --host-ip argumentum
felülírja a felderítést.
"""

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Élő szavazó webapp – szerver indítás")
    parser.add_argument(
        "--host-ip",
        default=None,
        help="Résztvevői URL/QR-hez használt LAN IP (felülírja a felderítést)",
    )
    args = parser.parse_args()
    if args.host_ip:
        os.environ["HOST_IP"] = args.host_ip

    # A HOST_IP env-et az app.py importáláskor olvassa be
    from app import ADMIN_URL, IP_CANDIDATES, LAN_IP, VOTER_URL, app

    def out(msg: str) -> None:
        print(msg, flush=True)

    out("=" * 62)
    out(f"Admin felület:    {ADMIN_URL}")
    out(f"Résztvevői URL:   {VOTER_URL}")
    if IP_CANDIDATES:
        out("Jelölt LAN IP-k (adapter nevével):")
        for addr, name in IP_CANDIDATES:
            marker = "*" if addr == LAN_IP else " "
            out(f"  {marker} {addr:16s} ({name})")
    else:
        out("(A jelölt IP-k nem listázhatók – valószínűleg HOST_IP felülírás, "
            "vagy nem találtam privát IPv4-et.)")
    if LAN_IP == "127.0.0.1":
        out("FIGYELEM: nincs LAN IP – telefonról NEM érhető el! Állítsd be a HOST_IP-t, "
            "vagy ellenőrizd a hálózatot/tűzfalat.")
    out("=" * 62)

    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_graceful_shutdown=1)


if __name__ == "__main__":
    main()