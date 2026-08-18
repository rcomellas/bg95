import utime
import pm
import atcmd
import quecgnss

from usr import config
from usr.utils import debug

tau_demanat = None
tau_net = None
active_time = None


def despertar():
    pm.autosleep(0)

    # if pm.get_psm_time()[0]:
    #     pm.set_psm_time(0)


def calcular_tau():
    hora = utime.localtime()[3]

    hora_futura = (
        hora + config.TAU_LLARG // 3600
    ) % 24

    return (config.TAU_LLARG if config.HORA_INICI_NIT <= hora_futura < config.HORA_FINAL_NIT else config.TAU_CURT)


def preparar_psm():
    global tau_demanat
    global tau_net
    global active_time

    tau_demanat = config.TAU_CURT
    # tau_demanat = calcular_tau()

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

    utime.sleep(2)

    tau_net, active_time = obtenir_psm_negociat()


def obtenir_psm_negociat():
    resposta = bytearray(100)

    ret = atcmd.sendSync(
        "AT+QPSMS?\r\n",
        resposta,
        "",
        2
    )

    if ret != 0:
        return None, None

    text = bytes(resposta).decode(
        "utf-8", "ignore"
    )

    valors = text.split('"')

    try:
        return int(valors[1]), int(valors[3])

    except Exception:
        return None, None


def dormir():
    quecgnss.gnssEnable(0)

    resposta = bytearray(100)

    atcmd.sendSync(
        "AT+QIDEACT=1\r\n",
        resposta,
        "",
        10
    )
    debug("A dormir...")
    pm.autosleep(1)

    utime.sleep(120)
