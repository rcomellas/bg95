from usr.mqtt import *
from usr.psm import *
from usr.gnss import *


despertar()

posicio = obtenir_posicio()
# posicio = (42.123456, 1.123456, 8)  # posicio de prova

connectar_mqtt()
# connectar_xarxa()
publicar_posicio(posicio)

while tracking_actiu():
    esperar_tracking()
    posicio = obtenir_posicio()
    publicar_posicio(posicio)

if ota_pendent():
    actualitzar_programa()

preparar_psm()
# desconnectar_mqtt()
publicar_status()

dormir()
