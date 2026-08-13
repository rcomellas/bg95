import app_fota
from misc import Power

BASE_URL_OTA = "https://raw.githubusercontent.com/rcomellas/bg95/main/src/ota/"


def executar_ota(fitxers, client):
    ota = app_fota.new()

    for nom in fitxers:
        resultat = ota.download(
            BASE_URL_OTA + nom,
            "/usr/" + nom
        )

        if resultat != 0:
            client.disconnect()
            return

    client.disconnect()

    ota.set_update_flag()
    Power.powerRestart()


