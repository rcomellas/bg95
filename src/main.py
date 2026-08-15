from usr.gnss import *
from usr.power import *
from usr.app import *
from usr.mqtt import *


despertar()

posicio = obtenir_posicio()
# posicio = (42.123456, 1.123456, 8)

connectar_mqtt()

publicar_posicio(posicio)

while tracking_actiu():
    esperar_tracking()
    # posicio = obtenir_posicio()
    posicio = (42.123456, 1.123456, 8)
    publicar_posicio(posicio)

if ota_pendent():
    actualitzar_programa()

status = construir_status()

publicar_status(status)

dormir()
