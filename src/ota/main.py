# region imports

import time
import ujson
import quecgnss
import pm
import checkNet
import _thread
import atcmd
from misc import Power
from umqtt import MQTTClient
import app_fota
from machine import WDT

from usr import xtra
from usr import config
from usr import secrets

# endregion imports

# region Constants

VERSIO = "1.0.3"
DEBUG = True

TAU_CURT = 1800
TAU_LLARG = 10800
HORA_INICI_NIT = 0
HORA_FINAL_NIT = 7
ACTIVE_TIME = 6

TRACKING_INTERVAL_DEFECTE = 30
TRACKING_MAX_DEFECTE = 600

TOPIC_ORDRES = b"bg95/command"
BASE_URL_OTA = "https://raw.githubusercontent.com/rcomellas/bg95/main/src/ota/"

_thread.stack_size(16 * 1024)

# endregion

wdt = WDT(180)

fitxers_ota_pendents = None

tracking_actiu = False
tracking_interval = TRACKING_INTERVAL_DEFECTE
tracking_max = TRACKING_MAX_DEFECTE
tracking_inici = None


def obtenir_posicio():
    debug("TEMPS_MAXIM_FIX:", config.TEMPS_MAXIM_FIX)

    inici = time.ticks_ms()

    while time.ticks_diff(time.ticks_ms(), inici) < config.TEMPS_MAXIM_FIX * 1000:
        resultat = quecgnss.read(4096)

        if resultat != -1 and resultat[0] > 0:
            dades = resultat[1]

            if isinstance(dades, bytes):
                dades = dades.decode("utf-8", "ignore")

            rmc = None
            gga = None

            for linia in dades.split("\r\n"):
                if linia.startswith("$GPRMC"):
                    camps = linia.split(",")

                    if len(camps) > 6 and camps[2] == "A":
                        rmc = camps

                elif linia.startswith("$GPGGA"):
                    camps = linia.split(",")

                    if len(camps) > 9 and camps[6] != "0":
                        gga = camps

            if rmc:
                latitud = convertir_coordenada(rmc[3], rmc[4], 2)
                longitud = convertir_coordenada(rmc[5], rmc[6], 3)
                satel_lits = int(gga[7]) if gga and gga[7] else 0

                return latitud, longitud, satel_lits

        debug("Sense fix GNSS. Esperant 2 segons...")
        time.sleep(2)

    return None


def convertir_coordenada(valor, hemisferi, graus):
    decimal = float(valor[:graus]) + float(valor[graus:]) / 60

    if hemisferi == "S" or hemisferi == "W":
        decimal = -decimal

    return round(decimal, 6)


def temps_transcorregut(inici):
    return time.ticks_diff(time.ticks_ms(), inici) // 1000


def debug(*args):
    if DEBUG:
        print(*args)


def obtenir_senyal():
    resposta = bytearray(100)

    ret = atcmd.sendSync("AT+QCSQ\r\n", resposta, "", 2)

    if ret != 0:
        return None, None

    text = bytes(resposta).decode("utf-8", "ignore").replace("\x00", "")

    try:
        dades = text.split(":")[1].strip().split(",")
        return int(dades[2]), int(dades[4])

    except Exception:
        return None, None


