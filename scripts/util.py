import subprocess

import psycopg2
import sqlalchemy.engine
import sqlalchemy.orm
from eflips.model import Base, Scenario, VehicleType, Trip, Rotation
from psycopg2._psycopg import parse_dsn
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def construct_database_url(
    db_name: str, db_user: str, db_password: str, db_host: str, db_port: int
):
    """
    Constructs a database URL for use with SQLAlchemy.

    :param db_name: The name of the database.
    :param db_user: The username to connect to the database.
    :param db_password: The password to connect to the database.
    :param db_host: The host of the database.
    :param db_port: The port of the database.
    :return: A SQLAlchemy database URL.
    """
    return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


def clear_database(database_url: str):
    """
    Uses eflips-model to clear the database.
    **This will delete all data in the database.**
    :param engine: A SQLAlchemy engine.
    :return: None
    """
    engine = create_engine(database_url)
    Base.metadata.drop_all(engine)
    engine.dispose()


def import_database_dump(database_url: str, dump_path: str):
    """
    Uses eflips-model to import a database dump. Only runs if there are no scenarios in the database.

    :param engine: A SQLAlchemy engine.
    :param dump_path: The path to the database dump.
    :return: None
    """
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            if session.query(Scenario).count() > 0:
                raise ValueError("Database is not empty. Refusing to import dump.")
    except sqlalchemy.exc.ProgrammingError:
        pass
    engine.dispose()

    # Manually delete the "alembic_version" table
    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS alembic_version")
        conn.commit()

    database_info = parse_dsn(database_url)
    subprocess.check_output(
        f"psql -h {database_info['host']} -U {database_info['user']} -p {database_info['port']} {database_info['dbname']} -f {dump_path}",
        shell=True,
    )


def create_three_scenarios(session: sqlalchemy.orm.session.Session):
    current_scenario = session.query(Scenario).one()
    cloned_scenario_1 = current_scenario.clone(session)
    cloned_scenario_2 = current_scenario.clone(session)

    current_scenario.name = "Depot Charging"
    current_scenario.name_short = "DC"
    cloned_scenario_1.name = "Mixed Charging"
    cloned_scenario_1.name_short = "MIX"
    cloned_scenario_2.name = "Terminus Charging"
    cloned_scenario_2.name_short = "TERM"


def fixup_rotations(session: sqlalchemy.orm.session.Session) -> None:
    """
    Fix the rotations of the scenarios, by adding a single rotation for each trip
    :param session: An SQLAlchemy session
    :return: None
    """
    vehicle_type = (
        session.query(VehicleType).filter(VehicleType.name == "ElectricBus").one()
    )
    for trip in session.query(Trip):
        rotation = Rotation(
            scenario_id=trip.scenario_id,
            vehicle_type=vehicle_type,
            allow_opportunity_charging=True,
        )
        session.add(rotation)
        trip.rotation = rotation
    session.flush()
    session.expire_all()  # Unclear why this is necessary. But it helps…
