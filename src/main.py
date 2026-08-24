import utime, ujson, quecgnss, pm, checkNet, _thread, atcmd, app_fota
import ntptime
from misc import Power
from umqtt import MQTTClient
from machine import WDT
from usr import secrets, config

_thread.stack_size(16 * 1024)
mqtt_escolta_activa = False
wdt = WDT(config.TEMPS_WATCHDOG)

fitxers_ota_pendents = None
ordre_rebuda = False

tracking_actiu = False
tracking_interval = config.TRACKING_INTERVAL_DEFECTE
tracking_max = config.TRACKING_MAX_DEFECTE
tracking_inici = None
lock_tracking = _thread.allocate_lock()

# gnss

def obtenir_posicio():
    debug("TEMPS_MAXIM_FIX:", config.TEMPS_MAXIM_FIX)
    inici = utime.time()
    while temps_transcorregut(inici) < config.TEMPS_MAXIM_FIX :
        wdt.feed()

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

            if config.DEBUG:
                print("Sense fix:", temps_transcorregut(inici), "s", end=" ")

                cn0 = []

                for linia in dades.split("\r\n"):
                    if "GSV" in linia:
                        camps = linia.split(",")

                        for i in range(4, len(camps) - 3, 4):
                            try:
                                valor = int(camps[i + 3].split("*")[0])
                                if valor > 0:
                                    cn0.append(valor)
                            except:
                                pass

                if cn0:
                    print(
                        "Sat:", len(cn0),
                        "C/N0 mitjà:", sum(cn0) // len(cn0),
                        "dB-Hz"
                    )
                else:
                    print("Sat: 0 C/N0 mitjà: 0")

        utime.sleep(2)

    return None


def convertir_coordenada(valor, hemisferi, graus):
    try:
        decimal = float(valor[:graus]) + float(valor[graus:]) / 60
    except (ValueError, IndexError):
        return None

    if hemisferi in ("S", "W"):
        decimal = -decimal

    return round(decimal, 6)

# utils
def temps_transcorregut(inici):
    return utime.time() - inici
    
def debug(*args):
    if config.DEBUG:
        print(*args)


def obtenir_senyal():
    try:
        r=bytearray(100); atcmd.sendSync("AT+QCSQ\r\n",r,"",2)
        d=bytes(r).decode().split(":")[1].split(",")
        return int(d[2]),int(d[4])
    except:
        return None,None


# psm

def calcular_tau_a_demanar():
    hora = utime.localtime()[3]

    if config.HORA_INICI_TAU_LLARG <= config.HORA_FINAL_TAU_LLARG:
        dins_interval = config.HORA_INICI_TAU_LLARG <= hora <= config.HORA_FINAL_TAU_LLARG
    else:
        dins_interval = hora >= config.HORA_INICI_TAU_LLARG or hora <= config.HORA_FINAL_TAU_LLARG

    return config.TAU_LLARG if dins_interval else config.TAU_CURT


def obtenir_psm_negociat():
    resposta = bytearray(100)
    ret = atcmd.sendSync("AT+QPSMS?\r\n", resposta, "", 2)

    if ret != 0:
        return None, None

    text = bytes(resposta).decode("utf-8", "ignore")
    valors = text.split('"')

    try:
        return int(valors[1]), int(valors[3])

    except Exception:
        return None, None


def connectar_mqtt():
    global mqtt_escolta_activa

    inici = utime.time()

    client = MQTTClient(
        config.DEVICE_ID,
        config.MQTT_HOST,
        port=config.MQTT_PORT,
        user=secrets.TOKEN_FLESPI_MQTT,
        password=secrets.TOKEN_FLESPI_MQTT,
        reconn=False
    )

    client.set_callback(processar_ordre)

    quecgnss.setPriority(1)
    utime.sleep(1)

    client.connect()

    client.subscribe(config.TOPIC_ORDRES, 0)

    mqtt_escolta_activa = True

    _thread.start_new_thread(
        escoltar_mqtt,
        (client,)
    )

    mqtt_time = temps_transcorregut(inici)

    return client, mqtt_time


