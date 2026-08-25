import utime, ujson, quecgnss, pm, checkNet, _thread, atcmd, app_fota
import ntptime, uos
import ubinascii, uhashlib
from misc import Power
from umqtt import MQTTClient
from machine import WDT
from usr import secrets, config

_thread.stack_size(16 * 1024)
wdt = WDT(config.TEMPS_WATCHDOG)

mqtt_escolta_activa = False

fitxers_ota_pendents = None
hashes_ota_pendents = None
ordre_rebuda = False

tracking_actiu = False
tracking_interval = config.TRACKING_INTERVAL_DEFECTE
tracking_max = config.TRACKING_MAX_DEFECTE
tracking_inici = None
lock_tracking = _thread.allocate_lock()


# ---------------------------------------------------------------------------
# utils
# ---------------------------------------------------------------------------

def temps_transcorregut(inici):
    return utime.time() - inici


def debug(*args):
    if config.DEBUG:
        print(*args)


def guardar_error(*args):
    try:
        text = " ".join(str(x) for x in args)

        with open(config.FITXER_LOG, "a") as f:
            f.write(text + "\n")

    except Exception:
        pass


def publicar_log(client):
    try:
        with open(config.FITXER_LOG, "r") as f:
            contingut = f.read()

        if not contingut:
            return

        client.publish(config.TOPIC_LOG, contingut)

        try:
            uos.remove(config.FITXER_LOG)
        except Exception:
            pass


    except Exception as error:
        debug("Error publicant log:", error)

# ---------------------------------------------------------------------------
# gnss
# ---------------------------------------------------------------------------

def convertir_coordenada(valor, hemisferi, graus):
    try:
        decimal = float(valor[:graus]) + float(valor[graus:]) / 60
    except (ValueError, IndexError):
        return None

    if hemisferi in ("S", "W"):
        decimal = -decimal

    return round(decimal, 6)


def obtenir_posicio():
    """Fa un fix GNSS complet: activa la ràdio en prioritat GNSS,
    llegeix trames NMEA fins trobar fix o esgotar TEMPS_MAXIM_FIX,
    i la retorna a prioritat LTE en acabar (amb fix o sense).
    Retorna (posicio, gnss_time), on posicio és None si no hi ha fix."""
    if quecgnss.init() != 0:
        debug("Error inicialitzant GNSS")
        guardar_error("GNSS: error inicialitzant")
        return None, 0

    quecgnss.setPriority(0)
    quecgnss.gnssEnable(1)

    debug("TEMPS_MAXIM_FIX:", config.TEMPS_MAXIM_FIX)
    inici = utime.time()
    posicio = None

    while temps_transcorregut(inici) < config.TEMPS_MAXIM_FIX:
        wdt.feed()

        try:
            resultat = quecgnss.read(4096)
        except Exception as error:
            guardar_error("GNSS: error lectura:", error)
            return None, temps_transcorregut(inici)
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
                posicio = (latitud, longitud, satel_lits)
                break

            if config.DEBUG:
                _debug_cn0(dades, temps_transcorregut(inici))

        utime.sleep(2)

    gnss_time = temps_transcorregut(inici)

    quecgnss.gnssEnable(0)
    quecgnss.setPriority(1)
    wdt.feed()

    debug("Posició obtinguda en", gnss_time, "segons:", posicio)

    return posicio, gnss_time


