from usr import gnss
from usr import mqtt
from usr import power


preparar_sistema()

esperar_xarxa()

gnss.obtenir_fix()

mqtt.connectar()

mqtt.publicar_posicio(client, posicio)

while tracking_actiu:
    esperar()
    gnss.obtenir_fix()
    mqtt.publicar_posicio(client, posicio)

construir_status()

mqtt.publicar_status()

power.entrar_psm(client)
