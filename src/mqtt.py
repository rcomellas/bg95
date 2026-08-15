import atcmd
import checkNet
import utime
import ujson
import _thread
import quecgnss
from umqtt import MQTTClient
import app_fota
from misc import Power

from usr import config
from usr import secrets
from usr.power import dormir
from usr.utils import debug, temps_transcorregut

TOPIC_ORDRES = b"bg95/command"

ordre_rebuda = False
fitxers_ota_pendents = None

estat_tracking = False
tracking_interval = config.TRACKING_INTERVAL_DEFECTE
tracking_max = config.TRACKING_MAX_DEFECTE
tracking_inici = None

net_time = 0
mqtt_time = 0
client = None


def connectar_xarxa():
    global net_time
    inici = utime.ticks_ms()
    stage, state = checkNet.waitNetworkReady(30)
    net_time = utime.ticks_diff(
        utime.ticks_ms(),
        inici
    ) // 1000

    if stage != 3 or state != 1:
        dormir()


def connectar_mqtt():
    global mqtt_time
    global client

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

    client.set_callback(processar_ordre)

    quecgnss.setPriority(1)
    utime.sleep(1)

    client.connect()
    client.subscribe(TOPIC_ORDRES, 0)

    _thread.start_new_thread(
        escoltar,
        ()
    )

    mqtt_time = temps_transcorregut(inici)


def publicar_posicio(posicio):
    if not posicio:
        return

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


def publicar_status(status):
    client.publish(
        config.TOPIC_STATUS,
        ujson.dumps(status),
        True
    )


def escoltar():
    global ordre_rebuda

    while True:
        try:
            client.wait_msg()

            if ordre_rebuda:
                client.publish(TOPIC_ORDRES, b"", True)
                ordre_rebuda = False

        except Exception as error:
            debug("Escolta MQTT aturada:", error)
            break


def processar_ordre(topic, missatge):
    global fitxers_ota_pendents
    global ordre_rebuda
    global estat_tracking
    global tracking_interval
    global tracking_max
    global tracking_inici

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
                ordre.get(
                    "interval",
                    config.TRACKING_INTERVAL_DEFECTE
                ),
                config.TRACKING_INTERVAL_MAX
            )

            tracking_max = ordre.get(
                "max",
                config.TRACKING_MAX_DEFECTE
            )

            tracking_inici = utime.ticks_ms()
            estat_tracking = True
            ordre_rebuda = True

        elif cmd == "track_stop":
            estat_tracking = False
            ordre_rebuda = True

    except Exception as error:
        debug("Error processant ordre MQTT:", error)


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
        "utf-8", "ignore"
    ).replace("\x00", "")

    try:
        dades = text.split(":")[1].strip().split(",")
        return int(dades[2]), int(dades[4])

    except Exception:
        return None, None


def tracking_actiu():
    return estat_tracking


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
