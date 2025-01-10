import os

import eflips
import eflips.eval.input.prepare
import eflips.eval.input.visualize
import eflips.eval.output.prepare
import eflips.eval.output.visualize
import sqlalchemy
from eflips.model import Rotation, Event, Vehicle


def _rename_rotations(scenario, session):
    """
    Assign a user-friendly name to each rotation in the scenario.

    :param scenario: The Scenario object containing the rotations.
    :param session: A SQLAlchemy session for querying the database.
    """
    for rotation in session.query(Rotation).filter(Rotation.scenario == scenario):
        rotation.name = f"Rotation {rotation.id}"


def _plot_rotation_plan(scenario, session, scenario_dir):
    """
    Create and save an HTML plot displaying the rotation information
    for the given scenario.

    :param scenario: The Scenario object for which to create the plot.
    :param session: A SQLAlchemy session for querying the required data.
    :param scenario_dir: The directory path where the plot will be saved.
    """
    rotation_ids = [
        r[0]
        for r in session.query(Rotation.id).filter(Rotation.scenario == scenario).all()
    ]
    rotation_info = eflips.eval.input.prepare.rotation_info(
        scenario_id=scenario.id, session=session, rotation_ids=rotation_ids
    )
    fig = eflips.eval.input.visualize.rotation_info(rotation_info)
    fig.update_layout(title=f"Rotation information for scenario {scenario.name_short}")
    fig.write_html(os.path.join(scenario_dir, "rotation_info.html"))


def _plot_depot_load(scenario, session, scenario_dir):
    """
    Create and save an HTML plot displaying power and occupancy (load)
    for the depots in the given scenario.

    :param scenario: The Scenario object for which to create the plot.
    :param session: A SQLAlchemy session for querying the required data.
    :param scenario_dir: The directory path where the plot will be saved.
    """
    area_ids = [
        a[0]
        for a in session.query(Event.area_id)
        .filter(Event.scenario == scenario)
        .distinct()
        .all()
    ]
    df = eflips.eval.output.prepare.power_and_occupancy(area_ids, session)
    fig = eflips.eval.output.visualize.power_and_occupancy(df)
    fig.update_layout(title=f"Power and occupancy for scenario {scenario.name_short}")
    fig.write_html(os.path.join(scenario_dir, "power_and_occupancy.html"))


def _plot_depot_event_timeline(scenario, session, scenario_dir):
    """
    Create and save an HTML plot visualizing all events happening
    in the depot (e.g., arrivals, departures, charging, etc.).

    :param scenario: The Scenario object for which to create the plot.
    :param session: A SQLAlchemy session for querying the required data.
    :param scenario_dir: The directory path where the plot will be saved.
    """
    vehicle_ids = [
        v[0]
        for v in session.query(Vehicle.id).filter(Vehicle.scenario == scenario).all()
    ]
    df = eflips.eval.output.prepare.depot_event(scenario.id, session, vehicle_ids)
    color_scheme = "event_type"
    fig = eflips.eval.output.visualize.depot_event(df, color_scheme=color_scheme)
    fig.update_layout(title=f"Depot events for scenario {scenario.name_short}")
    fig.write_html(os.path.join(scenario_dir, f"depot_event_{color_scheme}.html"))


def _plot_vehicle_socs(scenario, session, scenario_dir):
    """
    Create and save an HTML plot (one per vehicle) showing the state of
    charge (SoC) over time for each vehicle in the scenario.

    :param scenario: The Scenario object for which to create the SoC plots.
    :param session: A SQLAlchemy session for querying the required data.
    :param scenario_dir: The directory path where the plots will be saved.
    """
    # For each vehicle, create a SoC over time plot
    for vehicle in session.query(Vehicle).filter(Vehicle.scenario == scenario):
        df, descriptions = eflips.eval.output.prepare.vehicle_soc(vehicle.id, session)
        fig = eflips.eval.output.visualize.vehicle_soc(df, descriptions)
        fig.update_layout(title=f"Vehicle {vehicle.id} SoC over time")
        fig.write_html(
            os.path.join(scenario_dir, "vehicle_socs", f"vehicle_{vehicle.id}_soc.html")
        )


def plot_results(
    scenario: "Scenario", session: "sqlalchemy.orm.session.Session", config: dict
):
    """
    Create and save multiple plots that visualize the results of a given scenario:
      - Rotation plan
      - Depot load (power and occupancy)
      - Depot event timeline
      - Vehicle SoC over time

    The plots are saved in an output folder named after the scenario.
    """
    # Create output directory for the scenario and subfolder for vehicle SoCs
    os.makedirs(
        os.path.join(
            config["paths"]["output_dir"],
            f"scenario {scenario.name_short}",
            "vehicle_socs",
        ),
        exist_ok=True,
    )
    scenario_dir = os.path.join(
        config["paths"]["output_dir"],
        f"scenario {scenario.name_short}",
    )

    # Rename rotations for better readability
    _rename_rotations(scenario, session)

    # Generate the various plots
    _plot_rotation_plan(scenario, session, scenario_dir)
    _plot_depot_load(scenario, session, scenario_dir)
    _plot_depot_event_timeline(scenario, session, scenario_dir)
    _plot_vehicle_socs(scenario, session, scenario_dir)
