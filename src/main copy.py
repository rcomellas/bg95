import time
import ujson
import quecgnss
import pm
import checkNet
import atcmd
from misc import Power
from umqtt import MQTTClient
import app_fota

from usr import xtra
from usr import config
from usr import secrets


TAU_DEMANAT = 3600
TOPIC_ORDRES = b"bg95/command"
BASE_URL_OTA = "https://raw.githubusercontent.com/rcomellas/bg95/main/ota/"

fitxers_ota_pendents = None


def processar_ordre(topic, missatge):
    global fitxers_ota_pendents

    try:
        ordre = ujson.loads(missatge)

        if ordre.get("cmd") == "ota":
            fitxers = ordre.get("files", [])

            if isinstance(fitxers, list) and fitxers:
                fitxers_ota_pendents = fitxers
                print("Ordre OTA rebuda:", fitxers)

    except Exception as error:
        print("Error processant ordre:", error)


def executar_ota(fitxers, client):
    ota = app_fota.new()

    for nom in fitxers:
        if "/" in nom or "\\" in nom or ".." in nom:
            print("Nom OTA no vàlid:", nom)
            return False

        resultat = ota.download(
            BASE_URL_OTA + nom,
            "/usr/" + nom
        )

        print("OTA:", nom, resultat)

        if resultat != 0:
            print("Error OTA:", nom)
            return False

    # Esborra l'ordre només si totes les descàrregues han funcionat
    client.publish(TOPIC_ORDRES, b"", True)
    client.disconnect()

    ota.set_update_flag()
    print("OTA preparada. Reiniciant...")
    Power.powerRestart()

    return True


def convertir_coordenada(valor, hemisferi, graus):
    decimal = float(valor[:graus]) + float(valor[graus:]) / 60

    if hemisferi == "S" or hemisferi == "W":
        decimal = -decimal

    return round(decimal, 6)


def temps_transcorregut(inici):
    return time.ticks_diff(time.ticks_ms(), inici) // 1000


def obtenir_posicio():
    inici = time.ticks_ms()

    while time.ticks_diff(time.ticks_ms(), inici) < config.TEMPS_MAXIM_FIX * 1000:
        resultat = quecgnss.read(4096)

        if resultat != -1 and resultat[0] > 0:
            dades = resultat[1]

            if isinstance(dades, bytes):
                dades = dades.decode("utf-8", "ignore")

            rmc = None
            gga = None

            for linia in dades.split("\r\n"):
                if linia.startswith("$GPRMC"):
                    camps = linia.split(",")

                    if len(camps) > 6 and camps[2] == "A":
                        rmc = camps

                elif linia.startswith("$GPGGA"):
                    camps = linia.split(",")

                    if len(camps) > 9 and camps[6] != "0":
                        gga = camps

            if rmc:
                latitud = convertir_coordenada(rmc[3], rmc[4], 2)
                longitud = convertir_coordenada(rmc[5], rmc[6], 3)
                satel_lits = int(gga[7]) if gga and gga[7] else 0

                return latitud, longitud, satel_lits

        print("Sense fix")
        time.sleep(2)

    return None


def obtenir_psm_negociat():
    resposta = bytearray(100)

    ret = atcmd.sendSync(
        "AT+QPSMS?\r\n",
        resposta,
        "",
        10
    )

    if ret != 0:
        return None, None

    text = bytes(resposta).decode("utf-8", "ignore")
    valors = text.split('"')

    try:
        return int(valors[1]), int(valors[3])
    except Exception:
        print("Resposta QPSMS no reconeguda:", text)
        return None, None


def publicar_mqtt(posicio, status):
    global fitxers_ota_pendents

    client = MQTTClient(
        config.DEVICE_ID,
        config.MQTT_HOST,
        port=config.MQTT_PORT,
        user=secrets.TOKEN_FLESPI_MQTT,
        password=secrets.TOKEN_FLESPI_MQTT
    )

    client.set_callback(processar_ordre)

    print("Connectant MQTT...")
    inici = time.ticks_ms()

    print("MQTT connectat:", client.connect())

    client.subscribe(TOPIC_ORDRES, 0)
    print("Subscrit a:", TOPIC_ORDRES)

    if posicio:
        latitud, longitud, satel_lits = posicio

        missatge = {
            "id": config.DEVICE_ID,
            "lat": latitud,
            "lon": longitud,
            "bat": Power.getVbatt(),
            "sat": satel_lits
        }

        client.publish(
            config.TOPIC_POSICIO,
            ujson.dumps(missatge),
            True
        )

        print("Enviat:", missatge)

    status["mqtt_time"] = temps_transcorregut(inici)

    client.publish(
        config.TOPIC_STATUS,
        ujson.dumps(status),
        True
    )

    client.check_msg()

    if fitxers_ota_pendents:
        fitxers = fitxers_ota_pendents
        fitxers_ota_pendents = None

        executar_ota(fitxers, client)
        return

    client.disconnect()
    print("Status:", status)


# Evita que el PSM anterior talli el GNSS mentre busca fix
pm.autosleep(0)

psm_actiu = pm.get_psm_time()[0]
if psm_actiu:
    print("PSM anterior desactivat:", pm.set_psm_time(0))

inici = time.ticks_ms()
stage, state = checkNet.waitNetworkReady(30)
net_time = temps_transcorregut(inici)

if stage == 3 and state == 1:
    print("Xarxa disponible")

    try:
        xtra.actualitzar_si_cal()
    except Exception as error:
        print("Error XTRA:", error)

    quecgnss.setPriority(0)

    if quecgnss.init() != 0:
        print("Error inicialitzant GNSS")
        posicio = None
        gnss_time = 0

    else:
        print("Esperant fix GNSS...")

        inici = time.ticks_ms()
        posicio = obtenir_posicio()
        gnss_time = temps_transcorregut(inici)

        quecgnss.gnssEnable(0)

    # TAU d'1 hora i Active Time de 30 segons
    print("PSM:", pm.set_psm_time(1, 1, 0, 15))

    time.sleep(5)

    tau_net, active_time = obtenir_psm_negociat()

    status = {
        "tau_req": TAU_DEMANAT,
        "tau_net": tau_net,
        "active_time": active_time,
        "net_time": net_time,
        "gnss_time": gnss_time,
        "fix": posicio is not None
    }

    try:
        publicar_mqtt(posicio, status)
    except Exception as error:
        print("Error MQTT:", error)

else:
    print("Sense xarxa")

pm.autosleep(1)
print("Esperant entrada en PSM...")
time.sleep(120)