def tau_a_demanar():
    hora_futura = (time.localtime()[3] + TAU_LLARG // 3600) % 24

    return (
        TAU_LLARG
        if HORA_INICI_NIT <= hora_futura < HORA_FINAL_NIT
        else TAU_CURT
    )


def obtenir_psm_negociat():
    resposta = bytearray(100)

    ret = atcmd.sendSync(
        "AT+QPSMS?\r\n",
        resposta,
        "",
        2
    )

    if ret != 0:
        return None, None

    text = bytes(resposta).decode("utf-8", "ignore")
    valors = text.split('"')

    try:
        return int(valors[1]), int(valors[3])

    except Exception:
        return None, None


def publicar_posicio(client, posicio):
    if not posicio:
        return

    latitud, longitud, satel_lits = posicio

    missatge = {
        "id": config.DEVICE_ID,
        "latitude": latitud,
        "longitude": longitud,
        "sat": satel_lits
    }

    client.publish(
        config.TOPIC_POSICIO,
        ujson.dumps(missatge),
        True
    )


def publicar_mqtt(posicio, status):
    global fitxers_ota_pendents

    client = MQTTClient(
        config.DEVICE_ID,
        config.MQTT_HOST,
        port=config.MQTT_PORT,
        user=secrets.TOKEN_FLESPI_MQTT,
        password=secrets.TOKEN_FLESPI_MQTT
    )

    client.set_callback(processar_ordre)

    inici = time.ticks_ms()

    client.connect()
    client.subscribe(TOPIC_ORDRES, 0)

    _thread.start_new_thread(escoltar_mqtt, (client,))

    publicar_posicio(client, posicio)

    status["mqtt_time"] = temps_transcorregut(inici)

    client.publish(
        config.TOPIC_STATUS,
        ujson.dumps(status),
        True
    )

    time.sleep(1)

    if fitxers_ota_pendents:
        executar_ota(fitxers_ota_pendents, client)

    return client


def escoltar_mqtt(client):
    while True:
        try:
            client.wait_msg()

        except Exception:
            break


def processar_ordre(topic, missatge):
    global fitxers_ota_pendents
    global tracking_actiu
    global tracking_interval
    global tracking_max
    global tracking_inici

    try:
        debug("Ordre MQTT rebuda:", missatge)

        ordre = ujson.loads(missatge)

        cmd = ordre.get("cmd")

        if cmd == "ota":
            fitxers_ota_pendents = ordre.get("files")

        elif cmd == "track_start":
            tracking_interval = ordre.get(
                "interval",
                TRACKING_INTERVAL_DEFECTE
            )

            tracking_max = ordre.get(
                "max",
                TRACKING_MAX_DEFECTE
            )

            tracking_inici = time.ticks_ms()
            tracking_actiu = True

        elif cmd == "track_stop":
            tracking_actiu = False

    except Exception as error:
        debug("Error processant ordre MQTT:", error)


def executar_ota(fitxers, client):
    ota = app_fota.new()

    for nom in fitxers:
        resultat = ota.download(
            BASE_URL_OTA + nom,
            "/usr/" + nom
        )

        if resultat != 0:
            client.disconnect()
            return

    client.publish(TOPIC_ORDRES, b"", True)
    client.disconnect()

    ota.set_update_flag()
    Power.powerRestart()


def main():
    global tracking_actiu
    global tracking_inici

    pm.autosleep(0)

    if pm.get_psm_time()[0]:
        pm.set_psm_time(0)

    inici = time.ticks_ms()
    stage, state = checkNet.waitNetworkReady(30)
    net_time = temps_transcorregut(inici)

    wdt.feed()

    if stage == 3 and state == 1:

        try:
            quecgnss.gnssEnable(0)
            xtra.actualitzar_si_cal()

        except Exception:
            pass

        quecgnss.setPriority(0)

        if quecgnss.init() != 0:
            posicio = None
            gnss_time = 0

        else:
            inici = time.ticks_ms()

            posicio = obtenir_posicio()

            gnss_time = temps_transcorregut(inici)

            wdt.feed()

            debug(
                "Posició obtinguda en",
                gnss_time,
                "segons:",
                posicio
            )

            quecgnss.gnssEnable(0)

        tau_demanat = tau_a_demanar()

        unitat_tau, valor_tau = (
            (5, tau_demanat // 60)
            if tau_demanat < 3600
            else (1, tau_demanat // 3600)
        )

        pm.set_psm_time(
            unitat_tau,
            valor_tau,
            0,
            ACTIVE_TIME // 2
        )

        time.sleep(2)

        tau_net, active_time = obtenir_psm_negociat()
        rsrp, rsrq = obtenir_senyal()

        status = {
            "version": VERSIO,
            "bat": Power.getVbatt(),
            "tau_req": tau_demanat,
            "tau_net": tau_net,
            "active_time": active_time,
            "net_time": net_time,
            "gnss_time": gnss_time,
            "fix": posicio is not None,
            "rsrp": rsrp,
            "rsrq": rsrq
        }

        try:
            client = publicar_mqtt(posicio, status)

            debug(
                "Publicat MQTT posicio:",
                posicio,
                "status:",
                status
            )

            wdt.feed()

            while tracking_actiu:

                if time.ticks_diff(
                    time.ticks_ms(),
                    tracking_inici
                ) >= tracking_max * 1000:
                    tracking_actiu = False
                    break

                time.sleep(tracking_interval)

                if not tracking_actiu:
                    break

                quecgnss.gnssEnable(1)

                posicio = obtenir_posicio()

                quecgnss.gnssEnable(0)

                if posicio:
                    publicar_posicio(
                        client,
                        posicio
                    )

                    debug(
                        "Tracking posicio:",
                        posicio
                    )

                else:
                    debug("Tracking sense fix")

                wdt.feed()

            client.disconnect()
            tracking_inici = None

        except Exception as error:
            debug("Error MQTT:", error)

    pm.autosleep(1)
    time.sleep(120)


main()
