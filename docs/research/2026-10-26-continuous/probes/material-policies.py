#!/usr/bin/env python3
"""Small deterministic policy model, NOT a World.Server acceptance test.

Material growth, queues, reservation expiry and known control groups below are
candidate rules. None is claimed to exist in the current virtual world.
"""
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[4]
HORIZON = 36
RATE = 3
CAPACITY = 6
PROJECT = 3


def scenario(policy, early_actors=1, offline=False, lease=2, known_control=False):
    # All A names have one underlying controller in this constructed model.
    # B is independent by assumption, not by an identity-verification system.
    aliases = [f"early-{i}" for i in range(early_actors)]
    served_ids = ["early-controller", "late-controller"] if known_control else aliases + ["late"]
    late = "late-controller" if known_control else "late"
    queue = deque(served_ids)
    reservations = {}
    pool = 0
    issued = 12
    early_inventory = 6
    embodied = 6
    b_reservation = None
    trace = []
    expired = 0
    for cycle in range(1, HORIZON + 1):
        for actor, (quantity, start) in list(reservations.items()):
            if lease is not None and cycle - start >= lease:
                pool += quantity
                del reservations[actor]
                queue.append(actor)  # Returning requests go to the tail.
                expired += 1
        growth = min(RATE, CAPACITY - pool - sum(q for q, _ in reservations.values()))
        assert growth >= 0
        pool += growth
        issued += growth
        if policy in ("first_arrival", "inventory_cap"):
            # Candidate cap=6 is bypassed by legal recurrent consumption.
            # Such unlimited consumption is a model assumption, not r8 geometry.
            if policy == "inventory_cap":
                early_inventory -= PROJECT
                embodied += PROJECT
            harvested = min(pool, PROJECT)
            early_inventory += harvested
            pool -= harvested
            if policy == "first_arrival":
                early_inventory -= harvested
                embodied += harvested
            assert early_inventory <= 6
        else:
            while pool >= PROJECT and queue:
                actor = queue.popleft()
                assert actor not in reservations
                reservations[actor] = (PROJECT, cycle)
                pool -= PROJECT
                if actor == late:
                    b_reservation = cycle
                    break
            for actor, (quantity, _) in list(reservations.items()):
                if actor != late and not offline:
                    del reservations[actor]
                    # Idealized instant gathering then consumption, no travel.
                    embodied += quantity
                    queue.append(actor)
        reserved = sum(q for q, _ in reservations.values())
        assert issued == pool + reserved + early_inventory + embodied
        assert pool + reserved <= CAPACITY
        trace.append({"cycle": cycle, "newMaterial": growth, "issued": issued,
                      "availableNaturalMaterial": pool, "reservedNaturalMaterial": reserved,
                      "earlyInventory": early_inventory, "embodied": embodied,
                      "lateReservationAvailable": b_reservation is not None})
        if b_reservation is not None:
            break
    return {"policy": policy, "earlyActorCount": early_actors,
            "controlGroupsKnown": known_control, "earlyReservationUsersOffline": offline,
            "reservationLeaseCycles": lease if policy == "fifo_reservation" else None,
            "lateFirstReservationCycle": b_reservation,
            "lateHasThreeUnitsReserved": b_reservation is not None,
            "lateActualWorldProjectVerified": False,
            "expiredReservations": expired,
            "final": trace[-1], "conservedAtEveryCycle": True, "trace": trace}


def main():
    cases = [scenario("first_arrival"), scenario("inventory_cap")]
    for aliases in (1, 7, 31):
        cases.append(scenario("fifo_reservation", early_actors=aliases))
    cases.append(scenario("fifo_reservation", early_actors=31, known_control=True))
    cases.append(scenario("fifo_reservation", early_actors=2, offline=True, lease=None))
    cases.append(scenario("fifo_reservation", early_actors=2, offline=True, lease=2))
    assert [c["lateFirstReservationCycle"] for c in cases] == [None, None, 2, 8, 32, 2, None, 3]
    report = {
        "recordedAtUtc": datetime.now(timezone.utc).isoformat(),
        "kind": "hypothetical-policy-model", "actualModelCalls": 0,
        "actualWorldCommands": 0, "serverProcessesStarted": 0,
        "scriptSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "parameters": {"horizonCycles": HORIZON, "growthBudgetPerCycle": RATE,
                       "unharvestedCapacity": CAPACITY, "projectMaterial": PROJECT,
                       "initialTotalMaterial": 12, "earlyInitialInventory": 6,
                       "initialEmbodiedMaterial": 6},
        "assumptions": ["cycles have no chosen real-time duration",
                        "new material is an explicit candidate source, not current r8 behavior",
                        "all early aliases share one controller, late resident independent by construction",
                        "early actors always arrive first and have recurrent material-consuming demand",
                        "no travel, buildable area, latency, production capital, or unknown-control inference",
                        "late output is a reservation, not a verified gather or construction"],
        "cases": cases,
    }
    run = ROOT / ".local/research/material-policies" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])
    run.mkdir(parents=True, mode=0o700)
    output = run / "results.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Evidence:", output)
    print(json.dumps({"cases": len(cases), "reservationCycles": [c["lateFirstReservationCycle"] for c in cases],
                      "allMaterialConserved": all(c["conservedAtEveryCycle"] for c in cases)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
