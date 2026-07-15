"""
LLANO - Daemon de automatizacion
Corre silencioso en background desde el login.
Dispara las corridas a las 7:00, 11:00 y 17:00 aunque la pantalla este bloqueada.
"""
import subprocess
import time
import datetime
import os
import sys

RUTA = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(RUTA, "daemon.log")
PYTHON = sys.executable

def log(msg):
    ts = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    linea = f"{ts} {msg}\n"
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linea)
    except Exception:
        pass

def correr_actualizacion():
    try:
        result = subprocess.run(
            [PYTHON, os.path.join(RUTA, "actualizar.py")],
            capture_output=True, text=True, timeout=600,
            cwd=RUTA, env={**os.environ, "PYTHONUNBUFFERED": "1"}
        )
        salida = (result.stdout + result.stderr).strip()
        log(f"actualizar.py salida: {salida[:500]}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        log("TIMEOUT: actualizar.py tardo mas de 10 minutos")
        return False
    except Exception as e:
        log(f"ERROR al correr actualizar.py: {e}")
        return False

def main():
    log("=== DAEMON INICIADO ===")

    # Horarios objetivo (hora, minuto)
    HORARIOS = [(7, 0), (11, 0), (17, 0)]
    ultimo_disparo = None

    while True:
        try:
            ahora = datetime.datetime.now()
            clave_dia = ahora.strftime("%Y-%m-%d")

            for hora, minuto in HORARIOS:
                clave = f"{clave_dia}_{hora:02d}{minuto:02d}"

                # Ventana de 30 minutos post-horario para disparar
                objetivo = ahora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
                diferencia = (ahora - objetivo).total_seconds()

                if 0 <= diferencia < 1800 and clave != ultimo_disparo:
                    log(f"Disparando corrida de las {hora:02d}:{minuto:02d}")
                    ok = correr_actualizacion()
                    if ok:
                        ultimo_disparo = clave
                        log(f"Corrida {clave} completada OK")
                    else:
                        log(f"Corrida {clave} fallo, reintentara en proximo ciclo")

            # Esperar 5 minutos antes de revisar de nuevo
            time.sleep(300)

        except Exception as e:
            log(f"ERROR en loop principal: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
