""" 
Programa geolocalització en QuecPython per a mòdul BG95-M3,
amb localització GPS, comunicació LTE-M i PSM (baix consum)

Coordina:
- Obtenció de la posició GNSS.
- Comunicació LTE-M/MQTT.
- Mode de tracking.
- Actualització OTA.
- Configuració i entrada en PSM.
"""

from usr.mqtt import *
from usr.psm import *
from usr.gnss import *


despertar()

posicio = (42, 1.9, 4)
# posicio = obtenir_posicio()

connectar_mqtt()
# connectar_xarxa()
publicar_posicio(posicio)

if tracking_actiu():
    esperar_tracking()

    while tracking_actiu():
        posicio = obtenir_posicio()
        publicar_posicio(posicio)
        esperar_tracking()

if ota_pendent():
    actualitzar_programa()

preparar_psm()

publicar_status()

dormir()
