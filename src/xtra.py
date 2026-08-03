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
        print("Resposta XTRA no reconeguda:", text)
        return None


def descarregar():
    print("Descarregant XTRA...")

    ret, text = enviar_at(
        'AT+QGPSCFG="xtra_download",1',
        30
    )

    if ret != 0:
        print("Error iniciant descàrrega XTRA:", text)
        return False

    for _ in range(15):
        time.sleep(2)

        hores = obtenir_hores_restants()

        if hores is not None:
            print("XTRA descarregat:", hores, "hores restants")
            return True

    print("No s'ha pogut confirmar la descàrrega XTRA")
    return False


def actualitzar_si_cal():
    hores = obtenir_hores_restants()

    if hores is None:
        print("No hi ha dades XTRA vàlides")
        return descarregar()

    print("XTRA:", hores, "hores restants")

    if hores <= HORES_MINIMES:
        return descarregar()

    return True
