"""Export deterministic demonstrations from the actual simulator, not hand-made motion."""
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from elevator_sim.scenario import PassengerRequest, scenario_hash
from elevator_sim.simulation import Simulation


DEMAND = {
    "normal_ride": (PassengerRequest(0, 1, 4), PassengerRequest(0, 1, 8)),
    # t=8 is the middle of the first closing cycle. Arrival increases doorway
    # occupancy; the simulator's own door-safety logic must reverse the door.
    "anti_pinch": (PassengerRequest(0, 1, 4), PassengerRequest(8, 1, 3)),
}


def export(name, requests):
    sim = Simulation(duration=max(r.call_time for r in requests) + 1,
                     requests=requests, print_event=False, seed=42)
    sim.door_safety.pedestrian_prob = 0
    samples, events = [], []
    while sim.now < sim.max_ticks:
        time = sim.now
        result = sim.step()
        e = sim.elevator
        samples.append({"time": time, "floor": e.visual_position,
                        "at_floor": e.current_floor, "state": e.state.value,
                        "door": e.door_open_fraction,
                        "in_car": [p.pid for p in sim.passengers if p.status.value == "in_car"],
                        "load_kg": sim.load_cell.current_load_kg,
                        "reopens": sim.door_safety.reopen_count})
        if result["open_at"] is not None:
            events.append({"time": time, "type": "doors_open", "floor": result["open_at"]})
        if result["anti_pinch_reopen"]:
            events.append({"time": time, "type": "anti_pinch_reopen", "floor": e.current_floor})
        for key in ("boarders", "leavers"):
            for p in result[key]:
                events.append({"time": time, "type": key, "pid": p.pid, "floor": e.current_floor})
        if sim.is_finished():
            break
    assert sim.is_finished(), f"{name} did not complete"
    assert len({p.pid for p in sim.passengers}) == len(requests)
    assert all(p.status.value == "done" for p in sim.passengers)
    expected_reopens = 1 if name == "anti_pinch" else 0
    assert sim.door_safety.reopen_count == expected_reopens
    return {"schema_version": 1, "name": name, "total_floors": 10,
            "floor_height_m": 3.5, "model_tick_seconds": 1,
            "scenario_sha256": scenario_hash(requests),
            "requests": [asdict(r) for r in requests],
            "passengers": [asdict(p) | {"status": p.status.value} for p in sim.passengers],
            "samples": samples, "events": events,
            "presentation_note": "Walking is staged during door-open dwell; the original model boards instantaneously. No crowd dynamics or hardware validation is claimed."}


def main():
    output = ROOT / "assets" / "replays"
    output.mkdir(parents=True, exist_ok=True)
    for name, requests in DEMAND.items():
        replay = export(name, requests)
        path = output / f"{name}.json"
        path.write_text(json.dumps(replay, ensure_ascii=False, indent=2), encoding="utf-8")
        print(name, "duration", replay["samples"][-1]["time"],
              "events", [(e["time"], e["type"]) for e in replay["events"]])


if __name__ == "__main__":
    main()
