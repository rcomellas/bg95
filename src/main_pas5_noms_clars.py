# region imports

import utime
import ujson
import checkNet
import atcmd
from misc import Power
from machine import WDT

from usr import xtra
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


def calcular_calcular_temps_transcorregut(inici):
    return utime.ticks_diff(utime.ticks_ms(), inici) // 1000


def debug(*args):
    if DEBUG:
        print(*args)


def obtenir_senyal_xarxa():
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


def processar_ordre_mqtt(topic, missatge):
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



def preparar_sistema():
    power.preparar_despertar()


def esperar_connexio_xarxa():
    inici = utime.ticks_ms()

    stage, state = checkNet.waitNetworkReady(30)
    temps_xarxa = calcular_temps_transcorregut(inici)

    wdt.feed()

    return stage, state, temps_xarxa


def preparar_gnss():
    if DEBUG:
        resposta = bytearray(100)
        atcmd.sendSync('AT+QGPSCFG="xtra_info"\r\n', resposta, "", 5)
        text = bytes(resposta).decode(
            "utf-8", "ignore"
        ).replace("\x00", "").strip()
        debug("XTRA info:", text)

    gnss.quecgnss.gnssEnable(0)
    gnss.quecgnss.setPriority(0)


def obtenir_fix_gnss():
    if gnss.quecgnss.init() != 0:
        return None, 0

    gnss.quecgnss.gnssEnable(1)

    inici = utime.ticks_ms()
    posicio = gnss.obtenir_posicio()
    temps_gnss = calcular_temps_transcorregut(inici)

    wdt.feed()

    debug(
        "Posició obtinguda en",
        temps_gnss,
        "segons:",
        posicio
    )

    return posicio, temps_gnss


def esperar_interval_tracking():
    debug(
        "Tracking: espero",
        tracking_interval,
        "segons"
    )
    utime.sleep(tracking_interval)


def construir_status(posicio, temps_xarxa, temps_gnss, temps_mqtt,
                     tau_demanat, tau_xarxa, temps_actiu):
    rsrp, rsrq = obtenir_senyal_xarxa()

    return {
        "version": VERSIO,
        "bat": Power.getVbatt(),
        "hora": utime.localtime(),
        "tau_req": tau_demanat,
        "tau_net": tau_xarxa,
        "active_time": temps_actiu,
        "net_time": temps_xarxa,
        "gnss_time": temps_gnss,
        "mqtt_time": temps_mqtt,
        "fix": posicio is not None,
        "rsrp": rsrp,
        "rsrq": rsrq
    }


def main():
    global tracking_actiu
    global tracking_inici
    global fitxers_ota_pendents

    preparar_sistema()

    stage, state, temps_xarxa = esperar_connexio_xarxa()

    if stage != 3 or state != 1:
        power.dormir_sense_mqtt()
        return

    preparar_gnss()

    posicio, temps_gnss = obtenir_fix_gnss()

    try:
        client, temps_mqtt = mqtt.connectar(
            processar_ordre_mqtt,
            ordre_rebuda_actual,
            marcar_ordre_netejada
        )

    except Exception as error:
        debug("Error connectant MQTT:", error)
        power.dormir_sense_mqtt()
        return

    try:
        mqtt.publicar_posicio(client, posicio)
        debug("Publicada posició:", posicio)

    except Exception as error:
        debug("Error publicant posició:", error)

    utime.sleep(1)

    while tracking_actiu:
        debug("Tracking actiu. Interval:", tracking_interval)

        if utime.ticks_diff(
            utime.ticks_ms(),
            tracking_inici
        ) >= tracking_max * 1000:
            debug("Final tracking: temps màxim")
            tracking_actiu = False
            break

        if fitxers_ota_pendents:
            ota.executar_ota(
                fitxers_ota_pendents,
                client
            )
            return

        esperar_interval_tracking()

        if not tracking_actiu:
            debug("Final tracking: track_stop")
            break

        if utime.ticks_diff(
            utime.ticks_ms(),
            tracking_inici
        ) >= tracking_max * 1000:
            debug("Final tracking: temps màxim")
            tracking_actiu = False
            break

        gnss.quecgnss.gnssEnable(1)

        inici = utime.ticks_ms()
        posicio = gnss.obtenir_posicio()
        temps_gnss_tracking = calcular_temps_transcorregut(inici)

        wdt.feed()

        if posicio:
            try:
                mqtt.publicar_posicio(
                    client,
                    posicio
                )

                debug(
                    "Tracking posició:",
                    posicio,
                    "GNSS:",
                    temps_gnss_tracking,
                    "s"
                )

            except Exception as error:
                debug(
                    "Error MQTT tracking:",
                    error
                )

        else:
            debug("Tracking sense fix")

    gnss.quecgnss.gnssEnable(0)
    tracking_inici = None

    if fitxers_ota_pendents:
        ota.executar_ota(
            fitxers_ota_pendents,
            client
        )
        return

    tau_demanat, tau_xarxa, temps_actiu = power.preparar_psm()

    status = construir_status(
        posicio,
        temps_xarxa,
        temps_gnss,
        temps_mqtt,
        tau_demanat,
        tau_xarxa,
        temps_actiu
    )

    try:
        client.publish(
            config.TOPIC_STATUS,
            ujson.dumps(status),
            True
        )

        debug(
            "Publicat status:",
            status
        )

    except Exception as error:
        debug(
            "Error publicant status:",
            error
        )

    wdt.feed()

    power.entrar_psm(client)


main()
