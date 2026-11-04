"""Mantiene despierta la terminal en Streamlit Community Cloud.

Streamlit duerme las apps que llevan horas sin visitas y al volver hay que esperar a que arranquen. Este script abre
la app con un navegador real (una petición HTTP simple no cuenta como visita) y, si está dormida, pulsa el botón
para despertarla. Lo lanza cada pocas horas la GitHub Action .github/workflows/despertar.yml.
"""
from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

URL = "https://jesusvicens-screener-app-kc0xfh.streamlit.app/"


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(URL, wait_until="domcontentloaded", timeout=120_000)
        pg.wait_for_timeout(8_000)
        for fr in pg.frames:  # el botón puede estar dentro de un iframe
            try:
                boton = fr.get_by_text("get this app back up", exact=False)
                if boton.count():
                    print("Dormida: la despierto.")
                    boton.first.click()
                    pg.wait_for_timeout(90_000)
                    break
            except Exception:  # noqa: BLE001
                pass
        # espera a que cargue la app (pantalla de contraseña o Inicio)
        for i in range(36):
            txt = ""
            for fr in pg.frames:
                try:
                    txt += fr.inner_text("body", timeout=5_000)
                except Exception:  # noqa: BLE001
                    pass
            if "Contraseña" in txt or "Terminal" in txt or "Mis empresas" in txt:
                print("Despierta.")
                b.close()
                return 0
            if i % 6 == 0:
                print(f"[{i}] {len(pg.frames)} marcos · texto: {txt[:200]!r}")
            pg.wait_for_timeout(5_000)
        print("No he podido confirmar que esté despierta.")
        b.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
