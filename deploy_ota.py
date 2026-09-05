#!/usr/bin/env python3
"""
deploy_ota.py

Fa tot el flux OTA en una sola comanda, sense fitxers de configuració
duplicats: llegeix host/token/topic directament de src/config.py i
src/secrets.py (els mateixos fitxers que es pugen al dispositiu, on
acaben dins /usr/ al filesystem del BG95 — localment no cal aquesta
carpeta intermèdia), així que no hi ha res a mantenir sincronitzat a banda.

Passos:
  1. Actualitza VERSIO dins src/main.py
  2. Publica els fitxers en una branca OTA separada amb git worktree
  3. Publica l'ordre OTA per MQTT com a retained

Requereix: pip install paho-mqtt

Ús:
    python deploy_ota.py 1.4.3
    python deploy_ota.py 1.4.3 --files main.py config.py
    python deploy_ota.py 1.4.3 --skip-git
    python deploy_ota.py 1.4.3 --skip-publish

Assumeix:
  - src/main.py conté VERSIO
  - src/config.py conté MQTT_HOST, TOPIC_ORDRES
  - src/device.py conté DEVICE_ID
  - src/secrets.py conté TOKEN_FLESPI_MQTT
  - Els fitxers a publicar són els indicats a --files (per defecte: main.py)
  - Un repositori git ja inicialitzat amb remot 'origin' configurat
"""

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
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

def actualitzar_versio(main_path: Path, versio: str):
    text = main_path.read_text()
    patro = re.compile(r'^(VERSIO\s*=\s*)["\'].*["\']', re.MULTILINE)

    if not patro.search(text):
        print(
            f"Error: no s'ha trobat cap línia 'VERSIO = \"...\"' a {main_path}.\n"
            "Actualitza-la manualment i torna a córrer amb --skip-version.",
            file=sys.stderr
        )
        sys.exit(1)

    nou_text = patro.sub(rf'\1"{versio}"', text)

    if nou_text == text:
        print(f"VERSIO ja era '{versio}', no cal canviar res.")
    else:
        main_path.write_text(nou_text)
        print(f"VERSIO actualitzada a '{versio}' dins {main_path}")


# ---------------------------------------------------------------------------
# 2. Preparar fitxers / hashes Git
# ---------------------------------------------------------------------------

def calcular_sha256_bytes(dades: bytes) -> str:
    return hashlib.sha256(dades).hexdigest()


def validar_fitxers_locals(src_dir: Path, noms_fitxers: list, max_size_kb: int):
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


def calcular_hashes_git(repo: Path, ref: str, noms_fitxers: list) -> dict:
    hashes = {}

    for nom in noms_fitxers:
        ruta_git = f"src/{nom}"
        try:
            dades = subprocess.check_output(
                ["git", "-C", str(repo), "show", f"{ref}:{ruta_git}"]
            )
        except subprocess.CalledProcessError:
            print(
                f"Error: no s'ha pogut llegir {ruta_git} de {ref}.",
                file=sys.stderr
            )
            sys.exit(1)

        hash_hex = calcular_sha256_bytes(dades)
        hashes[nom] = hash_hex
        print(f"  {nom:30s} sha256:{hash_hex}")

    return hashes


# ---------------------------------------------------------------------------
# 3. Publicar fitxers a la branca OTA sense canviar la branca actual
# ---------------------------------------------------------------------------