def publicar_posicio(client, posicio):
    if not posicio:
        return

    latitud, longitud, satel_lits = posicio

    client.publish(
        config.TOPIC_POSICIO,
        ujson.dumps({
            "id": config.DEVICE_ID,
            "latitude": latitud,
            "longitude": longitud,
            "sat": satel_lits
        }),
        True
    )


def escoltar_mqtt(client):
    global ordre_rebuda
    global mqtt_escolta_activa

    errors_consecutius = 0
    max_errors = 3
    
    while mqtt_escolta_activa:
        try:
            client.wait_msg()
            errors_consecutius = 0

            if ordre_rebuda:
                client.publish(config.TOPIC_ORDRES, b"", True)
                ordre_rebuda = False

                if fitxers_ota_pendents:
                    break
        except Exception as error:
            if not mqtt_escolta_activa:
                break

            errors_consecutius += 1
            debug("escoltar_mqtt error:", error, "(", errors_consecutius, "/", max_errors, ")")

            if errors_consecutius >= max_errors:
                debug("escoltar_mqtt aturat definitivament")
                mqtt_escolta_activa = False
                break

            utime.sleep(1)
    debug("mqtt_escolta_activa:", mqtt_escolta_activa)
    
def processar_ordre(topic, missatge):
    global fitxers_ota_pendents
    global tracking_actiu
    global tracking_interval
    global tracking_max
    global tracking_inici
    global ordre_rebuda

    if not missatge:
        return

    try:
        debug("Ordre MQTT rebuda:", missatge)

        ordre = ujson.loads(missatge)
        cmd = ordre.get("cmd")

        if cmd == "ota":
            fitxers_ota_pendents = ordre.get("files")
            ordre_rebuda = True

        elif cmd == "track_start":
            try:
                interval = int(ordre.get("interval", config.TRACKING_INTERVAL_DEFECTE))
            except (TypeError, ValueError):
                interval = config.TRACKING_INTERVAL_DEFECTE

            nou_interval = max(config.TRACKING_INTERVAL_MIN, min(interval, config.TRACKING_INTERVAL_MAX))

            try:
                nou_max = int(ordre.get("max", config.TRACKING_MAX_DEFECTE))
            except (TypeError, ValueError):
                nou_max = config.TRACKING_MAX_DEFECTE
            nou_max = max(0, nou_max)

            with lock_tracking:
                tracking_interval = nou_interval
                tracking_max = nou_max
                tracking_inici = utime.time()
                tracking_actiu = True

            ordre_rebuda = True

        elif cmd == "track_stop":
            with lock_tracking:
                tracking_actiu = False
            ordre_rebuda = True
    except Exception as error:
        debug("Error processant ordre MQTT:", error)


def executar_ota(fitxers, client):
    ota = app_fota.new()

    for nom in fitxers:
        url = config.BASE_URL_OTA + nom
        wdt.feed()

        resultat = ota.download(
            url,
            "/usr/" + nom
        )

        if resultat != 0:
            client.disconnect()
            return

    ota.set_update_flag()
    Power.powerRestart()

