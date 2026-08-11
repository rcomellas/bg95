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

    text = bytes(resposta).decode(
        "utf-8",
        "ignore"
    ).replace("\x00", "")

    return ret, text


def obtenir_hores_restants():
    ret, text = enviar_at(
        'AT+QGPSCFG="xtra_info"',
        5
    )

    if ret != 0:
        print("XTRA info error. ret:", ret)
        return None

    try:
        inici = text.find('"xtra_info",')

        if inici == -1:
            print("XTRA info no trobada:", text)
            return None

        fragment = text[inici:].split(",")

        hores = int(fragment[1])

        print("XTRA hores restants:", hores)

        return hores

    except Exception as error:
        print("Error llegint XTRA info:", error)
        print("Resposta:", text)
        return None


def descarregar():
    print("Iniciant descàrrega XTRA...")

    ret, text = enviar_at(
        'AT+QGPSCFG="xtra_download",1',
        30
    )

    print("XTRA download ret:", ret)
    print("XTRA download resposta:", text)

    if ret != 0:
        print("Error iniciant descàrrega XTRA")
        return False

    for i in range(15):
        time.sleep(2)

        hores = obtenir_hores_restants()

        print(
            "XTRA comprovació",
            i + 1,
            "- hores:",
            hores
        )

        if hores is not None and hores > HORES_MINIMES:
            print("Descàrrega XTRA correcta")
            return True

    print("Timeout esperant descàrrega XTRA")

    return False


def actualitzar_si_cal():
    hores = obtenir_hores_restants()

    if hores is None:
        print("XTRA no disponible. Intentant descarregar...")

        if descarregar():
            return "descarregat"

        return "error"

    if hores <= HORES_MINIMES:
        print(
            "XTRA caduca aviat:",
            hores,
            "hores. Descarregant..."
        )

        if descarregar():
            return "descarregat"

        return "error"

    print(
        "XTRA correcta. Queden",
        hores,
        "hores"
    )

    return "ok"
