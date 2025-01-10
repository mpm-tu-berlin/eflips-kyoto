import logging
from datetime import timedelta

import sqlalchemy.orm
from eflips.model import (
    Scenario,
    Station,
    ChargeType,
    VoltageLevel,
    Route,
    Rotation,
    Trip,
    TripType,
    Event,
    EventType,
    Depot,
    Area,
    AreaType,
    VehicleType,
    Plan,
    Process,
    AssocPlanProcess,
    Vehicle,
)
from sqlalchemy.orm import Session


def add_empty_trips(scenario: Scenario, session: sqlalchemy.orm.session.Session):
    """
    Add empty trips from the depot to the first stop and from the last stop to the depot.
    :param scenario:
    :param session:
    :return:
    """

    DEPOT_LATLON = (34.97900836429751, 135.75613027247684)
    DEPOT_TRIP_DURATION = timedelta(minutes=6)
    DEPOT_TRIP_DISTANCE = 3100  # meters
    DEPOT_NAME = "九条車庫前"

    # Check if the depot is already in the stops
    if (
        session.query(Station)
        .filter(Station.scenario == scenario)
        .filter(Station.name == DEPOT_NAME)
        .one_or_none()
        is None
    ):
        depot = Station(
            scenario=scenario,
            name=DEPOT_NAME,
            name_short="DEP",
            geom=f"SRID=4326;POINT({DEPOT_LATLON[1]} {DEPOT_LATLON[0]} 0)",
            is_electrified=True,
            amount_charging_places=100,  # Dummy value, only used by simBA charging, which gets overwritten
            power_per_charger=300,  # kW, also dummy
            power_total=100 * 300,  # kW, also dummy
            charge_type=ChargeType.DEPOT,
            voltage_level=VoltageLevel.HV,
        )
        session.add(depot)
    else:
        raise ValueError(
            "Depot already in stops. Since we clear the database before running, this should not happen."
        )

    terminal = (
        session.query(Station)
        .filter(Station.scenario == scenario)
        .filter(Station.name == "北大路バスターミナル（地下鉄北大路駅）")
        .one()
    )

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
    for rotation in session.query(Rotation).filter(Rotation.scenario == scenario):
        first_trip_start = rotation.trips[0].departure_time
        depot_trip_end = first_trip_start - BREAK_DURATION
        depot_trip_start = depot_trip_end - DEPOT_TRIP_DURATION
        depot_trip = Trip(
            scenario=scenario,
            route=depot_to_first_stop,
            departure_time=depot_trip_start,
            arrival_time=depot_trip_end,
            trip_type=TripType.EMPTY,
            loaded_mass=0,
        )
        session.add(depot_trip)
        rotation.trips.insert(0, depot_trip)
        del depot_trip  # Because we don't want to accidentally use it again

        last_trip_end = rotation.trips[-1].arrival_time
        depot_trip_start = last_trip_end + BREAK_DURATION
        depot_trip_end = depot_trip_start + DEPOT_TRIP_DURATION
        depot_trip = Trip(
            scenario=scenario,
            route=first_stop_to_depot,
            departure_time=depot_trip_start,
            arrival_time=depot_trip_end,
            trip_type=TripType.EMPTY,
            loaded_mass=0,
        )
        session.add(depot_trip)
        rotation.trips.append(depot_trip)
        del depot_trip


