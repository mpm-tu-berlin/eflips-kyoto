#!/usr/bin/env python3

"""
This is the main file of the project. Run it to start the program.
"""
import logging
import os
import tomllib
from datetime import timedelta

import sqlalchemy.orm.session
from eflips.depot.api import simulate_scenario
from eflips.model import Scenario, Station, ChargeType, VoltageLevel, Route, Rotation, Trip, TripType, Depot, Plan, \
    Area, Process, AreaType
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



def add_empty_trips(scenario: Scenario, session: sqlalchemy.orm.session.Session):
    """
    Add empty trips from the depot to the first stop and from the last stop to the depot.
    :param scenario:
    :param session:
    :return:
    """

    raise NotImplementedError("We also need to add events here, taking the median energy consumption of the vehicles into account.")

    DEPOT_LATLON = (34.97900836429751, 135.75613027247684)
    DEPOT_TRIP_DURATION = timedelta(minutes=6)
    DEPOT_TRIP_DISTANCE = 3100 # meters
    DEPOT_NAME = "九条車庫前"

    # Check if the depot is already in the stops
    if session.query(Station).filter(Station.scenario == scenario).filter(Station.name == DEPOT_NAME).one_or_none() is None:
        depot = Station(
            scenario=scenario,
            name=DEPOT_NAME,
            name_short="DEP",
            geom=f"SRID=4326;POINT({DEPOT_LATLON[1]} {DEPOT_LATLON[0]} 0)",
            is_electrified=True,
            amount_charging_places=100, # Dummy value, only used by simBA charging, which gets overwritten
            power_per_charger=300, # kW, also dummy
            power_total=100*300, # kW, also dummy
            charge_type = ChargeType.DEPOT,
            voltage_level=VoltageLevel.HV
        )
        session.add(depot)
    else:
        raise ValueError("Depot already in stops. Since we clear the database before running, this should not happen.")

    terminal = session.query(Station).filter(Station.scenario == scenario).filter(Station.name == "北大路バスターミナル（地下鉄北大路駅）").one()

    # Add the route and keep a reference to it
    depot_to_first_stop = Route(
        scenario=scenario,
        departure_station=depot,
        arrival_station=terminal,
        name="九条車庫前 → 北大路バスターミナル",
        name_short="DEP_TERM",
        distance=DEPOT_TRIP_DISTANCE,
    )
    session.add(depot_to_first_stop)

    first_stop_to_depot = Route(
        scenario=scenario,
        departure_station=terminal,
        arrival_station=depot,
        name="北大路バスターミナル → 九条車庫前",
        name_short="TERM_DEP",
        distance=DEPOT_TRIP_DISTANCE,
    )
    session.add(first_stop_to_depot)

    # Now, add trips to each rotation
    BREAK_DURATION = timedelta(minutes=5)
    for rotation in session.query(Rotation).filter(Rotation.scenario==scenario):
        first_trip_start = rotation.trips[0].departure_time
        depot_trip_end = first_trip_start - BREAK_DURATION
        depot_trip_start = depot_trip_end - DEPOT_TRIP_DURATION
        depot_trip = Trip(
            scenario=scenario,
            route=depot_to_first_stop,
            departure_time=depot_trip_start,
            arrival_time=depot_trip_end,
            trip_type=TripType.EMPTY,
            loaded_mass=0
        )
        session.add(depot_trip)
        rotation.trips.insert(0, depot_trip)
        del depot_trip # Because we don't want to accidentally use it again

        last_trip_end = rotation.trips[-1].arrival_time
        depot_trip_start = last_trip_end + BREAK_DURATION
        depot_trip_end = depot_trip_start + DEPOT_TRIP_DURATION
        depot_trip = Trip(
            scenario=scenario,
            route=first_stop_to_depot,
            departure_time=depot_trip_start,
            arrival_time=depot_trip_end,
            trip_type=TripType.EMPTY,
            loaded_mass=0
        )
        session.add(depot_trip)
        rotation.trips.append(depot_trip)
        del depot_trip



def delete_invalid_rotations(scenario: Scenario, session: sqlalchemy.orm.session.Session):
    logger = logging.getLogger(__name__)
    rotations_to_delete = []
    for rotation in session.query(Rotation).filter(Rotation.scenario == scenario):
        for i, trip in enumerate(rotation.trips):
            if trip != rotation.trips[-1]:
                if rotation.trips[i].route.arrival_station != rotation.trips[i + 1].route.departure_station:
                    rotations_to_delete.append(rotation)

    rotations_to_delete = list(set(rotations_to_delete))
    if len(rotations_to_delete) > 0:
        logger.warning(f"Deleting {len(rotations_to_delete)} rotations with invalid trips.")
    for rotation in rotations_to_delete:
        for trip in rotation.trips:
            for stop_time in trip.stop_times:
                session.delete(stop_time)
            for event in trip.events:
                session.delete(event)
            session.delete(trip)
        session.delete(rotation)

def add_depot(scenario: Scenario, session: Session):
    """
    Add ad depot at the station with the "DEP" name_short.
    :param scenario: The scenario to add the depot to.
    :param session: THe session to add the depot to.
    :return: None
    """
    depot = Depot(
        scenario=scenario,
        name="Depot at Kyūjō Shako-mae",
        station = session.query(Station).filter(Station.scenario == scenario).filter(Station.name_short == "DEP").one()
    )
    session.add(depot)

    # Add a single direct charging area to the depot
    charging_area = Area(
        scenario=scenario,
        depot=depot,
        area_type=AreaType.DIRECT_ONESIDE,
        vehicle_type=None,
        name="Direct charging area",
        capacity=10,
    )
    session.add(charging_area)

    charging_process = Process(
        scenario=scenario,
        name="Direct charging process",
        dispatchable=True,
        electric_power=50,
        areas=[charging_area]
    )
    session.add(charging_process)

    standby_departure_process = Process(
        scenario=scenario,
        name="Standby departure process",
        dispatchable=True,
        electric_power=None,
        areas=[charging_area]
    )

    plan = Plan(
        scenario=scenario,
        name="Direct charging plan",
        processes=[charging_process, standby_departure_process]
    )
    depot.default_plan = plan
    session.add(plan)
    session.flush()



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
            add_empty_trips(scenario, session)
            delete_invalid_rotations(scenario, session)
            add_depot(scenario, session)

            simulate_scenario(scenario, session)

        session.commit()
