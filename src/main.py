from usr.gnss import *
from usr.mqtt import *
from usr.power import *
from usr.app import *
import usr.mqtt as mqtt

preparar_sistema()

esperar_xarxa()

obtenir_fix()

mqtt.publicar(posicio)

while mqtt.tracking_actiu:
    esperar()
    obtenir_fix()
    mqtt.publicar(posicio)

construir_status()

mqtt.publicar(status)

entrar_psm()
