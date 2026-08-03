# BG95-M3 GPS Tracker

Tracker GPS de baix consum basat en Quectel BG95-M3 i QuecPython.

## Objectius

- Enviar coordenades per LTE-M i MQTT.
- Enviar tensió de bateria.
- Interval d'enviament configurable remotament.
- Consum mínim mitjançant PSM.
- Integració amb Home Assistant.
- Actualització OTA en una fase posterior.

## Estructura

- `src/`: codi QuecPython del tracker.
- `server/`: MQTT Discovery, payloads de prova i OTA.
- `docs/`: documentació del projecte.
