"""Mantiene despierta la terminal en Streamlit Community Cloud.

Streamlit duerme las apps que llevan horas sin visitas y al volver hay que esperar a que arranquen. Este script abre
la app con un navegador real (una petición HTTP simple no cuenta como visita); si está dormida, pulsa el botón para
despertarla, y espera hasta que la app responde (pantalla de contraseña o Inicio). Lo lanza cada pocas horas la
GitHub Action .github/workflows/despertar.yml.
"""
from __future__ import annotations

import sys
import time

from playwright.sync_api import sync_playwright

URL = "https://jesusvicens-screener-app-kc0xfh.streamlit.app/"
APP = URL + "~/+/"          # la app en sí (lo que va dentro del marco de streamlit.app)
LISTA = ("Contraseña", "Mis empresas", "Terminal")
MAX_MIN = 9


def _texto(pg) -> str:
    out = ""
    for fr in pg.frames:
        try:
            out += fr.inner_text("body", timeout=5_000) + "\n"
        except Exception:  # noqa: BLE001
            pass
    return out


def _despertar_si_duerme(pg) -> bool:
    for fr in pg.frames:
        try:
            b = fr.get_by_text("get this app back up", exact=False)
            if b.count():
                print("Dormida: pulso el botón para despertarla.", flush=True)
                b.first.click()
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


def main() -> int:
    t0 = time.time()
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(viewport={"width": 1400, "height": 900}, locale="es-ES",
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                       "Chrome/131.0.0.0 Safari/537.36")
        ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        pg = ctx.new_page()
        pg.goto(URL, wait_until="domcontentloaded", timeout=120_000)
        pg.wait_for_timeout(10_000)
        _despertar_si_duerme(pg)
        intento = 0
        while time.time() - t0 < MAX_MIN * 60:
            intento += 1
            # la app directamente: así Streamlit ejecuta el script como en una visita normal
            try:
                if intento > 1:
                    pg.goto(URL, wait_until="domcontentloaded", timeout=120_000)
            except Exception as e:  # noqa: BLE001
                print(f"[{intento}] no carga: {e}", flush=True)
            for _ in range(12):  # hasta 2 minutos por intento
                pg.wait_for_timeout(10_000)
                txt = _texto(pg)
                if any(x in txt for x in LISTA):
                    print(f"Despierta y respondiendo ({time.time() - t0:.0f} s).", flush=True)
                    b.close()
                    return 0
                if _despertar_si_duerme(pg):
                    break
            print(f"[{intento}] aún arrancando ({time.time() - t0:.0f} s)…", flush=True)
            pg.screenshot(path=f"despertar_{intento}.png")
        print("No he podido confirmar que esté despierta.", flush=True)
        b.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