def delete_invalid_rotations_and_trips(
    scenario: Scenario, session: sqlalchemy.orm.session.Session
):
    logger = logging.getLogger(__name__)
    rotations_to_delete = []
    for rotation in session.query(Rotation).filter(Rotation.scenario == scenario):
        for i, trip in enumerate(rotation.trips):
            if trip != rotation.trips[-1]:
                if (
                    rotation.trips[i].route.arrival_station
                    != rotation.trips[i + 1].route.departure_station
                ):
                    rotations_to_delete.append(rotation)

    rotations_to_delete = list(set(rotations_to_delete))
    if len(rotations_to_delete) > 0:
        logger.warning(
            f"Deleting {len(rotations_to_delete)} rotations with invalid trips."
        )
    for rotation in rotations_to_delete:
        for trip in rotation.trips:
            for stop_time in trip.stop_times:
                session.delete(stop_time)
            for event in trip.events:
                session.delete(event)
            session.delete(trip)
        session.delete(rotation)

    # Also, delete all trips where their driving event has a negative energy consumption
    for event in (
        session.query(Event)
        .filter(Event.scenario == scenario)
        .filter(Event.event_type == EventType.DRIVING)
        .filter(Event.soc_start <= Event.soc_end)
    ):
        logger.warning(
            f"Deleting trip {event.trip.id} because it has a negative energy consumption."
        )
        for stop_time in event.trip.stop_times:
            session.delete(stop_time)
        trip = event.trip
        for event in trip.events:
            session.delete(event)
        rotation = trip.rotation
        rotation.trips.remove(trip)
        session.delete(trip)


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
        station=session.query(Station)
        .filter(Station.scenario == scenario)
        .filter(Station.name_short == "DEP")
        .one(),
    )
    session.add(depot)

    # Add a single waiting area to the depot
    waiting_area = Area(
        scenario=scenario,
        depot=depot,
        area_type=AreaType.DIRECT_ONESIDE,
        vehicle_type=None,
        name="Waiting area",
        capacity=10,
    )
    session.add(waiting_area)

    # Add a single direct charging area to the depot
    with session.no_autoflush:
        charging_area = Area(
            scenario=scenario,
            depot=depot,
            area_type=AreaType.DIRECT_ONESIDE,
            vehicle_type=session.query(VehicleType)
            .filter(VehicleType.scenario == scenario)
            .filter(VehicleType.name == "ElectricBus")
            .one(),
            name="Direct charging area",
            capacity=10,
        )
    session.add(charging_area)

    plan = Plan(
        scenario=scenario,
        name="Direct charging plan",
    )
    session.add(plan)

    charging_process = Process(
        scenario=scenario,
        name="Direct charging process",
        dispatchable=True,
        electric_power=50,
        areas=[charging_area],
    )
    session.add(charging_process)
    assoc_charging_process = AssocPlanProcess(
        scenario=scenario,
        plan=plan,
        process=charging_process,
        ordinal=0,
    )
    session.add(assoc_charging_process)

    standby_departure_process = Process(
        scenario=scenario,
        name="Standby departure process",
        dispatchable=True,
        electric_power=None,
        areas=[charging_area],
    )
    session.add(standby_departure_process)
    assoc_standby_departure_process = AssocPlanProcess(
        scenario=scenario,
        plan=plan,
        process=standby_departure_process,
        ordinal=1,
    )
    session.add(assoc_standby_departure_process)

    depot.default_plan = plan
    session.add(plan)


def fix_driving_events(scenario: Scenario, session: Session):
    """
    - add a driving event to the first trip of each rotation
    - assign all driving events to the same vehicle
    - add a driving event to the last trip of each rotation

    :param scenario:
    :param session:
    :return: Nothing
    """

    # In order to add the events to the trips, we calculate the average energy consumption of the vehicles
    sum_of_energy = 0
    sum_of_distance = 0
    for event in (
        session.query(Event)
        .filter(Event.scenario == scenario)
        .filter(Event.event_type == EventType.DRIVING)
    ):
        sum_of_energy += (
            event.soc_start - event.soc_end
        ) * event.vehicle_type.battery_capacity
        sum_of_distance += event.trip.route.distance / 1000  # convert to km

    average_energy_consumption = sum_of_energy / sum_of_distance
    for rotation in session.query(Rotation).filter(Rotation.scenario == scenario):
        # Create a new vehicle for each rotation
        vehicle = Vehicle(
            scenario=scenario,
            name=f"Auto-Generated Vehicle for Rotation {rotation.id}",
            name_short=f"V_{rotation.id}",
            vehicle_type=session.query(VehicleType)
            .filter(VehicleType.scenario == scenario)
            .filter(VehicleType.name == "ElectricBus")
            .one(),
        )
        session.add(vehicle)
        rotation.vehicle = vehicle

        soc_at_start_of_trip = 1
        for i, trip in enumerate(rotation.trips):

            if i == 0 or i == len(rotation.trips) - 1:
                assert len(trip.events) == 0
                # The first or last trip of a rotation should not have a driving event, as it is an empty trip
                # which we have just created
                energy = (trip.route.distance / 1000) * average_energy_consumption
                delta_soc = energy / rotation.vehicle_type.battery_capacity
                soc_at_end_of_trip = soc_at_start_of_trip - delta_soc
                event = Event(
                    scenario=scenario,
                    trip=trip,
                    event_type=EventType.DRIVING,
                    vehicle=vehicle,
                    vehicle_type=vehicle.vehicle_type,
                    time_start=trip.departure_time,
                    time_end=trip.arrival_time,
                    soc_start=soc_at_start_of_trip,
                    soc_end=soc_at_end_of_trip,
                )
                session.add(event)
            else:
                assert len(trip.events) == 1
                event = trip.events[0]
                event.vehicle = vehicle
                delta_soc = event.soc_start - event.soc_end
                if delta_soc < 0:
                    breakpoint()
                event.soc_start = soc_at_start_of_trip
                event.soc_end = soc_at_start_of_trip - delta_soc
                session.merge(event)
            soc_at_start_of_trip = event.soc_end
