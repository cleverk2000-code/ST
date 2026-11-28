## 0.1.7
- Persist the last validated hub/channel UUID pair in the add-on data directory; prefill it after restart and update.
- Save only after successful inventory/plan validation; rejected target changes retain the previous pair. No personal IDs or PAT in source.
- Add persistence, restart-prefill and target-change regression tests.

## 0.1.6
- Add opt-in `zcl-controls` package selection for original wonjj6768 ZCL Controls remotes and multi-component buttons. Keep the existing seven packages selected by default.
- Use the existing pinned upstream builder and MQTT button-event bridge; first installation requires explicit new-package approval and manual compatible driver selection in SmartThings.
- Add inventory and UI selection regression tests. Physical hub and MQTT button-event verification still required.

## 0.1.5
- Add manual Radar query all DP button for the two HOBEIAN TS0601 fingerprints in ef00-presence-general-2. Send one EF00 0x03 read request, with per-device 30-second cooldown; no polling.
- Accumulate observed DP values and last query/report timestamps in Radar DP report attributes. No unverified distance inference.
- Scope additional code to the presence package to preserve Samsung package size limits for unrelated drivers.
- Physical query response and measured-distance availability remain unverified.

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
