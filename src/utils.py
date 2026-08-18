import utime
from usr import config
from machine import WDT

watchdog = WDT(120)


def debug(*args):
    if config.DEBUG:
        print(*args)


def temps_transcorregut(inici):
    return utime.ticks_diff(utime.ticks_ms(), inici) // 1000
