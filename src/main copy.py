import time
import quecgnss
import atcmd
from misc import Power

from usr import xtra


TEMPS_MAXIM_FIX = 120

PROVES_SENSE_XTRA = 0
PROVES_AMB_XTRA = 10

ANTENA = "original"

ARXIU_ESTAT = "/usr/test_antena_estat.txt"
ARXIU_RESULTATS = "/usr/test_antena.csv"


def enviar_at(comanda, espera=5):
    resposta = bytearray(300)

    ret = atcmd.sendSync(
        comanda + "\r\n",
        resposta,
        "",
        espera
    )

    text = bytes(resposta).decode("utf-8", "ignore")

    return ret, text


def carregar_estat():
    try:
        with open(ARXIU_ESTAT, "r") as f:
            dades = f.read().strip().split(",")

        antena = dades[0]
        prova = int(dades[1])
        xtra_preparat = dades[2]

        if antena != ANTENA:
            return 0, ""

        return prova, xtra_preparat

    except:
        return 0, ""


def desar_estat(prova, xtra_preparat):
    with open(ARXIU_ESTAT, "w") as f:
        f.write(
            "{},{},{}".format(
                ANTENA,
                prova,
                xtra_preparat
            )
        )


def guardar_resultat(prova, mode, temps_fix, sat, error=""):
    try:
        with open(ARXIU_RESULTATS, "r"):
            existeix = True
    except:
        existeix = False

    with open(ARXIU_RESULTATS, "a") as f:

        if not existeix:
            f.write(
                "antena,prova,mode,temps_fix,sat,error\n"
            )

        f.write(
            "{},{},{},{},{},{}\n".format(
                ANTENA,
                prova,
                mode,
                temps_fix,
                sat,
                error
            )
        )


def obtenir_fix_i_sats(dades):
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
        sat = int(gga[7]) if gga and gga[7] else 0
        return True, sat

    return False, 0


# ==================================================
# INICI
# ==================================================

time.sleep(5)

prova, xtra_preparat = carregar_estat()

total = PROVES_SENSE_XTRA + PROVES_AMB_XTRA


if prova >= total:
    print()
    print("===== TEST ACABAT =====")
    print("Antena:", ANTENA)
    print("Resultats:", ARXIU_RESULTATS)

    while True:
        time.sleep(60)


if prova < PROVES_SENSE_XTRA:
    mode = "sense_xtra"
else:
    mode = "amb_xtra"


print()
print("===== TEST ANTENA GPS =====")
print("Antena:", ANTENA)
print("Prova:", prova + 1, "/", total)
print("Mode:", mode)


# ==================================================
# PREPARAR XTRA
# ==================================================

if xtra_preparat != mode:

    if mode == "sense_xtra":

        print("Desactivant XTRA...")

        ret, text = enviar_at("AT+QGPSXTRA=0")

        print("QGPSXTRA=0:", ret)
        print(text)

    else:

        print("Activant XTRA...")

        ret, text = enviar_at("AT+QGPSXTRA=1")

        print("QGPSXTRA=1:", ret)
        print(text)

    desar_estat(prova, mode)

    print("Reiniciant per aplicar configuració XTRA...")

    time.sleep(3)

    Power.powerRestart()


# ==================================================
# SEQÜÈNCIA GNSS IGUAL QUE MAIN.PY
# ==================================================

quecgnss.gnssEnable(0)


if mode == "amb_xtra":

    ret, text = enviar_at("AT+QGPSXTRA?")

    print("QGPSXTRA?:", ret)
    print(text)

    estat_xtra = xtra.actualitzar_si_cal()

    print("XTRA:", estat_xtra)

    hores = xtra.obtenir_hores_restants()

    print("XTRA hores:", hores)


quecgnss.setPriority(0)


error_init = None

if quecgnss.init() != 0:

    error_init = "error_init_gnss"

    print("ERROR inicialitzant GNSS")


if error_init:

    guardar_resultat(
        prova + 1,
        mode,
        0,
        0,
        error_init
    )

    desar_estat(
        prova + 1,
        mode
    )

    print("Resultat desat amb error")
    print("Reiniciant...")

    time.sleep(3)

    Power.powerRestart()


# ==================================================
# FER FIX
# ==================================================

inici = time.ticks_ms()

fix = False
sat = 0
error_lectura = ""

ultim_avis = -5


while time.ticks_diff(
    time.ticks_ms(),
    inici
) < TEMPS_MAXIM_FIX * 1000:

    try:

        resultat = quecgnss.read(4096)

        if resultat != -1 and resultat[0] > 0:

            fix, sat = obtenir_fix_i_sats(
                resultat[1]
            )

            if fix:
                break

    except Exception as e:

        error_lectura = "error_lectura:{}".format(e)

        print(
            "Error llegint GNSS:",
            e
        )

    transcorregut = time.ticks_diff(
        time.ticks_ms(),
        inici
    ) // 1000

    if transcorregut >= ultim_avis + 5:

        print(
            "Buscant fix...",
            transcorregut,
            "s"
        )

        ultim_avis = transcorregut

    time.sleep(2)


# ==================================================
# RESULTAT
# ==================================================

if fix:

    temps_fix = time.ticks_diff(
        time.ticks_ms(),
        inici
    ) // 1000

    print("FIX:", temps_fix, "s")
    print("SAT:", sat)

else:

    temps_fix = TEMPS_MAXIM_FIX

    print(
        "SENSE FIX després de",
        TEMPS_MAXIM_FIX,
        "s"
    )


quecgnss.gnssEnable(0)


guardar_resultat(
    prova + 1,
    mode,
    temps_fix,
    sat,
    error_lectura
)


desar_estat(
    prova + 1,
    mode
)


print("Resultat desat")
print("Reiniciant...")

time.sleep(3)

Power.powerRestart()
