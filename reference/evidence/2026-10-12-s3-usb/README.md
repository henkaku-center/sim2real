# S3 USB firmware installation — October 12, 2026

Instructor confirmed battery physically unplugged and requested retaining all
servo connections. No external supply was required. Device on Artemis:
`303a:1001`, `/dev/ttyACM0`, by-id suffix `D4:05:92:47:C8:B0`.

## Backup and upload

- Firmware source: `71af7e0bb6941928b32f51c0dc2262dcd8284774`.
- Full 4,194,304-byte pre-flash backup succeeded with esptool 5.3.1 **ROM reader**
  (`--no-stub`). Default stub reads repeatedly stopped near address `0x6b000`,
  including a smaller overlapping read. A ROM read of that region succeeded;
  the full ROM read then completed in 128.3 seconds. Cause of the stub-path
  failure remains undiagnosed; it is not proof of a bad flash region or USB power.
- Backup SHA-256: `dc1b715e72414a4216807fa09f5391c1313b659817dc15dcfbaf4ad9c37f332e`.
  Raw backups stay private on Artemis and the instructor's Mac, not in git.
- Application binary SHA-256:
  `5d5c66f935efa68db848125e001d9a7b8c1d86d761e43a1a7b6367ed0d8209f3`.
- Every staged binary matched the clean macOS build report before upload.
- Arduino CLI 1.5.1, ESP32 core 3.3.11; complete upload recipe with native USB CDC,
  4 MB/default partition, PSRAM disabled and `EraseFlash=none`.
- Upload wrote the application at `0x10000`, 1,021,424 image bytes; the tool
  reported successful data-hash verification and reset. The complete recipe also
  supplies the matching bootloader/partitions/boot-app image; NVS was not erased.

## Observed after reboot

`status`, `show` and `bench` replied successfully; see `identity-status.log`.
Profile `tim-pca9685-150-512-v1`, manifest `bd7675604b98ae46`, outputs off,
hub ready, fault clear, all mappings -1/unverified, limits 85–95 degrees.

This establishes USB upload, serial command replies and the controller's reported
hub/outputs state. It does not establish observed OLED appearance, physical horn
motion, channel identity, measured oscillator frequency, OE wiring, power capacity
under motion or Wi-Fi performance. No arming or movement command was sent.
