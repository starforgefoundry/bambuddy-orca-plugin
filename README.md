# Bambuddy for OrcaSlicer

OrcaSlicer 2.5 plugin that imports the printer models on a Bambuddy instance as printer profiles and sends prints to the Bambuddy queue.

Browser sign-in needs Bambuddy 1.2.5.7.9 or later (device sign-in at `/connect`). Older instances sign in with an API key instead.

## Build

```sh
mise run build   # dist/Bambuddy-<version>-py3-none-any.whl
mise run test
```

## Use

1. OrcaSlicer → Plugins → Install local → pick the wheel, then enable it.
2. Run **Connect to Bambuddy**, enter the instance URL, and sign in on the instance's own login page (password or SSO). If the instance has no `/connect`, paste an API key from Settings → API Keys.
3. Restart OrcaSlicer. The printer list now has one `Bambuddy - <model> <nozzle> nozzle` profile per printer model and nozzle size on the instance.
4. Slice, then Print or Send. After OrcaSlicer's dialog, the Bambuddy window lets you rename the print (the plate suffix is kept), pick any printer of that model or a specific printer, a printer group, the filament mapping, and whether to start now or wait in the queue.

Dual-nozzle models (H2D, H2D Pro, H2C, X2D) are skipped for now.
