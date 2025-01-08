# eflips-kyoto

---

Part of the [eFLIPS/simBA](https://github.com/stars/ludgerheide/lists/ebus2030) list of projects.

---

Application of the [eFLIPS](https://www.tu.berlin/mpm/forschung/projekte/eflips) bus simulation framework to a dataset from kyoto.

## Installation

1. Clone this git repository
2. Install the packages listed in `requirements.txt`
3. Open `settings.toml.sample`, set `database_url` to a Postgres database (with PostGIS and the `btree_gist`) extension and save it to `settings.toml`.

## Usage 

Running `main.py` will **clear the existing database**, run the simulation and save the documents to the `output` directory.

# License

This project is licensed under the AGPLv3 license - see the [LICENSE](LICENSE.md) file for details.

## Funding Notice

This code was developed as part of the project [eBus2030+]([https://www.eflip.de/](https://www.now-gmbh.de/projektfinder/e-bus-2030/)) funded by the Federal German Ministry for Digital and Transport (BMDV) under grant number 03EMF0402.
