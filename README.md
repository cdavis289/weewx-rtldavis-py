# Davis RTL-SDR

Receive Davis Vantage Pro, Pro2 and Vue observations with an RTL-SDR USB dongle.
The driver supports EU, US and NZ frequency plans, separate wind transmitters,
and leaf/soil and temperature/humidity stations. The receiver runs inside WeeWX
and finds the dongle's frequency error by itself.

The maintained Python fork has a published production driver release,
[`v0.23.0-prod.1`](https://github.com/cdavis289/weewx-rtldavis-py/releases/tag/v0.23.0-prod.1).
The corresponding [WeeWX Docker RTL-Davis image](https://github.com/cdavis289/weewx-docker/pkgs/container/weewx-rtldavis)
bundles this driver and its native dependencies. The Docker repository publishes
[`v5.6.0`](https://github.com/cdavis289/weewx-docker/releases/tag/v5.6.0)
with WeeWX 5.6.0; the previous WeeWX 5.5.2-r3 image remains a separate release.

This is an independent continuation of
[lheijst/weewx-rtldavis](https://github.com/lheijst/weewx-rtldavis), with the
Go receiver of [lheijst/rtldavis](https://github.com/lheijst/rtldavis) ported to
Python. Report problems in [this issue tracker](https://github.com/weewx-packages/weewx-rtldavis/issues).

## Requirements

- Linux, a Davis wireless station and an RTL-SDR dongle.
- numpy and librtlsdr. On Debian, Ubuntu or Raspberry Pi OS with WeeWX
  installed from its package:

  ```sh
  sudo apt install python3-numpy rtl-sdr
  ```

  With a pip installation of WeeWX, install numpy into its virtual environment
  instead, for example `~/weewx-venv/bin/pip install numpy`, and librtlsdr with
  `sudo apt install rtl-sdr`.

`rtl-sdr` pulls in the librtlsdr package of the distribution, `librtlsdr0` or
`librtlsdr2` on Ubuntu 24.04, and adds tools such as `rtl_test`. The library
package brings the udev rule that gives the `plugdev` group access to the
dongle. The DVB-T kernel driver needs no blacklist; librtlsdr releases the
dongle from it.

## Installation

Install `rtldavis` from the [WeeWX packages catalog](https://github.com/weewx-packages/catalog/blob/main/packages/rtldavis.md).
The catalog page lists the current release, its WeeWX and Python
requirements, and the install, update and removal commands.

For fork-specific changes, build the extension from the desired fork
revision with `python tools/package.py`. The upstream catalog release
does not include these fork-specific changes.

Then select the driver. It asks for the frequency band, the ISS channel and
the rain bucket:

```sh
weectl station reconfigure --driver=user.rtldavis
```

Let the WeeWX service user open the dongle, then restart WeeWX. For a package
installation the user is `weewx`; for a pip installation it is the user that
runs WeeWX:

```sh
sudo usermod -aG plugdev weewx
sudo systemctl restart weewx
```

Plug in the dongle. The log shows the frequency search, the frequency error
found and each transmitter once it is received:

```sh
journalctl -u weewx -f
```

## Using the maintained Docker image

For a Docker-based receiver, use
[`ghcr.io/cdavis289/weewx-rtldavis:5.6.0`](https://github.com/cdavis289/weewx-docker/pkgs/container/weewx-rtldavis)
instead of installing the catalog package into the container. This image
vendors the pinned fork version `v0.23.0-prod.1`, NumPy and RTL-SDR
dependencies, and selected MQTT and Belchertown integrations.

```yaml
services:
  weewx:
    image: ghcr.io/cdavis289/weewx-rtldavis:5.6.0
    restart: unless-stopped
    stop_grace_period: 90s
    devices:
      - /dev/bus/usb:/dev/bus/usb
    volumes:
      - ./data:/data
```

Create and configure `data/weewx.conf`, including the `[Rtldavis]`
section, for your actual station and USB dongle. Set `device` to the
dongle's serial number when multiple SDR receivers are attached. USB access,
MQTT settings, report configuration and any host volume permissions remain
the operator's responsibility. Back up `data/weewx.conf` and the archive
database before changing image versions. A Docker image release and a
standalone driver release are distinct version numbers; they should not be
confused.

See [Docker deployment and production maintenance](https://github.com/cdavis289/weewx-docker/blob/develop/docs/rtldavis-production.md)
for image validation details. The standard WeeWX package installation
instructions above remain applicable to non-Docker installations.

## Configuration

`weectl station reconfigure` writes the `[Rtldavis]` section:

```ini
[Rtldavis]
    driver = user.rtldavis
    transceiver_frequency = EU
    iss_channel = 1
    rain_bucket_type = 1
```

Bucket type `1` means 0.2 mm per tip, `0` means 0.01 inch. Additional
transmitters, the dongle, its gain and the sensor map are optional.
The [configuration reference](docs/configuration.md) lists every option with
its default and the observations. [Troubleshooting](docs/troubleshooting.md)
explains the log messages and how to test reception without WeeWX.

## Optional diagnostics and development history

Optional gust, frame, RF, wind-validation and synchronization diagnostics
are disabled by default. Evidence captures use bounded memory and are
written on anomalies, not as continuous raw SDR IQ recordings. Completed
captures have individual file-count limits and a combined 50 MiB default
retention budget, enforced at startup, after writes and periodically.

See the [configuration reference](docs/configuration.md) and
[development history](docs/development-history.md). The historical
[dongle A/B crossover procedure](docs/ab-crossover-test.md) documents
controlled testing; the comparison recorder has been removed.
Use writable, persistent capture directories.

## Limitations

- Tests cover recorded problem frames and simulated transmitters with
  frequency errors. The librtlsdr binding and the installation into WeeWX were
  checked against a stand-in library that plays recorded samples. This fork has also undergone controlled live US-band RF testing with a
  Davis Vantage Pro2. Phase C2 completed approximately six days without
  synchronization loss. The Python receiver subsequently passed production integration tests and
  was deployed with WeeWX 5.5.2 on November 25, 2026. Live receiver
  synchronization, MQTT publishing and new five-minute archive records were
  observed after deployment. This is a validation of the tested US-band Davis
  Vantage Pro2 setup, not a guarantee of reliability on other hardware or
  frequency plans.
- The first observations can take a while. Each of the five steps of the
  frequency search lasts 18 seconds in the EU band and 136 seconds in the US
  and NZ bands for an ISS on channel 1, up to 21 and 159 seconds on channel 8.
- In the EU band, a dongle reading more than about 90 kHz (100 ppm) low is
  taken for the next channel. Reception then works for four of five channels.
  Set `ppm` to the dongle's error to avoid this.
- librtlsdr 0.6.0 in Debian bookworm, and in Raspberry Pi OS based on it,
  does not support the RTL-SDR Blog V4. Use a system based on Debian trixie,
  or another dongle.
- Repeater frame formats are not supported. The original EU no-decode report
  with a repeater is unresolved.
- The driver reads no I2C sensor. A BMP280 or BME280 needs its own WeeWX
  service.

## Development

Install WeeWX, numpy and pytest in a virtual environment, then run:

```sh
python -m pytest -q
python tools/package.py
```

`tools/package.py` builds the extension archive in `dist/`. The catalog's
[compatibility workflow](https://github.com/weewx-packages/catalog/actions)
tests catalog releases against WeeWX `master` and `development` once a week.

## License

GPL-3.0-or-later. Original authors include Matthew Wall, Luc Heijst and Douglas
Hall. See [credits](docs/credits.md) and [license](license).
