#!/usr/bin/env python3
"""
deploy_ota.py

Fa tot el flux OTA en una sola comanda, sense fitxers de configuració
duplicats: llegeix host/token/topic directament de src/config.py i
src/secrets.py (els mateixos fitxers que es pugen al dispositiu, on
acaben dins /usr/ al filesystem del BG95 — localment no cal aquesta
carpeta intermèdia), així que no hi ha res a mantenir sincronitzat a banda.

Passos:
  1. Actualitza VERSIO dins usr/config.py
  2. Genera manifest.json (hashes sha256 dels fitxers a publicar)
  3. git add + commit + push
  4. Publica l'ordre OTA per MQTT (amb confirmació abans d'enviar)

Requereix: pip install paho-mqtt

Ús:
    python deploy_ota.py 1.4.3
    python deploy_ota.py 1.4.3 --files main.py config.py
    python deploy_ota.py 1.4.3 --skip-git
    python deploy_ota.py 1.4.3 --skip-publish
    python deploy_ota.py 1.4.3 --wait-ack 30

Assumeix:
  - src/config.py conté VERSIO, MQTT_HOST, TOPIC_ORDRES
  - src/secrets.py conté TOKEN_FLESPI_MQTT
  - Els fitxers a publicar són els indicats a --files (per defecte: main.py config.py)
  - Un repositori git ja inicialitzat amb remot configurat
"""

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print(
        "Falta la llibreria paho-mqtt. Instal·la-la amb:\n"
        "    pip install paho-mqtt",
        file=sys.stderr
    )
    sys.exit(1)


ack_rebut = {"valor": False}


# ---------------------------------------------------------------------------
# 0. Llegir config.py / secrets.py del dispositiu (font única de veritat)
# ---------------------------------------------------------------------------

def carregar_modul(path: Path, nom: str):
    if not path.is_file():
        print(f"Error: no s'ha trobat '{path}'.", file=sys.stderr)
        sys.exit(1)

    spec = importlib.util.spec_from_file_location(nom, path)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def run(cmd, check=True):
    print(f"$ {' '.join(cmd)}")
    resultat = subprocess.run(cmd)
    if check and resultat.returncode != 0:
        print(f"\nError: la comanda ha fallat (codi {resultat.returncode}). Aturant.", file=sys.stderr)
        sys.exit(resultat.returncode)
    return resultat.returncode


# ---------------------------------------------------------------------------
# 1. Versió
# ---------------------------------------------------------------------------

def actualitzar_versio(config_path: Path, versio: str):
    text = config_path.read_text()
    patro = re.compile(r'^(VERSIO\s*=\s*)["\'].*["\']', re.MULTILINE)

    if not patro.search(text):
        print(
            f"Error: no s'ha trobat cap línia 'VERSIO = \"...\"' a {config_path}.\n"
            "Actualitza-la manualment i torna a córrer amb --skip-version.",
            file=sys.stderr
        )
        sys.exit(1)

    nou_text = patro.sub(rf'\1"{versio}"', text)

    if nou_text == text:
        print(f"VERSIO ja era '{versio}', no cal canviar res.")
    else:
        config_path.write_text(nou_text)
        print(f"VERSIO actualitzada a '{versio}' dins {config_path}")


# ---------------------------------------------------------------------------
# 2. Manifest
# ---------------------------------------------------------------------------

def calcular_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloc in iter(lambda: f.read(8192), b""):
            h.update(bloc)
    return h.hexdigest()


def generar_manifest(src_dir: Path, noms_fitxers: list, versio: str,
                      output: Path, max_size_kb: int) -> dict:
    hashes = {}

    for nom in noms_fitxers:
        path = src_dir / nom

        if not path.is_file():
            print(f"Error: no s'ha trobat '{path}'.", file=sys.stderr)
            sys.exit(1)

        mida_kb = path.stat().st_size / 1024

        if mida_kb > max_size_kb:
            print(
                f"AVÍS: {nom} fa {mida_kb:.1f} KB, supera el límit de {max_size_kb} KB.",
                file=sys.stderr
            )

        hash_hex = calcular_sha256(path)
        hashes[nom] = hash_hex

        print(f"  {nom:30s} {mida_kb:7.1f} KB   sha256:{hash_hex[:12]}...")

    manifest = {"version": versio, "files": noms_fitxers, "hashes": hashes}
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    print(f"\nManifest generat: {output}")
    return manifest


# ---------------------------------------------------------------------------
# 4. Publicar per MQTT
# ---------------------------------------------------------------------------

def on_connect(client, userdata, flags, rc, *extra):
    # extra absorbeix 'properties' (paho-mqtt >= 2.0) sense trencar amb v1.x
    if rc == 0:
        print("Connectat al broker MQTT.")
    else:
        print(f"Error de connexió MQTT, codi: {rc}", file=sys.stderr)


def on_message(client, userdata, msg):
    if msg.payload == b"":
        ack_rebut["valor"] = True
        print("ACK rebut: el dispositiu ha processat l'ordre.")


