#!/usr/bin/env python3
"""Bind local Codex accounts to named Orca terminals without switching global login."""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / ".local/agents/accounts.json"


def registry():
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text())
    return {"version": 1, "accounts": {}}


def run_json(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    data = json.loads(result.stdout)
    if data.get("ok") is False:
        raise RuntimeError(json.dumps(data, ensure_ascii=False))
    return data


def inventory(config, executable=None):
    orca = executable or config.get("orca") or os.environ.get("ORCA_CLI_COMMAND")
    if not orca:
        orca = shutil.which("orca-ide")
    if not orca:
        raise RuntimeError("Orca CLI not found; pass --orca /absolute/path")
    data = run_json([orca, "account", "list", "--json"])["result"]["codex"]
    profiles = {}
    default = data.get("systemDefault") or {}
    if default.get("hasAuth"):
        profiles["system"] = {**default, "id": "system", "home": str(Path.home() / ".codex")}
    data_root = Path(os.environ.get("ORCA_USER_DATA_PATH", str(Path.home() / ".config/orca")))
    for row in data.get("accounts", []):
        if row.get("managedHomeRuntime") != "host":
            continue
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", row["id"]):
            raise RuntimeError("Invalid managed account ID")
        profiles[row["id"]] = {
            **row, "home": str(data_root / "codex-accounts" / row["id"] / "home")
        }
    return orca, profiles


def public_profile(row):
    return {key: row.get(key) for key in ("id", "email", "workspaceLabel", "providerAccountId", "home")}


def resolve_account(config, profiles, alias):
    binding = config.get("accounts", {}).get(alias)
    if not binding:
        raise RuntimeError(f"Unknown alias: {alias}; use bind first")
    row = profiles.get(binding["id"])
    if not row:
        raise RuntimeError(f"Account for {alias} is no longer registered; no fallback")
    if (not row.get("providerAccountId") or
            row["providerAccountId"] != binding["providerAccountId"]):
        raise RuntimeError(f"Account identity changed for {alias}; verify and bind explicitly")
    if Path(row["home"]).resolve() != Path(binding["home"]).resolve():
        raise RuntimeError(f"Account home changed for {alias}; verify and bind explicitly")
    auth_path = Path(row["home"]) / "auth.json"
    if not auth_path.is_file():
        raise RuntimeError(f"Account credential file is missing for {alias}; sign in with Orca")
    # Read only identity metadata for comparison; never print or copy credentials.
    auth = json.loads(auth_path.read_text())
    if (auth.get("auth_mode") != "chatgpt" or
            auth.get("tokens", {}).get("account_id") != binding["providerAccountId"]):
        raise RuntimeError(f"Cached login identity differs for {alias}; no fallback")
    return row


def account_env(row, alias):
    env = os.environ.copy()
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"):
        if env.get(name):
            raise RuntimeError(f"{name} is set; resolve the authentication override before using account binding")
    # These are Codex's actual state-directory settings, scoped to the child process.
    env["CODEX_HOME"] = row["home"]
    env["ORCA_CODEX_HOME"] = row["home"]
    env["METAVERSE_AGENT_ACCOUNT"] = alias
    return env


def check_login(config, row, alias):
    executable = config.get("codex") or shutil.which("codex")
    if not executable:
        raise RuntimeError("Codex CLI not found")
    env = account_env(row, alias)
    result = subprocess.run([executable, "login", "status"], env=env,
                            capture_output=True, text=True, timeout=20)
    message = (result.stdout + result.stderr).strip()
    if result.returncode or "Logged in using ChatGPT" not in message:
        raise RuntimeError(f"{alias}: ChatGPT login is not ready: {message}")
    return executable, env


def session_args(executable, env, model, effort):
    if not re.fullmatch(r"gpt-6(?:[.-][A-Za-z0-9]+)*", model):
        raise RuntimeError("Only GPT-6 models are allowed")
    argv = [executable, "--no-daemon", "--model", model,
            "-c", f"model_reasoning_effort={json.dumps(effort)}",
            "-c", 'cli_auth_credentials_store="file"',
            "-c", 'forced_login_method="chatgpt"',
            "--cd", str(ROOT)]
    # Match Orca's shell wrapper: preserve each pane's identity in tool subprocesses.
    for name in ("ORCA_TERMINAL_HANDLE", "ORCA_PANE_KEY", "ORCA_WORKTREE_ID",
                 "ORCA_WORKSPACE_ID", "ORCA_USER_DATA_PATH", "CODEX_HOME",
                 "ORCA_CODEX_HOME", "METAVERSE_AGENT_ACCOUNT"):
        if env.get(name):
            argv += ["-c", f"shell_environment_policy.set.{name}={json.dumps(env[name])}"]
    return argv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--orca", help="Exact Orca CLI executable (saved by bind)")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list", help="List live local Codex account metadata, without credentials")
    bind = sub.add_parser("bind", help="Save a local alias pinned to account identity")
    bind.add_argument("alias")
    bind.add_argument("--account", required=True, help="system or Orca managed account ID")
    doctor = sub.add_parser("doctor", help="Verify bound identities and cached ChatGPT login")
    doctor.add_argument("alias", nargs="?")
    for action in ("session", "start"):
        p = sub.add_parser(action, help="Run in this terminal" if action == "session" else "Create an account-bound Orca terminal")
        p.add_argument("alias")
        p.add_argument("--model", default="gpt-6-astra")
        p.add_argument("--effort", default="xhigh", choices=("low", "medium", "high", "xhigh", "max", "ultra"))
        if action == "start":
            p.add_argument("--title")
    args = parser.parse_args()
    config = registry()
    orca, profiles = inventory(config, args.orca)
    if args.action == "list":
        print(json.dumps({"accounts": [public_profile(p) for p in profiles.values()],
                          "bindings": config["accounts"]}, ensure_ascii=False, indent=2))
        return
    if args.action == "bind":
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", args.alias):
            raise RuntimeError("Alias must use lowercase letters, digits, - or _")
        row = profiles.get(args.account)
        if not row or not row.get("providerAccountId"):
            raise RuntimeError("Account is not available; inspect list")
        executable, _ = check_login(config, row, args.alias)
        config.update(orca=orca, codex=executable)
        config["accounts"][args.alias] = public_profile(row)
        REGISTRY.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = REGISTRY.with_suffix(".tmp")
        with temporary.open("w") as stream:
            os.chmod(temporary, 0o600)
            json.dump(config, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary.replace(REGISTRY)
        print(json.dumps({"alias": args.alias, "account": public_profile(row)}, ensure_ascii=False))
        return
    if args.action == "doctor":
        names = [args.alias] if args.alias else list(config["accounts"])
        if not names:
            raise RuntimeError("No bound accounts; use bind first")
        for alias in names:
            row = resolve_account(config, profiles, alias)
            check_login(config, row, alias)
            print(json.dumps({"alias": alias, "identity": "matched", "login": "ChatGPT",
                              "account": public_profile(row)}, ensure_ascii=False))
        return
    row = resolve_account(config, profiles, args.alias)
    executable, env = check_login(config, row, args.alias)
    argv = session_args(executable, env, args.model, args.effort)
    if args.action == "session":
        print(f"Account binding: {args.alias}; model: {args.model}; isolated server", flush=True)
        os.execve(executable, argv, env)
    else:
        # The CLI has no Codex account flag: use its documented custom-command lane,
        # then give the returned handle to orchestration worker-start --terminal.
        command = shlex.join(["exec", sys.executable, str(Path(__file__).resolve()),
                              "session", args.alias, "--model", args.model, "--effort", args.effort])
        result = run_json([orca, "terminal", "create", "--worktree", "path:" + str(ROOT),
                           "--title", args.title or "agent:" + args.alias,
                           "--command", command, "--json"])
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"agent_accounts: {error}", file=sys.stderr)
        sys.exit(1)
