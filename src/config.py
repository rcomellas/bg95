"""Configuració persistent del tracker."""

MQTT_HOST = "mqtt.flespi.io"
MQTT_PORT = 1883

TOPIC_POSICIO = "bg95/location"
TOPIC_STATUS = "bg95/status"
# TOPIC_DISCOVERY = "homeassistant/device_tracker/bg95/config"

DEVICE_ID = "BG95"
INTERVAL_SEGONS = 60
TEMPS_MAXIM_FIX = 120
