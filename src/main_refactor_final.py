import utime
import checkNet
from misc import Power
from machine import WDT

from usr import gnss
from usr import mqtt
from usr import ota
from usr import power
from usr import config

VERSIO = "1.0.4"
DEBUG = True

tracking_actiu = False
tracking_interval = config.TRACKING_INTERVAL_DEFECTE
tracking_max = config.TRACKING_MAX_DEFECTE
tracking_inici = None
fitxers_ota_pendents = None

wdt = WDT(180)


def debug(*args):
    if DEBUG:
        print(*args)


def preparar_sistema():
    power.preparar_despertar()


def esperar_xarxa():
    inici = utime.ticks_ms()

    stage, state = checkNet.waitNetworkReady(30)
    net_time = utime.ticks_diff(utime.ticks_ms(), inici) // 1000

    wdt.feed()

    if stage != 3 or state != 1:
        power.dormir_sense_mqtt()
        return None

    return net_time


def processar_ordre(topic, missatge):
    global tracking_actiu
    global tracking_interval
    global tracking_max
    global tracking_inici
    global fitxers_ota_pendents

    if not missatge:
        return

    try:
        ordre = mqtt.llegir_ordre(missatge)
        cmd = ordre.get("cmd")

        if cmd == "ota":
            fitxers_ota_pendents = ordre.get("files")

        elif cmd == "track_start":
            tracking_interval = min(
                ordre.get("interval", config.TRACKING_INTERVAL_DEFECTE),
                config.TRACKING_INTERVAL_MAX
            )
            tracking_max = ordre.get(
                "max",
                config.TRACKING_MAX_DEFECTE
            )
            tracking_inici = utime.ticks_ms()
            tracking_actiu = True

        elif cmd == "track_stop":
            tracking_actiu = False

    except Exception as error:
        debug("Error processant ordre MQTT:", error)


def esperar():
    global tracking_actiu

    utime.sleep(tracking_interval)

    if tracking_inici is not None:
        if utime.ticks_diff(
            utime.ticks_ms(),
            tracking_inici
        ) >= tracking_max * 1000:
            tracking_actiu = False


def construir_status():
    tau_demanat, tau_net, active_time = power.preparar_psm()
    rsrp, rsrq = mqtt.obtenir_senyal_xarxa()

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


preparar_sistema()

net_time = esperar_xarxa()

posicio, gnss_time = gnss.obtenir_fix()

client, mqtt_time = mqtt.connectar(processar_ordre)

mqtt.publicar_posicio(client, posicio)

while tracking_actiu:
    esperar()

    posicio, _ = gnss.obtenir_fix()

    mqtt.publicar_posicio(client, posicio)

gnss.apagar()

if fitxers_ota_pendents:
    ota.actualitzar(fitxers_ota_pendents, client)

status = construir_status()

mqtt.publicar_status(client, status)

wdt.feed()

power.entrar_psm(client)
