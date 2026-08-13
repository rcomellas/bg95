import utime
import quecgnss
import atcmd

from usr import config

DEBUG = True


def debug(*args):
    if DEBUG:
        print(*args)


def convertir_coordenada(valor, hemisferi, graus):
    decimal = float(valor[:graus]) + float(valor[graus:]) / 60

    if hemisferi == "S" or hemisferi == "W":
        decimal = -decimal

    return round(decimal, 6)


def mostrar_info_xtra():
    if not DEBUG:
        return

    resposta = bytearray(100)

    atcmd.sendSync(
        'AT+QGPSCFG="xtra_info"\r\n',
        resposta,
        "",
        5
    )

    text = bytes(resposta).decode(
        "utf-8", "ignore"
    ).replace("\x00", "").strip()

    debug("XTRA info:", text)


def obtenir_posicio():
    debug("TEMPS_MAXIM_FIX:", config.TEMPS_MAXIM_FIX)

    inici = utime.ticks_ms()

    while utime.ticks_diff(
        utime.ticks_ms(),
        inici
    ) < config.TEMPS_MAXIM_FIX * 1000:

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

            if DEBUG:
                print(
                    "Sense fix GNSS:",
                    utime.ticks_diff(utime.ticks_ms(), inici) // 1000,
                    "segons",
                    end=" "
                )

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
                        "C/N0 mitjà:",
                        sum(cn0) // len(cn0),
                        "dB-Hz"
                    )
                else:
                    print("Sat: 0 C/N0 mitjà: 0")

        utime.sleep(2)

    return None


def obtenir_fix():
    mostrar_info_xtra()

    quecgnss.gnssEnable(0)
    quecgnss.setPriority(0)

    if quecgnss.init() != 0:
        return None, 0

    quecgnss.gnssEnable(1)

    inici = utime.ticks_ms()

    posicio = obtenir_posicio()

    gnss_time = utime.ticks_diff(
        utime.ticks_ms(),
        inici
    ) // 1000

    debug(
        "Posició obtinguda en",
        gnss_time,
        "segons:",
        posicio
    )

    return posicio, gnss_time


def apagar():
    quecgnss.gnssEnable(0)
