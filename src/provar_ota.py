import app_fota
from misc import Power

URL = "https://raw.githubusercontent.com/rcomellas/bg95/main/src/ota/prova_ota.py"
ota = app_fota.new()

resultat = ota.download(URL, "/usr/prova_ota.py")
print("Resultat descàrrega:", resultat)

if resultat == 0:
    ota.set_update_flag()
    print("Reiniciant...")
    Power.powerRestart()
