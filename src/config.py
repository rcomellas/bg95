"""Configuració persistent del tracker."""

VERSIO = "1.0.4"

DEBUG = True

MQTT_HOST = "mqtt.flespi.io"
MQTT_PORT = 1883

TOPIC_POSICIO = "bg95/location"
TOPIC_STATUS = "bg95/status"
# TOPIC_DISCOVERY = "homeassistant/device_tracker/bg95/config"

DEVICE_ID = "BG95"

INTERVAL_SEGONS = 60
TEMPS_MAXIM_FIX = 120

TAU_CURT = 1800
TAU_LLARG = 10800
HORA_INICI_NIT = 0
HORA_FINAL_NIT = 7
ACTIVE_TIME = 6

TRACKING_INTERVAL_DEFECTE = 30
TRACKING_INTERVAL_MAX = 120
TRACKING_MAX_DEFECTE = 600

BASE_URL_OTA = "https://raw.githubusercontent.com/rcomellas/bg95/main/src/ota/"
