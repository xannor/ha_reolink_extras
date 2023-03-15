# Reolink Extras

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![hacs][hacsbadge]][hacs]
![Project Maintenance][maintenance-shield]

_Integration to extend the [reolink][reolink] integration with additional features._

**This integration will set up the following platforms.**

Platform | Description
-- | --
`media` | Provide access to recordings.

## Installation

1. Using the tool of choice open the directory (folder) for your HA configuration (where you find `configuration.yaml`).
1. If you do not have a `custom_components` directory (folder) there, you need to create it.
1. In the `custom_components` directory (folder) create a new folder called `reolink_extras`.
1. Download _all_ the files from the `custom_components/reolink_extras/` directory (folder) in this repository.
1. Place the files you downloaded in the new directory (folder) you created.
1. Restart Home Assistant
1. In the HA UI go to "Configuration" -> "Integrations" click "+" and search for "Reolink Extras"

## Configuration is done in the UI

<!---->

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

***

[reolink]: https://www.home-assistant.io/integrations/reolink
[reolink_extras]: https://github.com/xannor/ha_reolink_extras
[commits-shield]: https://img.shields.io/github/commit-activity/y/xannor/reolink_extras.svg?style=for-the-badge
[commits]: https://github.com/xannor/reolink_extras/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/xannor/reolink_extras.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-Xannor%20%40xannor-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/xannor/reolink_extras.svg?style=for-the-badge
[releases]: https://github.com/xannor/reolink_extras/releases
