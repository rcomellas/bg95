import time
import atcmd


HORES_MINIMES = 12


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

    for _ in range(5):
        time.sleep(2)

        hores = obtenir_hores_restants()

        if hores is not None:
            return True

    return False


def actualitzar_si_cal():
    """
    Retorna:
        "ok"          -> ja tenia dades XTRA vàlides, no calia descarregar
        "descarregat" -> s'ha fet una descàrrega nova (cal marge abans del GNSS)
        "error"       -> ha fallat la descàrrega
    """
    hores = obtenir_hores_restants()

    if hores is None or hores <= HORES_MINIMES:
        if descarregar():
            return "descarregat"
        else:
            return "error"

    return "ok"
