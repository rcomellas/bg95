import utime
import ujson
import _thread
import quecgnss
from umqtt import MQTTClient

from usr import config
from usr import secrets

TOPIC_ORDRES = b"bg95/command"


def temps_transcorregut(inici):
    return utime.ticks_diff(utime.ticks_ms(), inici) // 1000


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


def connectar(processar_ordre, ordre_rebuda_fn=None, ordre_netejada_fn=None):
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

    gnss.quecgnss.setPriority(1)
    utime.sleep(1)

    client.connect()

    client.subscribe(TOPIC_ORDRES, 0)

    _thread.start_new_thread(
        escoltar,
        (client, ordre_rebuda_fn, ordre_netejada_fn)
    )

    mqtt_time = temps_transcorregut(inici)

    return client, mqtt_time


def escoltar(client, ordre_rebuda_fn=None, ordre_netejada_fn=None):

    while True:
        try:
            client.wait_msg()

            if ordre_rebuda_fn and ordre_rebuda_fn():
                client.publish(TOPIC_ORDRES, b"", True)
                if ordre_netejada_fn:
                    ordre_netejada_fn()

        except Exception as error:
            debug("escoltar_mqtt aturat:", error)
            break