def publicar_branca_ota(src_dir: Path, noms_fitxers: list,
                        commit_msg: str, branca: str = "ota"):
    """
    Publica els fitxers OTA en una branca separada utilitzant un worktree
    temporal. No canvia la branca actual ni fa commits a main.
    """

    # Actualitza referències remotes.
    run(["git", "fetch", "origin"])

    # Comprova si la branca remota ja existeix.
    resultat = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branca}"]
    )
    branca_remota_existeix = resultat.returncode == 0

    # git worktree add vol una ruta que encara no existeixi.
    worktree = Path(tempfile.mkdtemp(prefix="bg95_ota_"))
    worktree.rmdir()

    try:
        if branca_remota_existeix:
            run(["git", "worktree", "add", "--detach", str(worktree), f"origin/{branca}"])
        else:
            # Primera publicació: parteix de l'HEAD actual, però sense tocar-lo.
            run(["git", "worktree", "add", "--detach", str(worktree), "HEAD"])

        # Copia només els fitxers seleccionats, mantenint-los dins src/.
        for nom in noms_fitxers:
            origen = src_dir / nom
            desti = worktree / "src" / nom
            desti.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origen, desti)
            print(f"  OTA: src/{nom}")

        run(["git", "-C", str(worktree), "add", "-A"])

        canvis = subprocess.run(
            ["git", "-C", str(worktree), "diff", "--cached", "--quiet"]
        ).returncode != 0

        if canvis:
            run(["git", "-C", str(worktree), "commit", "-m", commit_msg])
        else:
            print("La branca OTA ja conté exactament aquests fitxers.")

        # Publica l'HEAD temporal directament a origin/ota.
        run(["git", "-C", str(worktree), "push", "origin", f"HEAD:{branca}"])

        # Torna a llegir exactament el que ha quedat publicat al remot.
        run(["git", "-C", str(worktree), "fetch", "origin"])
        print("Hashes dels fitxers publicats:")
        hashes = calcular_hashes_git(
            worktree,
            f"origin/{branca}",
            noms_fitxers,
        )

        print(f"Branca '{branca}' publicada correctament.")
        return hashes

    finally:
        # Elimina el worktree encara que algun pas falli.
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if worktree.exists():
            shutil.rmtree(worktree, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4. Publicar per MQTT
# ---------------------------------------------------------------------------

def on_connect(client, userdata, flags, rc, *extra):
    # extra absorbeix 'properties' (paho-mqtt >= 2.0) sense trencar amb v1.x
    if rc == 0:
        print("Connectat al broker MQTT.")
    else:
        print(f"Error de connexió MQTT, codi: {rc}", file=sys.stderr)


def publicar_ordre_ota(versio: str, fitxers: list, hashes: dict,
                        host: str, port: int, token: str,
                        topic: str, use_tls: bool):
    ordre = {
        "cmd": "ota",
        "files": fitxers,
        "hashes": hashes,
        "version": versio,
    }

    print(f"\nVersió a publicar: {versio}")
    print(f"Fitxers: {', '.join(fitxers)}")
    print(f"Topic: {topic}")
    print(f"Broker: {host}:{port} (TLS: {use_tls})\n")

    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    else:
        client = mqtt.Client()  # paho-mqtt < 2.0

    client.username_pw_set(token, token)

    if use_tls:
        client.tls_set()

    client.on_connect = on_connect
    client.connect(host, port, keepalive=30)
    client.loop_start()

    client.publish(topic, json.dumps(ordre), qos=0, retain=True)
    print("Ordre OTA publicada.")

    client.loop_stop()
    client.disconnect()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Desplega una nova versió OTA de cap a cap.")
    parser.add_argument("version", help="Número de versió a publicar (ex: 1.4.3)")
    parser.add_argument("--src-dir", default="src", help="Directori local amb el codi del dispositiu (per defecte: src)")
    parser.add_argument("--files", nargs="+", default=["main.py"],
                         help="Fitxers a publicar per OTA (per defecte: main.py)")
    parser.add_argument("--max-size-kb", type=int, default=100)
    parser.add_argument("--mqtt-port", type=int, default=8883, help="Port MQTT per publicar (per defecte: 8883, TLS)")
    parser.add_argument("--no-tls", action="store_true")
    parser.add_argument("--commit-msg", default=None)
    parser.add_argument("--ota-branch", default="ota", help="Branca Git usada per OTA (per defecte: ota)")
    parser.add_argument("--skip-version", action="store_true")
    parser.add_argument("--skip-git", action="store_true")
    parser.add_argument("--skip-publish", action="store_true")
    args = parser.parse_args()

    src_dir = Path(args.src_dir)
    main_path = src_dir / "main.py"
    config_path = src_dir / "config.py"
    device_path = src_dir / "device.py"
    secrets_path = src_dir / "secrets.py"
    commit_msg = args.commit_msg or f"OTA v{args.version}"

    print(f"=== Desplegament OTA v{args.version} ===\n")

    # 1. Versió
    if not args.skip_version:
        print("-- Pas 1/3: actualitzar VERSIO --")
        actualitzar_versio(main_path, args.version)
    else:
        print("-- Pas 1/3: omès (--skip-version) --")

    print("\n-- Preparar OTA --")
    validar_fitxers_locals(src_dir, args.files, args.max_size_kb)

    # 2. Git: publicar només a la branca OTA
    if not args.skip_git:
        print(f"\n-- Pas 2/3: publicar branca {args.ota_branch} --")
        hashes = publicar_branca_ota(
            src_dir=src_dir,
            noms_fitxers=args.files,
            commit_msg=commit_msg,
            branca=args.ota_branch,
        )
    else:
        print("\n-- Pas 2/3: omès (--skip-git) --")
        run(["git", "fetch", "origin"])
        print(f"Hashes de origin/{args.ota_branch}:")
        hashes = calcular_hashes_git(Path("."), f"origin/{args.ota_branch}", args.files)

    # 4. Publicar (llegeix config/secrets del dispositiu, no hi ha fitxer dedicat a mantenir)
    if not args.skip_publish:
        print("\n-- Pas 3/3: publicar ordre OTA per MQTT --")

        config_modul = carregar_modul(config_path, "device_config")
        device_modul = carregar_modul(device_path, "device_config_id")
        secrets_modul = carregar_modul(secrets_path, "device_secrets")

        host = config_modul.MQTT_HOST
        token = secrets_modul.TOKEN_FLESPI_MQTT
        device_id = device_modul.DEVICE_ID
        topic_base = config_modul.TOPIC_ORDRES

        if isinstance(device_id, bytes):
            device_id = device_id.decode("utf-8")
        if isinstance(topic_base, bytes):
            topic_base = topic_base.decode("utf-8")

        topic = device_id + topic_base

        if isinstance(host, bytes):
            host = host.decode("utf-8")

        publicar_ordre_ota(
            versio=args.version,
            fitxers=args.files,
            hashes=hashes,
            host=host,
            port=args.mqtt_port,
            token=token,
            topic=topic,
            use_tls=not args.no_tls,
        )
    else:
        print("\n-- Pas 3/3: omès (--skip-publish) --")

    print(f"\n=== Desplegament v{args.version} completat ===")


if __name__ == "__main__":
    main()
