import utime
import ujson
import _thread
import quecgnss
import atcmd
from umqtt import MQTTClient

from usr import config
from usr import secrets

TOPIC_ORDRES = b"bg95/command"


def llegir_ordre(missatge):
    return ujson.loads(missatge)


def escoltar_ordres(client):
    while True:
        try:
            client.wait_msg()
            client.publish(TOPIC_ORDRES, b"", True)

        except Exception as error:
            print("Escolta MQTT aturada:", error)
            break


def connectar(processar_ordre):
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
        escoltar_ordres,
        (client,)
    )

    mqtt_time = utime.ticks_diff(
        utime.ticks_ms(),
        inici
    ) // 1000

    return client, mqtt_time


def publicar_posicio(client, posicio):
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


def publicar_status(client, status):
    client.publish(
        config.TOPIC_STATUS,
        ujson.dumps(status),
        True
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
        "utf-8", "ignore"
    ).replace("\x00", "")

    try:
        dades = text.split(":")[1].strip().split(",")
        return int(dades[2]), int(dades[4])

    except Exception:
        return None, None
