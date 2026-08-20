""" Gestió del PSM (mode de baix consum) """

import utime, pm, atcmd, quecgnss
from misc import Power

from usr import config
from usr.utils import debug, log

tau_demanat = None
tau_net = None
active_time = None


def despertar():
    pm.autosleep(0)
    motiu_despertar = Power.powerOnReason()

    if motiu_despertar == 5:
        log("WDT o error d'encesa: reinici")
    elif motiu_despertar == 9:
        log("DUMP: reinici anormal")
    # if pm.get_psm_time()[0]:
    #     pm.set_psm_time(0)
    debug("Versió:", config.VERSIO)

def calcular_tau():
    hora = utime.localtime()[3]

    hora_futura = (
        hora + config.TAU_LLARG // 3600
    ) % 24

    return (config.TAU_LLARG if config.HORA_INICI_NIT <= hora_futura < config.HORA_FINAL_NIT else config.TAU_CURT)


def preparar_psm():
    global tau_demanat, tau_net, active_time

    tau_demanat = config.TAU_CURT
    # tau_demanat = calcular_tau()
    
    if tau_demanat < 3600:
        unitat_tau = 5
        valor_tau = tau_demanat // 60
    else:
        unitat_tau = 1
        valor_tau = tau_demanat // 3600

    pm.set_psm_time(
        unitat_tau,
        valor_tau,
        0,
        config.ACTIVE_TIME // 2
    )

    tau_net, active_time = obtenir_psm_negociat()


def obtenir_psm_negociat():
    resposta = bytearray(100)

    if atcmd.sendSync("AT+QPSMS?\r\n", resposta, "", 2) != 0:
        return None, None

    try:
        valors = bytes(resposta).decode("utf-8", "ignore").split('"')
        return int(valors[1]), int(valors[3])
    except Exception:
        return None, None

    
def dormir():
    quecgnss.gnssEnable(0)

    # resposta = bytearray(100)

    # atcmd.sendSync(
    #     "AT+QIDEACT=1\r\n",
    #     resposta,
    #     "",
    #     10
    # )
    debug("A dormir...")
    pm.autosleep(1)

    utime.sleep(120)
