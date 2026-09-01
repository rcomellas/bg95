""" Configuració del tracker """

# DEVICE_ID = "BG95"
VERSIO = "1.0.20"

DEBUG = True

# XARXA
TEMPS_INTENT_XARXA = 12
TEMPS_REINTENT_XARXA = 30

# MQTT
MQTT_HOST = "mqtt.flespi.io"
MQTT_PORT = 1883

TOPIC_POSICIO = b"/location"
TOPIC_STATUS = b"/status"
TOPIC_ORDRES = b"/command"
TOPIC_LOG = b"/log_errors"
# TOPIC_DISCOVERY = b"homeassistant/device_tracker/bg95/config"

# GNSS
TEMPS_MAXIM_FIX = 100  # segons

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