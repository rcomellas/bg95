""" Utilitats generals"""

import utime
import uos
from machine import WDT
from usr import config


watchdog = WDT(config.TEMPS_WATCHDOG)


def debug(*args):
    if config.DEBUG:
        print(*args)


def temps_transcorregut(inici):
    return utime.ticks_diff(utime.ticks_ms(), inici) // 1000


def log(missatge):
    t = utime.localtime()

    linia = "{:02d}/{:02d} {:02d}:{:02d}:{:02d} {}\n".format(
        t[2], t[1],
        t[3], t[4], t[5],
        str(missatge)
    )

    debug(linia)

    try:
        with open(config.FITXER_LOG, "a") as f:
            f.write(linia)
    except:
        pass


def llegir_log():
    try:
        with open(config.FITXER_LOG, "r") as f:
            return f.read()
    except:
        return None


def netejar_log():
    try:
        uos.remove(config.FITXER_LOG)
    except:
        pass
