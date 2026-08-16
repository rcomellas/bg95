"""
Monitor de port sèrie amb timestamp per línia, i possibilitat
d'enviar Ctrl+D (soft reset MicroPython/QuecPython) sense tocar
el botó físic del mòdul.

Ús:
    python monitor_serial.py COM12 115200

Mentre corre:
    - Escriu "r" + Enter  -> envia Ctrl+D (soft reset) al mòdul
    - Ctrl+C               -> surt del programa

Requereix pyserial:
    pip install pyserial
"""

import sys
import time
import threading
import serial


CTRL_D = b"\x04"


def escoltar_teclat(ser):
    """Fil separat: llegeix comandes de teclat i les envia al port."""

    while True:
        try:
            ordre = input()
        except EOFError:
            return

        if ordre.strip().lower() == "r":
            print(">>> Enviant Ctrl+D (soft reset)...")
            ser.write(CTRL_D)


def main():
    if len(sys.argv) < 2:
        print("Us: python monitor_serial.py <port> [baudrate]")
        print("Exemple: python monitor_serial.py COM12 115200")
        sys.exit(1)

    port = sys.argv[1]
    baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

    print(f"Obrint {port} a {baudrate} baud... (Ctrl+C per sortir)")
    print("Escriu 'r' + Enter en qualsevol moment per fer soft reset (Ctrl+D)")

    try:
        ser = serial.Serial(port, baudrate, timeout=1)
    except serial.SerialException as error:
        print(f"Error obrint el port: {error}")
        sys.exit(1)

    fil = threading.Thread(target=escoltar_teclat, args=(ser,), daemon=True)
    fil.start()

    inici = None

    try:
        while True:
            linia = ser.readline()

            if not linia:
                continue

            ara = time.time()
            text = linia.decode("utf-8", "ignore").rstrip()

            if inici is None:
                inici = ara

            delta = ara - inici

            print(f"[{delta:8.2f}s] {text}")

    except KeyboardInterrupt:
        print("\nAturat per l'usuari.")

    except serial.SerialException:
        final = time.time()
        delta = final - inici if inici else 0
        print(
            f"[{delta:8.2f}s] >>> Port desconnectat (possible entrada a PSM real) <<<")

    finally:
        ser.close()


if __name__ == "__main__":
    main()
