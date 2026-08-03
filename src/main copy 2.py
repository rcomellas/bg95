import time
import ujson
import checkNet
import _thread

from umqtt import MQTTClient
from usr import config
from usr import secrets


TOPIC = b"bg95/command"
missatge_rebut = False


def callback(topic, missatge):
    global missatge_rebut

    print("Rebut:", topic, missatge)

    try:
        print("JSON:", ujson.loads(missatge))
    except Exception:
        pass

    missatge_rebut = True


def escoltar_mqtt(client):
    print("Fil MQTT esperant...")

    try:
        client.wait_msg()
        print("Fil MQTT finalitzat")
    except Exception as error:
        print("Error fil MQTT:", error)


stage, state = checkNet.waitNetworkReady(30)
print("Xarxa:", stage, state)

if stage != 3 or state != 1:
    raise Exception("Xarxa no disponible")


client = MQTTClient(
    "BG95_PROVA_FIL",
    config.MQTT_HOST,
    port=config.MQTT_PORT,
    user=secrets.TOKEN_FLESPI_MQTT,
    password=secrets.TOKEN_FLESPI_MQTT
)

client.set_callback(callback)

print("Connectant...")
print("Connectat:", client.connect())

client.subscribe(TOPIC, 0)
print("Subscrit")

_thread.stack_size(16 * 1024)
_thread.start_new_thread(escoltar_mqtt, (client,))

print("Fil principal continua")

for segon in range(10):
    print("Principal:", segon)
    time.sleep(1)

print("Final del programa principal")
