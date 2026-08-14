import utime
from usr import config


def debug(*args):
    if config.DEBUG:
        print(*args)


def temps_transcorregut(inici):
    return utime.ticks_diff(utime.ticks_ms(), inici) // 1000
