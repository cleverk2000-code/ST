## 0.1.4
- Add read-only EF00 radar DP diagnostics for TS0601 / _TZE200_rhgsbacq and _TZE200_y8jijhba in the supported Edge driver.
- Publish the latest received DP report in HA MQTT Discovery and Edge logs, marking undocumented DP IDs. No estimated distance, additional Zigbee polling or SmartThings capability changes.
- Pin the add-on driver builder to the tested radar diagnostics merge revision. Physical hub validation remains required.

## 0.1.3
- Poll active power every 10 seconds for the TS011F / _TZ3000_5f43h46b variant on the official Zigbee switch driver, without changing relay state.
- Accept lux/LUX illuminance units and expand sensor zero-value and polling regression coverage.

## 0.1.2
- Forward capability reports immediately through the SmartThings device extension API.

## 0.1.1
- Discover SmartThings child switches as individual MQTT devices and retry interrupted discovery.

## 0.1.0
- Ingress web UI; temporary PAT authentication
- Existing seven driver inventory, dry run, and identity-checked deployment
- Optional per-build common MQTT settings with explicit consent
