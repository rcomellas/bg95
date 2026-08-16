import app_fota
import quecgnss
import dataCall
import atcmd
import utime
import ujson
import _thread

from umqtt import MQTTClient
from misc import Power

from usr import config, gnss, secrets, psm
from usr.utils import debug, temps_transcorregut
from usr.psm import dormir


ordre_rebuda = False
fitxers_ota_pendents = None

net_time = 0
mqtt_time = 0
client = None


def connectar_xarxa():
    global net_time

    quecgnss.gnssEnable(0)
    quecgnss.setPriority(1)

    inici = utime.ticks_ms()

    debug("Connectant xarxa...")

    while temps_transcorregut(inici) < 120:
        lte = dataCall.getInfo(1, 0)

        debug(lte)

        if lte[2][0] == 1:
            net_time = temps_transcorregut(inici)
            debug("Xarxa connectada")
            return

        utime.sleep(1)

    net_time = temps_transcorregut(inici)

    debug("No s'ha pogut connectar a la xarxa")

    dormir()


def connectar_mqtt():
    global client
    global mqtt_time

    connectar_xarxa()

    inici = utime.ticks_ms()

    client = MQTTClient(
        config.DEVICE_ID,
        config.MQTT_HOST,
        port=config.MQTT_PORT,
        user=secrets.TOKEN_FLESPI_MQTT,
        password=secrets.TOKEN_FLESPI_MQTT,
        reconn=False
    )

    debug("Connectant MQTT...")
    client.connect()
    debug("MQTT connectat")

    # client.disconnect()
    # debug("MQTT desconnectat")

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
        "hora": utime.localtime(),
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
    resposta = bytearray(100)

    ret = atcmd.sendSync(
        "AT+QCSQ\r\n",
        resposta,
        "",
        2
    )

    if ret != 0:
        return None, None

    text = bytes(resposta).decode(
        "utf-8",
        "ignore"
    ).replace(
        "\x00",
        ""
    )

    try:
        dades = text.split(":")[1].strip().split(",")

        return (
            int(dades[2]),
            int(dades[4])
        )

    except Exception:
        return None, None


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
