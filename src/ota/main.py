# region imports
import time
import ujson
import quecgnss
import pm
import checkNet
import _thread
import atcmd
from misc import Power
from umqtt import MQTTClient
import app_fota
from machine import WDT

from usr import xtra
from usr import config
from usr import secrets
# endregion imports

# region Constants
VERSIO = "1.0.1"
DEBUG = True
TAU_DEMANAT = 1800  # per tal que la xarxa em doni 60 minuts, en demano 30
# segons. Per defecte 6 segons, que és el mínim que permet la xarxa. Si es vol més temps, cal demanar-ho a l'operador.
ACTIVE_TIME = 6
TOPIC_ORDRES = b"bg95/command"
BASE_URL_OTA = "https://raw.githubusercontent.com/rcomellas/bg95/main/src/ota/"
_thread.stack_size(16 * 1024)
# endregion

wdt = WDT(180)  # en segons
fitxers_ota_pendents = None


def obtenir_posicio():
    debug("TEMPS_MAXIM_FIX:", config.TEMPS_MAXIM_FIX)
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
        debug("Sense fix GNSS. Esperant 2 segons...")
        time.sleep(2)

    return None


def convertir_coordenada(valor, hemisferi, graus):
    decimal = float(valor[:graus]) + float(valor[graus:]) / 60

    if hemisferi == "S" or hemisferi == "W":
        decimal = -decimal

    return round(decimal, 6)


def temps_transcorregut(inici):
    return time.ticks_diff(time.ticks_ms(), inici) // 1000


def debug(*args):
    if DEBUG:
        print(*args)


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

    inici = time.ticks_ms()

    client.connect()

    client.subscribe(TOPIC_ORDRES, 0)

    _thread.start_new_thread(escoltar_mqtt, (client,))

    if posicio:
        latitud, longitud, satel_lits = posicio

        missatge = {
            "id": config.DEVICE_ID,
            "latitude": latitud,
            "longitude": longitud,
            "sat": satel_lits
        }

        client.publish(
            config.TOPIC_POSICIO,
            ujson.dumps(missatge),
            True
        )

    status["mqtt_time"] = temps_transcorregut(inici)

    client.publish(
        config.TOPIC_STATUS,
        ujson.dumps(status),
        True
    )

    if fitxers_ota_pendents:
        executar_ota(fitxers_ota_pendents, client)
        return
    debug(posicio, status)
    time.sleep(1)
    client.disconnect()


def escoltar_mqtt(client):
    try:
        client.wait_msg()
    except Exception as error:
        pass


def processar_ordre(topic, missatge):
    global fitxers_ota_pendents

    try:
        ordre = ujson.loads(missatge)

        if ordre.get("cmd") == "ota":
            fitxers_ota_pendents = ordre.get("files")

    except Exception as error:
        pass


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

    # Esborra l’ordre retained
    client.publish(TOPIC_ORDRES, b"", True)
    client.disconnect()

    ota.set_update_flag()  # OTA preparada. Reinicia
    Power.powerRestart()


def main():
    # Evita que el PSM anterior talli el GNSS mentre busca fix
    pm.autosleep(0)

    if pm.get_psm_time()[0]:
        pm.set_psm_time(0)

    inici = time.ticks_ms()
    stage, state = checkNet.waitNetworkReady(30)
    net_time = temps_transcorregut(inici)
    wdt.feed()

    if stage == 3 and state == 1:
        try:
            quecgnss.gnssEnable(0)

            xtra.actualitzar_si_cal()
        except Exception as error:
            pass

        quecgnss.setPriority(0)

        if quecgnss.init() != 0:
            posicio = None
            gnss_time = 0

        else:
            inici = time.ticks_ms()
            posicio = obtenir_posicio()
            gnss_time = temps_transcorregut(inici)
            wdt.feed()
            debug("Posició obtinguda en", gnss_time, "segons:", posicio)
            quecgnss.gnssEnable(0)

        unitat_tau, valor_tau = (
            (5, TAU_DEMANAT // 60)
            if TAU_DEMANAT < 3600
            else (1, TAU_DEMANAT // 3600)
        )

        pm.set_psm_time(unitat_tau, valor_tau, 0, ACTIVE_TIME // 2)

        time.sleep(5)

        tau_net, active_time = obtenir_psm_negociat()

        status = {
            "version": VERSIO,
            "bat": Power.getVbatt(),
            "tau_req": TAU_DEMANAT,
            "tau_net": tau_net,
            "active_time": active_time,
            "net_time": net_time,
            "gnss_time": gnss_time,
            "fix": posicio is not None
        }

        try:
            publicar_mqtt(posicio, status)
            debug("Publicat MQTT posicio: ", posicio, "status:", status)
            wdt.feed()
        except Exception as error:
            pass

    pm.autosleep(1)
    time.sleep(120)


main()