def _debug_cn0(dades, temps):
    print("Sense fix:", temps, "s", end=" ")
    cn0 = []

    for linia in dades.split("\r\n"):
        if "GSV" in linia:
            camps = linia.split(",")
            for i in range(4, len(camps) - 3, 4):
                try:
                    valor = int(camps[i + 3].split("*")[0])
                    if valor > 0:
                        cn0.append(valor)
                except Exception:
                    pass

    if cn0:
        print("Sat:", len(cn0), "C/N0 mitjà:", sum(cn0) // len(cn0), "dB-Hz")
    else:
        print("Sat: 0 C/N0 mitjà: 0")


# ---------------------------------------------------------------------------
# senyal / psm
# ---------------------------------------------------------------------------

def obtenir_senyal():
    try:
        r = bytearray(100)
        atcmd.sendSync("AT+QCSQ\r\n", r, "", 2)
        d = bytes(r).decode().split(":")[1].split(",")
        return int(d[2]), int(d[4])
    except Exception:
        return None, None


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


# ---------------------------------------------------------------------------
# mqtt
# ---------------------------------------------------------------------------

def connectar_mqtt(intents=3):
    """Connecta, subscriu (rep qualsevol ordre retained pendent) i llança
    el fil d'escolta. Reintenta amb backoff si falla."""
    global mqtt_escolta_activa

    inici = utime.time()
    ultim_error = None

    for intent in range(1, intents + 1):
        try:
            client = MQTTClient(
                config.DEVICE_ID,
                config.MQTT_HOST,
                port=config.MQTT_PORT,
                user=secrets.TOKEN_FLESPI_MQTT,
                password=secrets.TOKEN_FLESPI_MQTT,
                reconn=False
            )

            client.set_callback(processar_ordre)
            client.connect()
            client.subscribe(config.TOPIC_ORDRES, 0)

            mqtt_escolta_activa = True
            _thread.start_new_thread(escoltar_mqtt, (client,))

            mqtt_time = temps_transcorregut(inici)
            return client, mqtt_time

        except Exception as error:
            ultim_error = error
            debug("Error connectant MQTT (intent", intent, "/", intents, "):", error)

            if intent < intents:
                utime.sleep(min(2 ** intent, 10))
                wdt.feed()

    raise ultim_error


def desconnectar_mqtt(client):
    global mqtt_escolta_activa

    mqtt_escolta_activa = False

    try:
        client.disconnect()
    except Exception as error:
        debug("Error desconnectant MQTT:", error)
        guardar_error("MQTT: error desconnectant:", error)


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
            guardar_error("MQTT: error escolta:", error)

            if errors_consecutius >= max_errors:
                debug("escoltar_mqtt aturat")
                guardar_error("MQTT: escolta aturada")
                mqtt_escolta_activa = False
                break

            utime.sleep(1)

    debug("mqtt_escolta_activa:", mqtt_escolta_activa)


def publicar_posicio_segura(client, posicio):
    if not posicio:
        return

    try:
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

        debug("Publicada posició:", posicio)

    except Exception as error:
        debug("Error publicant posició:", error)
        guardar_error("MQTT: error publicant posicio:", error)


def processar_ordre(topic, missatge):
    global fitxers_ota_pendents
    global hashes_ota_pendents
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
            hashes_ota_pendents = ordre.get("hashes")
            ordre_rebuda = True

        elif cmd == "track_start":
            try:
                interval = int(ordre.get("interval", config.TRACKING_INTERVAL_DEFECTE))
            except (TypeError, ValueError):
                interval = config.TRACKING_INTERVAL_DEFECTE

            nou_interval = max(
                config.TRACKING_INTERVAL_MIN,
                min(interval, config.TRACKING_INTERVAL_MAX)
            )

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
        guardar_error("MQTT: error processant ordre:", error)



# ---------------------------------------------------------------------------
# ota
# ---------------------------------------------------------------------------

def verificar_hash(path, hash_esperat, intents=5):
    for intent in range(intents):
        try:
            h = uhashlib.sha256()
            with open(path, "rb") as f:
                while True:
                    bloc = f.read(512)
                    if not bloc:
                        break
                    h.update(bloc)
            return ubinascii.hexlify(h.digest()).decode() == hash_esperat

        except OSError as error:
            debug("Fitxer encara no llegible (intent", intent + 1, "/", intents, "):", error)
            utime.sleep(0.5)

        except Exception as error:
            debug("Error verificant hash:", error)
            return False

    debug("No s'ha pogut llegir el fitxer després de", intents, "intents")
    return False


def executar_ota(fitxers, hashes, client):
    ota = app_fota.new()

    for nom in fitxers:
        url = config.BASE_URL_OTA + nom
        path_final = "/usr/" + nom
        path_temp = "/usr/" + nom + ".tmp"
        wdt.feed()

        resultat = ota.download(url, path_temp)

        if resultat != 0:
            debug("Error descarregant:", nom)
            client.disconnect()
            return

        hash_esperat = hashes.get(nom) if hashes else None

        if hash_esperat and not verificar_hash(path_temp, hash_esperat):
            debug("Hash invàlid, OTA abortada:", nom)
            try:
                uos.remove(path_temp)
            except Exception:
                pass
            client.disconnect()
            return

        # Hash confirmat: ara sí, substituïm el fitxer real
        try:
            uos.remove(path_final)
        except Exception:
            pass

        uos.rename(path_temp, path_final)
        debug("OTA:", nom, "actualitzat i verificat")

    ota.set_update_flag()
    Power.powerRestart()


# ---------------------------------------------------------------------------
# tracking
# ---------------------------------------------------------------------------

def cicle_tracking(client):
    """Un cicle de tracking: espera l'interval (MQTT desconnectat, sense
    contenció de ràdio), fa un fix, reconnecta MQTT (rep ordres retained
    pendents com track_stop/ota) i publica. Retorna el client (nou) i
    si cal seguir fent tracking."""
    global tracking_actiu
    with lock_tracking:
        interval_actual = tracking_interval
        max_actual = tracking_max
        inici_actual = tracking_inici

    debug("Tracking actiu. Interval:", interval_actual)

    if temps_transcorregut(inici_actual) >= max_actual:
        debug("Final tracking: temps màxim")
        with lock_tracking:
            tracking_actiu = False
        return client, False

    desconnectar_mqtt(client)

    debug("Tracking: espero", interval_actual, "segons (MQTT desconnectat)")
    utime.sleep(interval_actual)

    with lock_tracking:
        actiu_actual = tracking_actiu
        max_actual = tracking_max
        inici_actual = tracking_inici

    if not actiu_actual:
        debug("Final tracking: track_stop mentre esperava")
        return client, False

    if temps_transcorregut(inici_actual) >= max_actual:
        debug("Final tracking: temps màxim")
        with lock_tracking:
            tracking_actiu = False
        return client, False

    posicio, gnss_time = obtenir_posicio()

    try:
        client, _ = connectar_mqtt()
    except Exception as error:
        debug("MQTT no disponible aquest cicle, continuo tracking:", error)
        return client, True

    if fitxers_ota_pendents:
        executar_ota(fitxers_ota_pendents, hashes_ota_pendents, client)
        return client, False

    publicar_posicio_segura(client, posicio)
    debug("Tracking GNSS:", gnss_time, "s")

    with lock_tracking:
        actiu_actual = tracking_actiu

    return client, actiu_actual


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    global tracking_actiu
    global tracking_inici
    global fitxers_ota_pendents

    if pm.get_psm_time()[0]:
        pm.set_psm_time(0)

    debug("Versió:", config.VERSIO)

    if config.DEBUG:
        resposta = bytearray(100)
        atcmd.sendSync('AT+QGPSCFG="xtra_info"\r\n', resposta, "", 5)
        text = bytes(resposta).decode("utf-8", "ignore").replace("\x00", "").strip()
        debug("XTRA info:", text)

    # region Fix GNSS abans de xarxa (ràdio compartida, no cal esperar LTE)
    posicio, gnss_time = obtenir_posicio()
    # endregion

    # region Xarxa
    inici = utime.time()
    stage, state = checkNet.waitNetworkReady(30)
    net_time = temps_transcorregut(inici)

    wdt.feed()

    if stage != 3 or state != 1:
        guardar_error("Xarxa: error connexio:", stage, state)
        pm.autosleep(1)
        utime.sleep(120)
        return

    try:
        ntptime.settime(2)
    except Exception as error:
        debug("Error NTP:", error)
        guardar_error("NTP: error:", error)

    # endregion

    # region Connectar MQTT i publicar primera posició
    try:
        client, mqtt_time = connectar_mqtt()
    except Exception as error:
        debug("Error connectant MQTT:", error)
        guardar_error("MQTT: error connexio:", error)

        pm.autosleep(1)
        utime.sleep(120)
        return

    utime.sleep(1)

    if fitxers_ota_pendents:
        executar_ota(fitxers_ota_pendents, hashes_ota_pendents, client)
        return

    publicar_posicio_segura(client, posicio)
    # endregion

    # region Tracking (si s'ha activat via ordre retained o rebuda ara)
    while tracking_actiu:
        client, tracking_actiu = cicle_tracking(client)

        if fitxers_ota_pendents:
            return
    # endregion

    with lock_tracking:
        tracking_inici = None

    # region Status final i PSM
    publicar_log(client)
    rsrp, rsrq = obtenir_senyal()
    tau_demanat = calcular_tau_a_demanar()

    unitat_tau, valor_tau = (
        (5, tau_demanat // 60)
        if tau_demanat < 3600
        else (1, tau_demanat // 3600)
    )

    pm.set_psm_time(unitat_tau, valor_tau, 0, config.ACTIVE_TIME // 2)

    proper = None
    tau_net = None
    active_time = None

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
        client.publish(config.TOPIC_STATUS, ujson.dumps(status), True)
        debug("Publicat status:", status)
        utime.sleep(2)
    except Exception as error:
        debug("Error publicant status:", error)
        guardar_error("MQTT: error publicant status:", error)
    # endregion

    wdt.feed()
    desconnectar_mqtt(client)

    debug("A dormir")
    pm.autosleep(1)
    utime.sleep(120)


try:
    main()
except Exception as error:
    debug("Error fatal a main:", error)
    guardar_error("Main: error fatal:", error)

    pm.autosleep(1)
    utime.sleep(120)