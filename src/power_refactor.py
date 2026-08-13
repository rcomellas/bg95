import utime
import pm
import atcmd

TAU_CURT = 1800
TAU_LLARG = 10800
HORA_INICI_NIT = 0
HORA_FINAL_NIT = 7
ACTIVE_TIME = 6
DEBUG = True


def debug(*args):
    if DEBUG:
        print(*args)


def tau_a_demanar():
    hora = utime.localtime()[3]
    hora_futura = (hora + TAU_LLARG // 3600) % 24

    debug("HORA RTC:", hora, "HORA FUTURA:", hora_futura)

    return (
        TAU_LLARG
        if HORA_INICI_NIT <= hora_futura < HORA_FINAL_NIT
        else TAU_CURT
    )


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

    text = bytes(resposta).decode("utf-8", "ignore")
    valors = text.split('"')

    try:
        return int(valors[1]), int(valors[3])

    except Exception:
        return None, None




def preparar_despertar():
    pm.autosleep(0)

    if pm.get_psm_time()[0]:
        pm.set_psm_time(0)


def preparar_psm():
    tau_demanat = tau_a_demanar()

    unitat_tau, valor_tau = (
        (5, tau_demanat // 60)
        if tau_demanat < 3600
        else (1, tau_demanat // 3600)
    )

    pm.set_psm_time(
        unitat_tau,
        valor_tau,
        0,
        ACTIVE_TIME // 2
    )

    utime.sleep(2)

    tau_net, active_time = obtenir_psm_negociat()

    return tau_demanat, tau_net, active_time


def dormir_sense_mqtt():
    pm.autosleep(1)
    utime.sleep(120)


def entrar_psm(client):
    client.disconnect()
    pm.autosleep(1)
    utime.sleep(120)
