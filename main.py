#!/usr/bin/env python3

"""
This is the main file of the project. Run it to start the program.
"""
import logging
import os
import tomllib
from datetime import timedelta

from eflips.model import Scenario
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from scripts import util
from scripts.scheduling import do_scheduling
from scripts.util import create_three_scenarios, fixup_rotations

if os.path.exists("config.toml"):
    with open("config.toml", "rb") as fp:
        config = tomllib.load(fp)
else:
    raise FileNotFoundError("config.toml not found.")

DB_URL = util.construct_database_url(
    config["database"]["dbname"],
    config["database"]["user"],
    config["database"]["password"],
    config["database"]["host"],
    config["database"]["port"],
)


def setup_database():
    logger = logging.getLogger(__name__)

    util.clear_database(DB_URL)
    util.import_database_dump(DB_URL, config["paths"]["input_sql"])

    logger.info("Database setup complete.")


if __name__ == "__main__":
    logging.basicConfig(level=config["logging"]["level"])
    setup_database()
    engine = create_engine(DB_URL)
    with Session(engine) as session:
        fixup_rotations(session)
        create_three_scenarios(session)
        for scenario in session.query(Scenario):
            if scenario.name_short == "MIX":
                max_duration = timedelta(hours=5)
            else:
                max_duration = None
            do_scheduling(scenario, session, max_duration)

        session.commit()
