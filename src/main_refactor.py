# region imports

import utime
import ujson
import checkNet
import atcmd
from misc import Power
from machine import WDT

from usr import gnss
from usr import mqtt
from usr import power
from usr import ota
from usr import config
from usr import secrets

# endregion imports


# region Constants

VERSIO = "1.0.4"
DEBUG = True


TRACKING_INTERVAL_DEFECTE = 30
TRACKING_INTERVAL_MAX = 120
TRACKING_MAX_DEFECTE = 600


_thread.stack_size(16 * 1024)

# endregion

wdt = WDT(180)

fitxers_ota_pendents = None
ordre_rebuda = False

tracking_actiu = False
tracking_interval = TRACKING_INTERVAL_DEFECTE
tracking_max = TRACKING_MAX_DEFECTE
tracking_inici = None


def ordre_rebuda_actual():
    return ordre_rebuda


def marcar_ordre_netejada():
    global ordre_rebuda
    ordre_rebuda = False


def temps_transcorregut(inici):
    return utime.ticks_diff(utime.ticks_ms(), inici) // 1000


def debug(*args):
    if DEBUG:
        print(*args)


def obtenir_senyal():
    resposta = bytearray(100)

    ret = atcmd.sendSync(
        "AT+QCSQ\r\n",
        resposta,
        "",
        2
    )

    if ret != 0:
        return None, None

    text = bytes(resposta).decode("utf-8", "ignore").replace("\x00", "")

    try:
        dades = text.split(":")[1].strip().split(",")
        return int(dades[2]), int(dades[4])

    except Exception:
        return None, None



def preparar_sistema():
    power.preparar_despertar()


def esperar_connexio_xarxa():
    inici = utime.ticks_ms()
    stage, state = checkNet.waitNetworkReady(30)
    net_time = temps_transcorregut(inici)
    wdt.feed()

    if stage != 3 or state != 1:
        power.dormir_sense_mqtt()
        return None

    return net_time


def esperar_interval_tracking():
    utime.sleep(tracking_interval)


def construir_status(posicio, net_time, gnss_time, mqtt_time,
                     tau_demanat, tau_net, active_time):
    rsrp, rsrq = obtenir_senyal()

    return {
        "version": VERSIO,
        "bat": Power.getVbatt(),
        "hora": utime.localtime(),
        "tau_req": tau_demanat,
        "tau_net": tau_net,
        "active_time": active_time,
        "net_time": net_time,
        "gnss_time": gnss_time,
        "mqtt_time": mqtt_time,
        "fix": posicio is not None,
        "rsrp": rsrp,
        "rsrq": rsrq
    }


def processar_ordre(topic, missatge):
    global fitxers_ota_pendents
    global tracking_actiu
    global tracking_interval
    global tracking_max
    global tracking_inici
    global ordre_rebuda

    if not missatge:
        return

    try:
        debug("Ordre MQTT rebuda:", missatge)

        ordre = ujson.loads(missatge)
        cmd = ordre.get("cmd")

        if cmd == "ota":
            fitxers_ota_pendents = ordre.get("files")
            ordre_rebuda = True

        elif cmd == "track_start":
            tracking_interval = min(
                ordre.get("interval",
                          TRACKING_INTERVAL_DEFECTE),
                TRACKING_INTERVAL_MAX
            )

            tracking_max = ordre.get(
                "max",
                TRACKING_MAX_DEFECTE
            )

            tracking_inici = utime.ticks_ms()
            tracking_actiu = True
            ordre_rebuda = True

        elif cmd == "track_stop":
            tracking_actiu = False
            ordre_rebuda = True

    except Exception as error:
        debug("Error processant ordre MQTT:", error)


def main():
    global tracking_actiu
    global tracking_inici
    global fitxers_ota_pendents

    preparar_sistema()

    net_time = esperar_connexio_xarxa()
    if net_time is None:
        return

    posicio, gnss_time = gnss.obtenir_fix(wdt)

    try:
        client, mqtt_time = mqtt.connectar(
            processar_ordre,
            ordre_rebuda_actual,
            marcar_ordre_netejada
        )
    except Exception as error:
        debug("Error connectant MQTT:", error)
        power.dormir_sense_mqtt()
        return

    try:
        mqtt.publicar_posicio(client, posicio)
    except Exception as error:
        debug("Error publicant posició:", error)

    utime.sleep(1)

    while tracking_actiu:
        if utime.ticks_diff(utime.ticks_ms(), tracking_inici) >= tracking_max * 1000:
            tracking_actiu = False
            break

        if fitxers_ota_pendents:
            ota.executar_ota(fitxers_ota_pendents, client)
            return

        esperar_interval_tracking()

        if not tracking_actiu:
            break

        if utime.ticks_diff(utime.ticks_ms(), tracking_inici) >= tracking_max * 1000:
            tracking_actiu = False
            break

        posicio, _ = gnss.obtenir_fix(wdt)

        if posicio:
            try:
                mqtt.publicar_posicio(client, posicio)
            except Exception as error:
                debug("Error MQTT tracking:", error)

    gnss.apagar()
    tracking_inici = None

    if fitxers_ota_pendents:
        ota.executar_ota(fitxers_ota_pendents, client)
        return

    tau_demanat, tau_net, active_time = power.preparar_psm()

    status = construir_status(
        posicio,
        net_time,
        gnss_time,
        mqtt_time,
        tau_demanat,
        tau_net,
        active_time
    )

    try:
        mqtt.publicar_status(client, status)
    except Exception as error:
        debug("Error publicant status:", error)

    wdt.feed()

    power.entrar_psm(client)


main()