def publicar_ordre_ota(manifest: dict, host: str, port: int, token: str,
                        topic: str, use_tls: bool, wait_ack: int):
    ordre = {
        "cmd": "ota",
        "files": manifest["files"],
        "hashes": manifest["hashes"],
        "version": manifest["version"],
    }

    print(f"\nVersió a publicar: {manifest['version']}")
    print(f"Fitxers: {', '.join(manifest['files'])}")
    print(f"Topic: {topic}")
    print(f"Broker: {host}:{port} (TLS: {use_tls})\n")

    confirmacio = input("Confirmes la publicació d'aquesta ordre OTA? [s/N] ")
    if confirmacio.strip().lower() not in ("s", "si", "sí", "y", "yes"):
        print("Cancel·lat.")
        sys.exit(0)

    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    else:
        client = mqtt.Client()  # paho-mqtt < 2.0

    client.username_pw_set(token, token)

    if use_tls:
        client.tls_set()

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(host, port, keepalive=30)
    client.subscribe(topic, qos=0)
    client.loop_start()

    time.sleep(1)  # marge per completar la subscripció abans de publicar

    client.publish(topic, json.dumps(ordre), qos=0, retain=True)
    print("Ordre OTA publicada.")

    if wait_ack > 0:
        print(f"Esperant confirmació del dispositiu (fins a {wait_ack}s)...")
        inici = time.time()

        while time.time() - inici < wait_ack:
            if ack_rebut["valor"]:
                break
            time.sleep(0.5)

        if not ack_rebut["valor"]:
            print(
                "AVÍS: no s'ha rebut confirmació dins el temps d'espera. "
                "El dispositiu pot estar en PSM/dormint; rebrà l'ordre "
                "(retained) al proper cicle d'activitat.",
                file=sys.stderr
            )

    client.loop_stop()
    client.disconnect()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Desplega una nova versió OTA de cap a cap.")
    parser.add_argument("version", help="Número de versió a publicar (ex: 1.4.3)")
    parser.add_argument("--src-dir", default="src", help="Directori local amb el codi del dispositiu (per defecte: src)")
    parser.add_argument("--files", nargs="+", default=["main.py", "config.py"],
                         help="Fitxers a publicar per OTA (per defecte: main.py config.py)")
    parser.add_argument("--manifest-out", default="ota/manifest.json",
                         help="Ruta on desar el manifest (per defecte: ota/manifest.json)")
    parser.add_argument("--max-size-kb", type=int, default=100)
    parser.add_argument("--mqtt-port", type=int, default=8883, help="Port MQTT per publicar (per defecte: 8883, TLS)")
    parser.add_argument("--no-tls", action="store_true")
    parser.add_argument("--wait-ack", type=int, default=20)
    parser.add_argument("--commit-msg", default=None)
    parser.add_argument("--skip-version", action="store_true")
    parser.add_argument("--skip-git", action="store_true")
    parser.add_argument("--skip-publish", action="store_true")
    args = parser.parse_args()

    src_dir = Path(args.src_dir)
    config_path = src_dir / "config.py"
    secrets_path = src_dir / "secrets.py"
    manifest_path = Path(args.manifest_out)
    commit_msg = args.commit_msg or f"OTA v{args.version}"

    print(f"=== Desplegament OTA v{args.version} ===\n")

    # 1. Versió
    if not args.skip_version:
        print("-- Pas 1/4: actualitzar VERSIO --")
        actualitzar_versio(config_path, args.version)
    else:
        print("-- Pas 1/4: omès (--skip-version) --")

    # 2. Manifest (llegeix els fitxers ja actualitzats, incloent el nou VERSIO)
    print("\n-- Pas 2/4: generar manifest.json --")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = generar_manifest(src_dir, args.files, args.version, manifest_path, args.max_size_kb)

    # 3. Git
    if not args.skip_git:
        print("\n-- Pas 3/4: git add / commit / push --")
        run(["git", "add", "-A"])

        codi = run(["git", "diff", "--cached", "--quiet"], check=False)
        if codi == 0:
            print("No hi ha canvis a committejar (working tree ja net).")
        else:
            run(["git", "commit", "-m", commit_msg])
            run(["git", "push"])
    else:
        print("\n-- Pas 3/4: omès (--skip-git) --")

    # 4. Publicar (llegeix config/secrets del dispositiu, no hi ha fitxer dedicat a mantenir)
    if not args.skip_publish:
        print("\n-- Pas 4/4: publicar ordre OTA per MQTT --")

        config_modul = carregar_modul(config_path, "device_config")
        secrets_modul = carregar_modul(secrets_path, "device_secrets")

        host = config_modul.MQTT_HOST
        token = secrets_modul.TOKEN_FLESPI_MQTT
        topic = config_modul.TOPIC_ORDRES

        publicar_ordre_ota(
            manifest=manifest,
            host=host,
            port=args.mqtt_port,
            token=token,
            topic=topic,
            use_tls=not args.no_tls,
            wait_ack=args.wait_ack,
        )
    else:
        print("\n-- Pas 4/4: omès (--skip-publish) --")
        print(f"Manifest llest a {manifest_path}.")

    print(f"\n=== Desplegament v{args.version} completat ===")


if __name__ == "__main__":
    main()