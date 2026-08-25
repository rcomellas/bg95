""" Configuració del tracker """

DEVICE_ID = "BG95"
VERSIO = "1.0.18"

DEBUG = True

# XARXA
TEMPS_INTENT_XARXA = 12
TEMPS_REINTENT_XARXA = 30

# MQTT
MQTT_HOST = "mqtt.flespi.io"
MQTT_PORT = 1883

TOPIC_POSICIO = b"bg95/location"
TOPIC_STATUS = b"bg95/status"
TOPIC_ORDRES = b"bg95/command"
# TOPIC_DISCOVERY = b"homeassistant/device_tracker/bg95/config"

# GNSS
TEMPS_MAXIM_FIX = 10  # segons

# PSM
TAU_CURT = 180  # en segons
TAU_LLARG = 5000  # en segons
ACTIVE_TIME = 10  # en segons
HORA_INICI_TAU_LLARG = 0
HORA_FINAL_TAU_LLARG = 7

# Tracking
TRACKING_INTERVAL_DEFECTE = 30  # en segons
TRACKING_INTERVAL_MAX = 120  # en segons
TRACKING_MAX_DEFECTE = 600  # en segons

# OTA
BASE_URL_OTA = "https://raw.githubusercontent.com/rcomellas/bg95/main/src/"

# LOG ERRORS
FITXER_LOG = "/usr/bg95.error.log"
TOPIC_LOG = b"bg95/log"

# ALTRES
TEMPS_WATCHDOG = 120