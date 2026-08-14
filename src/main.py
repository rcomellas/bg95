from usr.gnss import *
from usr.power import *
from usr.app import *
from usr.mqtt import *

import usr.ota as ota
import utime

despertar()

connectar_xarxa()

posicio = obtenir_fix()
# posicio = (42.123456, 1.123456, 8)

connectar_mqtt()
publicar_posicio(posicio)

while tracking_actiu():
    esperar_tracking()
    # posicio = obtenir_fix()
    posicio = (42.123456, 1.123456, 8)
    publicar_posicio(posicio)

if ota_pendent():
    ota.actualitzar_programa()

# status = construir_status()

# publicar_status(client, status)

# dormir(client)
