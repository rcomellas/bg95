import time
import atcmd


HORES_MINIMES = 12


def enviar_at(comanda, espera=10):
    resposta = bytearray(300)

    ret = atcmd.sendSync(
        comanda + "\r\n",
        resposta,
        "",
        espera
    )

    text = bytes(resposta).decode("utf-8", "ignore")

    return ret, text


def obtenir_hores_restants():
    ret, text = enviar_at(
        'AT+QGPSCFG="xtra_info"',
        5
    )

    if ret != 0:
        return None

    try:
        inici = text.find('"xtra_info",')

        if inici == -1:
            return None

        fragment = text[inici:].split(",")

        return int(fragment[1])

    except Exception:
        return None


def descarregar():
    ret, text = enviar_at(
        'AT+QGPSCFG="xtra_download",1',
        30
    )

    if ret != 0:
        return False

    for _ in range(15):
        time.sleep(2)

        hores = obtenir_hores_restants()

        if hores is not None:
            return True

    return False


def actualitzar_si_cal():
    hores = obtenir_hores_restants()

    if hores is None:
        return descarregar()

    if hores <= HORES_MINIMES:
        return descarregar()

    return True
