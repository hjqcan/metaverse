extends SceneTree
## Runs only a copied pure validator. No World.Server or client session exists.
const Evidence = preload("res://command_evidence.gd")

var checks: Array[Dictionary] = []
var failures: int = 0

func check_case(label: String, applied: int, version: int, code: String,
		committed: bool, expected: bool, echoed: int = 42) -> void:
	var command: Dictionary = {"preconditionMode": "actor-state-v1", "expectedStateVersion": 42}
	var data: Dictionary = {"stateVersion": version,
		"error": {"code": code},
		"execution": {"preconditionMode": "actor-state-v1",
			"observedStateVersion": echoed, "appliedOnStateVersion": applied}}
	# Exercise the actual JSON number representation used by the native client.
	var wire_command: Dictionary = JSON.parse_string(JSON.stringify(command))
	var wire_data: Dictionary = JSON.parse_string(JSON.stringify(data))
	var actual: bool = Evidence.execution(wire_data, wire_command, committed)
	var passed: bool = actual == expected
	checks.append({"name": label, "expected": expected, "actual": actual, "passed": passed,
		"appliedOnStateVersion": applied, "stateVersion": version, "errorCode": code,
		"committed": committed, "observedStateVersion": echoed,
		"wireNumberIsFloat": typeof(wire_command.expectedStateVersion) == TYPE_FLOAT})
	if not passed:
		failures += 1
		push_error("FAIL " + label)

func run_cases() -> bool:
	check_case("ordinary rejection at current transaction version", 43, 43, "RESOURCE_DEPLETED", false, true)
	check_case("future observation rejected with the dedicated code", 0, 0, "STATE_VERSION_AHEAD", false, true)
	check_case("future observation cannot confirm unrelated rejection", 0, 0, "RESOURCE_DEPLETED", false, false)
	check_case("valid concurrent commit uses applied version plus one", 43, 44, "", true, true)
	check_case("incorrect commit version stays unconfirmed", 43, 45, "", true, false)
	check_case("different original observation stays unconfirmed", 43, 44, "", true, false, 41)
	return true

func _initialize() -> void:
	if run_cases() != true:
		failures += 1
	var result: Dictionary = {"kind": "actual-godot-headless-pure-validator-recheck",
		"passed": failures == 0, "checks": checks, "failures": failures,
		"actualWorldCommands": 0, "actualModelCalls": 0,
		"fullClientExecuted": false, "serverExecuted": false, "visualUiExecuted": false}
	var output: FileAccess = FileAccess.open(OS.get_environment("RESEARCH_OUTPUT"), FileAccess.WRITE)
	if output == null:
		push_error("Could not write research result")
		quit(2)
		return
	output.store_string(JSON.stringify(result, "  ") + "\n")
	output.close()
	print("Execution evidence checks: %d passed, %d failed" % [checks.size() - failures, failures])
	quit(1 if failures else 0)