def main():
    global tracking_actiu
    global tracking_inici
    global fitxers_ota_pendents
    global mqtt_escolta_activa

    # pm.autosleep(0)

    if pm.get_psm_time()[0]:
        pm.set_psm_time(0)

    inici = utime.time()

    stage, state = checkNet.waitNetworkReady(30)
    net_time = temps_transcorregut(inici)

    wdt.feed()
    debug("Versió:", config.VERSIO)

    if stage != 3 or state != 1:
        pm.autosleep(1)
        utime.sleep(120)
        return

    try:
        ntptime.settime(2)
    except Exception as error:
        debug("Error NTP:", error)

    
    if config.DEBUG:
        resposta = bytearray(100)
        atcmd.sendSync('AT+QGPSCFG="xtra_info"\r\n', resposta, "", 5)
        text = bytes(resposta).decode(
            "utf-8", "ignore").replace("\x00", "").strip()
        debug("XTRA info:", text)

    quecgnss.gnssEnable(0)
    quecgnss.setPriority(0)

    if quecgnss.init() != 0:
        posicio = None
        gnss_time = 0

    else:
        quecgnss.gnssEnable(1)
        inici = utime.time()
        posicio = obtenir_posicio()
        gnss_time = temps_transcorregut(inici)
        wdt.feed()

        debug(
            "Posició obtinguda en",
            gnss_time,
            "segons:",
            posicio
        )
    quecgnss.gnssEnable(0)

    try:
        client, mqtt_time = connectar_mqtt()

    except Exception as error:
        debug("Error connectant MQTT:", error)

        pm.autosleep(1)
        utime.sleep(120)
        return

    try:
        publicar_posicio(client, posicio)
        debug("Publicada posició:", posicio)

    except Exception as error:
        debug("Error publicant posició:", error)

    # pm.autosleep(1)
    # utime.sleep(1)

    while tracking_actiu:
        with lock_tracking:
            interval_actual = tracking_interval
            max_actual = tracking_max
            inici_actual = tracking_inici

        debug("Tracking actiu. Interval:", interval_actual)
        if temps_transcorregut(inici_actual) >= max_actual:
            debug("Final tracking: temps màxim")
            with lock_tracking:
                tracking_actiu = False
            break

        if fitxers_ota_pendents:
            executar_ota(
                fitxers_ota_pendents,
                client
            )
            return

        debug("Tracking: espero", interval_actual, "segons")

        utime.sleep(interval_actual)

        with lock_tracking:
            actiu_actual = tracking_actiu

        if not actiu_actual:
            debug("Final tracking: track_stop")
            break

        with lock_tracking:
            max_actual = tracking_max
            inici_actual = tracking_inici

        if temps_transcorregut(inici_actual) >= max_actual:
            debug("Final tracking: temps màxim")
            with lock_tracking:
                tracking_actiu = False
            break

        quecgnss.gnssEnable(1)
        inici = utime.time()
        posicio = obtenir_posicio()
        gnss_tracking_time = temps_transcorregut(inici)
        # quecgnss.gnssEnable(0)
        wdt.feed()

        if posicio:
            try:
                publicar_posicio(client, posicio)
                debug("Tracking posició:", posicio, "GNSS:", gnss_tracking_time, "s")

            except Exception as error:
                debug("Error MQTT tracking:", error)

        else:
            debug("Tracking sense fix")

    quecgnss.gnssEnable(0)
    tracking_inici = None

    if fitxers_ota_pendents:
        executar_ota(
            fitxers_ota_pendents,
            client
        )
        return

    rsrp, rsrq = obtenir_senyal()
    tau_demanat = calcular_tau_a_demanar()

    unitat_tau, valor_tau = (
        (5, tau_demanat // 60)
        if tau_demanat < 3600
        else (1, tau_demanat // 3600)
    )

    pm.set_psm_time(
        unitat_tau,
        valor_tau,
        0,
        config.ACTIVE_TIME // 2
    )

    proper = None
    for _ in range(4):
        utime.sleep(0.5)
        tau_net, active_time = obtenir_psm_negociat()
        if tau_net is not None:
            proper = "%02d:%02d:%02d" % utime.localtime(
                utime.mktime(utime.localtime()) + tau_net
            )[3:6]
            break
        
    status = {
        "version": config.VERSIO,
        "bat": Power.getVbatt(),
        "tau_req": tau_demanat,
        "tau_net": tau_net,
        "proper": proper,
        "active_time": active_time,
        "net_time": net_time,
        "gnss_time": gnss_time,
        "mqtt_time": mqtt_time,
        "fix": posicio is not None,
        "rsrp": rsrp,
        "rsrq": rsrq
    }

    try:
        client.publish(
            config.TOPIC_STATUS,
            ujson.dumps(status),
            True
        )

        debug("Publicat status:", status)
        utime.sleep(2)

    except Exception as error:
        debug("Error publicant status:", error)

    wdt.feed()
    mqtt_escolta_activa = False
    client.disconnect()

    debug("A dormir")
    pm.autosleep(1)

    utime.sleep(120)


try:
    main()
except Exception as error:
    debug("Error fatal a main:", error)
    pm.autosleep(1)
    utime.sleep(120)