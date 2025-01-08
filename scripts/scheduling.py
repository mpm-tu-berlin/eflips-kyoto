import logging
from datetime import timedelta

import sqlalchemy.orm
from eflips.model import Scenario, Trip
from eflips.opt.scheduling import create_graph, solve, write_back_rotation_plan


def do_scheduling(
    scenario: Scenario,
    session: sqlalchemy.orm.session.Session,
    max_duration: timedelta | None = None,
):
    logger = logging.getLogger(__name__)
    trips = session.query(Trip).filter(Trip.scenario == scenario).all()
    logger.info(f"Creating graph for scenario {scenario.name}")
    graph = create_graph(
        trips,
        delta_socs=None,
        maximum_schedule_duration=max_duration,
    )
    logger.info(f"Solving scenario {scenario.name}")
    rotation_plan = solve(graph, write_to_file=True)
    logger.info(f"Starting write back for scenario {scenario.name}")
    write_back_rotation_plan(rotation_plan, session)
    logger.info(f"Rotation plan written back for scenario {scenario.name}")
