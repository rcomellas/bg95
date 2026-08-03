# Requisits

## Maquinari

- Quectel BG95-M3, placa QuecPython de 40 pins.
- GNSS intern.
- Bateria Li-ion 1S.
- LTE-M.
- Acceleròmetre opcional en una fase posterior.

## Funcions del tracker

- Obtenir una posició GNSS.
- Llegir tensió de bateria.
- Llegir qualitat de cobertura.
- Publicar dades per MQTT.
- Llegir configuració MQTT retained.
- Canviar l'interval d'enviament.
- Guardar la configuració mínima.
- Entrar en PSM entre enviaments.
- Preparar una actualització OTA segura.

## Funcions del servidor

- Percentatge de bateria.
- Historial.
- Geofence.
- Validació i filtratge de posicions.
- Avisos.
- Distància, velocitat i estat del tracker.

## Payload inicial

```json
{"lat":42.047694,"lon":1.959975,"vb":3980,"sat":9,"rssi":-87,"int":3600,"seq":1}
```

## Topics

- Estat: `cabres/tracker01/state`
- Comandes: `cabres/tracker01/cmd`
