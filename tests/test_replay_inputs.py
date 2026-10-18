"""Regression tests for shared identity, frozen demand and replay continuity."""
import unittest

from elevator_sim.elevator import Elevator, ElevatorState
from elevator_sim.scenario import PassengerRequest, generate_requests, scenario_hash
from elevator_sim.simulation import Simulation


class ReplayInputs(unittest.TestCase):
    def test_regular_and_pedestrian_ids_share_one_sequence(self):
        sim = Simulation(duration=80, arrival_rate=1, print_event=False)
        for _ in range(80):
            sim._spawn_pedestrian_passenger(1)
            sim.step()
        ids = [p.pid for p in sim.passengers]
        self.assertEqual(len(ids), len(set(ids)))

    def test_pedestrians_do_not_change_regular_external_demand(self):
        plain = Simulation(duration=100, seed=42, print_event=False)
        extra = Simulation(duration=100, seed=42, print_event=False)
        observed = [[], []]
        for now in range(100):
            extra._spawn_pedestrian_passenger(1)
            for i, sim in enumerate((plain, extra)):
                observed[i].extend((p.call_time, p.origin, p.target, p.abandon_time)
                                   for p in sim.step()["new_call"])
        self.assertEqual(observed[0], observed[1])

    def test_frozen_requests_are_identical_for_all_policies(self):
        for seed in (42, 43, 51):
            requests = generate_requests(seed, duration=120)
            original_hash = scenario_hash(requests)
            inputs = []
            for radar, load, safety, hold in ((False, False, False, False),
                                             (True, False, False, False),
                                             (True, True, True, True)):
                sim = Simulation(duration=120, seed=seed, requests=requests,
                                 radar_enabled=radar, load_cell_enabled=load,
                                 anti_pinch_enabled=safety, hold_extension_enabled=hold,
                                 print_event=False)
                sim.run()
                self.assertTrue(sim.is_finished())
                inputs.append([(p.call_time, p.origin, p.target, p.abandon_time)
                               for p in sim.passengers])
            self.assertEqual(inputs[0], inputs[1])
            self.assertEqual(inputs[1], inputs[2])
            self.assertEqual(scenario_hash(requests), original_hash)

    def test_same_scenario_can_be_reused_without_status_leaking(self):
        requests = (PassengerRequest(0, 1, 3), PassengerRequest(3, 4, 1))
        reports = [Simulation(duration=4, requests=requests, print_event=False).run()
                   for _ in range(2)]
        self.assertEqual(reports[0], reports[1])

    def test_reopen_preserves_current_aperture(self):
        e = Elevator(10, 2, 2, 5, 2)
        e.state = ElevatorState.CLOSING
        e._action_timer = 1
        opened = e.door_open_fraction
        self.assertTrue(e.request_reopen())
        self.assertAlmostEqual(e.door_open_fraction, opened)

    def test_invalid_scheduled_request_rejected(self):
        with self.assertRaises(ValueError):
            Simulation(duration=5, requests=[PassengerRequest(0, 1, 1)])


if __name__ == "__main__":
    unittest.main()
