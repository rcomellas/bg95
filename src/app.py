import utime
import checkNet
from misc import Power

from usr import gnss
from usr import mqtt
from usr import power


VERSIO = "1.0.4"


def preparar_sistema():
    power.preparar_despertar()


def esperar_xarxa():
    inici = utime.ticks_ms()

    stage, state = checkNet.waitNetworkReady(30)

    mqtt.net_time = utime.ticks_diff(
        utime.ticks_ms(),
        inici
    ) // 1000

    if stage != 3 or state != 1:
        power.dormir_sense_mqtt()


def esperar():
    utime.sleep(mqtt.tracking_interval)

    if mqtt.tracking_inici is not None:
        if utime.ticks_diff(
            utime.ticks_ms(),
            mqtt.tracking_inici
        ) >= mqtt.tracking_max * 1000:
            mqtt.tracking_actiu = False


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
        "net_time": mqtt.net_time,
        "gnss_time": gnss.gnss_time,
        "mqtt_time": mqtt.mqtt_time,
        "fix": gnss.ultima_posicio is not None,
        "rsrp": rsrp,
        "rsrq": rsrq
    }
