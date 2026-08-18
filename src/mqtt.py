import app_fota
import quecgnss
import checkNet
import net
import utime
import ujson
import _thread

from umqtt import MQTTClient
from misc import Power

from usr import config,  gnss, secrets, psm
from usr.utils import debug, temps_transcorregut, watchdog


ordre_rebuda = False
fitxers_ota_pendents = None

net_time = 0
mqtt_time = 0
client = None


def connectar_xarxa():
    global net_time

    quecgnss.gnssEnable(0)
    quecgnss.setPriority(1)

    while True:
        stage, state = 0, 0
        watchdog.feed()

        if stage == 3 and state == 1:
            return

        net.setModemFun(0)

        utime.sleep(config.TEMPS_REINTENT_XARXA)

        net.setModemFun(1)


def connectar_mqtt():
    global mqtt_time
    global client

    stage, state = checkNet.waitNetworkReady(config.TEMPS_INTENT_XARXA)

    if not (stage == 3 and state == 1):
        debug("Xarxa no disponible")

        while True:
            watchdog.feed()
            utime.sleep(1)

    inici = utime.ticks_ms()

    client = MQTTClient(
        config.DEVICE_ID,
        config.MQTT_HOST,
        port=config.MQTT_PORT,
        user=secrets.TOKEN_FLESPI_MQTT,
        password=secrets.TOKEN_FLESPI_MQTT,
        reconn=False
    )

    client.set_callback(processar_ordre)

    client.connect()
    client.subscribe(config.TOPIC_ORDRES, 0)

    _thread.start_new_thread(escoltar, ())

    mqtt_time = temps_transcorregut(inici)


def publicar_posicio(posicio):
    if posicio:
        latitud, longitud, satel_lits = posicio

        client.publish(
            config.TOPIC_POSICIO,
            ujson.dumps({
                "id": config.DEVICE_ID,
                "latitude": latitud,
                "longitude": longitud,
                "sat": satel_lits
            }),
            True
        )

        debug(
            "Publicada posició:",
            posicio
        )


def publicar_status():
    rsrp, rsrq = obtenir_senyal_xarxa()

    status = {
        "version": config.VERSIO,
        "bat": Power.getVbatt(),
        # "hora": utime.localtime(),
        "tau_req": psm.tau_demanat,
        "tau_net": psm.tau_net,
        "active_time": psm.active_time,
        "net_time": net_time,
        "gnss_time": gnss.gnss_time,
        "mqtt_time": mqtt_time,
        "fix": gnss.ultima_posicio is not None,
        "rsrp": rsrp,
        "rsrq": rsrq
    }

    client.publish(
        config.TOPIC_STATUS,
        ujson.dumps(status),
        True
    )
    debug("Status publicat:", status)
    client.disconnect()


def escoltar():
    global ordre_rebuda

    while True:

        try:
            client.wait_msg()

            if ordre_rebuda:
                client.publish(
                    config.TOPIC_ORDRES,
                    b"",
                    True
                )

                ordre_rebuda = False

        except Exception as error:
            debug(
                "Escolta MQTT aturada:",
                error
            )

            break


def processar_ordre(topic, missatge):
    global fitxers_ota_pendents
    global ordre_rebuda

    if not missatge:
        return

    try:
        debug(
            "Ordre MQTT rebuda:",
            missatge
        )

        ordre = ujson.loads(missatge)
        cmd = ordre.get("cmd")

        if cmd == "ota":
            fitxers_ota_pendents = ordre.get("files")
            ordre_rebuda = True

        elif cmd == "track_start":
            gnss.tracking_interval = min(
                ordre.get(
                    "interval",
                    config.TRACKING_INTERVAL_DEFECTE
                ),
                config.TRACKING_INTERVAL_MAX
            )

            gnss.tracking_max = min(
                ordre.get(
                    "max",
                    config.TRACKING_MAX_DEFECTE
                ),
                config.TRACKING_MAX_DEFECTE
            )

            gnss.tracking_inici = utime.ticks_ms()
            gnss.estat_tracking = True
            ordre_rebuda = True

        elif cmd == "track_stop":
            gnss.estat_tracking = False
            ordre_rebuda = True

    except Exception as error:
        debug(
            "Error processant ordre MQTT:",
            error
        )


def obtenir_senyal_xarxa():
    senyal = net.getSignal()

    if senyal == -1:
        return None, None

    return senyal[1][1], senyal[1][2]


def ota_pendent():
    return fitxers_ota_pendents


def actualitzar_programa():
    ota = app_fota.new()

    for nom in fitxers_ota_pendents:
        resultat = ota.download(
            config.BASE_URL_OTA + nom,
            "/usr/" + nom
        )

        if resultat != 0:
            client.disconnect()
            return

    client.disconnect()

    ota.set_update_flag()

    Power.powerRestart()


def desconnectar_mqtt():
    client.disconnect()
    debug("MQTT desconnectat")
