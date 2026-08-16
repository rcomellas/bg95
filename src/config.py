"""Configuració del tracker."""

DEVICE_ID = "BG95"
VERSIO = "1.0.5"

DEBUG = True

# MQTT
MQTT_HOST = "mqtt.flespi.io"
MQTT_PORT = 1883

TOPIC_POSICIO = b"bg95/location"
TOPIC_STATUS = b"bg95/status"
TOPIC_ORDRES = b"bg95/command"
# TOPIC_DISCOVERY = b"homeassistant/device_tracker/bg95/config"

# GNSS
TEMPS_MAXIM_FIX = 15  # segons

# PSM
TAU_CURT = 1800  # en segons
TAU_LLARG = 10800  # en segons
ACTIVE_TIME = 0  # en segons
HORA_INICI_NIT = 0
HORA_FINAL_NIT = 7

# Tracking
TRACKING_INTERVAL_DEFECTE = 30  # en segons
TRACKING_INTERVAL_MAX = 120  # en segons
TRACKING_MAX_DEFECTE = 600  # en segons

# OTA
BASE_URL_OTA = "https://raw.githubusercontent.com/rcomellas/bg95/main/src/ota/"
