import utime
import ujson
from misc import Power

from usr import config
from usr import gnss
from usr import mqtt
from usr import psm


fitxers_ota_pendents = None


def debug(*args):
    if config.DEBUG:
        print(*args)


def esperar_tracking():
    utime.sleep(mqtt.tracking_interval)

    if mqtt.tracking_inici is not None:
        if utime.ticks_diff(
            utime.ticks_ms(),
            mqtt.tracking_inici
        ) >= mqtt.tracking_max * 1000:
            mqtt.tracking_actiu = False


def ota_pendent():
    return fitxers_ota_pendents


def construir_status():
    tau_demanat, tau_net, active_time = psm.preparar_psm()
    rsrp, rsrq = mqtt.obtenir_senyal_xarxa()

    return {
        "version": config.VERSIO,
        "bat": Power.getVbatt(),
        "hora": utime.localtime(),
        "tau_req": tau_demanat,
        "tau_net": tau_net,
        "active_time": active_time,
        "net_time": mqtt.net_time,
        "gnss_time": gnss.gnss_time,
        "mqtt_time": mqtt.mqtt_time,
        "fix": gnss.ultima_posicio is not None,
        "rsrp": rsrp,
        "rsrq": rsrq
    }
