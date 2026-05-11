# Remote Runner

Local CLI infrastructure for controlling remote machines through agent-friendly sessions.

Remote Runner turns configured remote machines into stable local CLI resources. The core is not
research, SEED, SSH convenience, tmux, or file mounting. The core is a predictable interface for
remote interaction: list machines, diagnose connections, create sessions, execute commands in a
remote directory, explicitly transfer files, and collect structured output, logs, and artifacts.

## Current Status

This repository currently contains the `seed-runner` prototype that started as a SEED lab
experiment runner. That prototype validated the deeper need: agents need a small, auditable local
tool for operating remote machines without repeatedly handling credentials and connection plumbing.

The project direction is now broader:

- `seed-runner` is the current prototype CLI and implementation.
- Remote Runner is the provisional product boundary and working name.
- Research, experiments, operations, SEED labs, model training, and benchmarks are use cases above
  the remote-interaction layer.
- SSH, tmux, sshfs, rsync, SFTP, Slurm, Docker, and Kubernetes are backend details, not product
  identity.

## One-Sentence Definition

Remote Runner is a lightweight local CLI that turns configured remote machines into agent-friendly
sessions for command execution, structured output, logs, and artifact handling.

## Core Principles

- Remote interaction first: the product is a CLI interface for operating remote machines.
- Local-first: the tool is installed, configured, and called on the user's own machine.
- Machine registry: users configure remote machines once, then humans or agents use machine IDs.
- Credential absorption: normal workflows should not revolve around passwords, private keys, jump
  hosts, or SSH incantations.
- Stable CLI contract: commands should support non-interactive use, JSON output, clear errors,
  timeouts, recovery, log lookup, and cleanup.
- Explicit transfer: file movement should be done through `file put/get/list`, not by assuming a
  mounted local/remote tree.
- Implementation flexibility: backend mechanisms can change without changing the machine/session
  contract.
- Domain workflows on top: research reports, SEED automation, operations runbooks, training jobs,
  and benchmarks are higher-level profiles.

## Target MVP Interface

The intended CLI shape is:

```bash
remote-runner machine add
remote-runner machine configure-startup lab-gpu-01 \
  --startup-command wsl \
  --default-cwd /mnt/c/Users/example/Desktop/SSHRunner \
  --json
remote-runner machine configure-path-map lab-gpu-01 \
  --command-prefix /mnt/c/Users/example/Desktop/SSHRunner \
  --file-prefix C:/Users/example/Desktop/SSHRunner \
  --json
remote-runner machine list --json
remote-runner machine show lab-gpu-01 --json
remote-runner machine doctor lab-gpu-01 --json

remote-runner session create --machine lab-gpu-01 --cwd /home/user/project --json
remote-runner session exec --session sess_abc123 --cmd "pytest -q" --timeout 300 --json
remote-runner session logs --session sess_abc123 --json
remote-runner session destroy --session sess_abc123 --json

remote-runner file put --session sess_abc123 --local ./input.txt --remote /home/user/project/input.txt --json
remote-runner file get --session sess_abc123 --remote /home/user/project/output.txt --local ./output.txt --json
remote-runner file list --session sess_abc123 --remote /home/user/project --json

remote-runner run once \
  --machine lab-gpu-01 \
  --cwd /home/user/project \
  --input ./input.txt=/home/user/project/input.txt \
  --cmd "python job.py --input input.txt --output output.txt" \
  --artifact /home/user/project/output.txt=./output.txt \
  --json
```

`session exec --json` should return the command, remote working directory, stdout, stderr,
exit code, timestamps, duration, and local log path.

`remote-runner machine add --json` prompts for missing SSH machine fields and writes prompts to
stderr, so stdout remains one JSON object. Password auth uses hidden input in the recommended
interactive path. The `--password` flag exists for compatibility and tests, but it is not the
recommended way to enter real credentials because shell history can leak it.

Machines can also store ordered startup commands that run immediately after SSH login and before
the normal `cd` plus user command. This is for hosts such as Windows OpenSSH where the usable Linux
shell is reached by first running `wsl`.

Machines can store explicit path mappings when command execution and SFTP use different path
namespaces. `file put/get/list` apply those mappings before transfer while keeping user-facing
paths in local state records.

`run once` is the first generic closed-loop layer above machine/session/file: it can upload inputs,
execute one command, download artifacts, save a run manifest, and destroy the temporary session
while preserving logs.

See [Remote Runner API Contract](docs/reference/REMOTE_RUNNER_API.md) for the target contract.

## Current Prototype Usage

Until the CLI is renamed and the machine/session contract is rebuilt, the working executable is
still `seed-runner`.

### Prerequisites

- Python 3.8+
- SSH access to the target VM with key authentication
- Current prototype backend dependencies on the target VM: `tmux` and `sshfs`

### Installation

```bash
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -e ".[dev]"
```

### Configuration

```bash
cp .env.machines.example .env.machines
```

Edit `.env.machines` with the current prototype's machine settings. This is a legacy prototype
format; the target MVP should move toward a local Remote Runner state directory such as
`~/.remote-runner/`.

### Basic Prototype Workflow

Create a workspace under `runs/` so prototype outputs do not mix with source files:

```bash
mkdir -p runs/exp-web-01
cd runs/exp-web-01
```

```bash
seed-runner mount create \
  --machine vm-seed-01 \
  --local-dir ./workspace

seed-runner session create \
  --machine vm-seed-01 \
  --mount-id mnt_20260407_001 \
  --name exp-web-01

seed-runner session exec \
  --session sess_20260407_001 \
  --cmd "make"

seed-runner session status --session sess_20260407_001
seed-runner session destroy --session sess_20260407_001
seed-runner mount destroy --mount-id mnt_20260407_001
```

In the prototype, `--local-dir` is the full sshfs sync root. The tool reserves
`<local-dir>/artifacts/` for command logs and synced outputs. This mount-first model is legacy
implementation detail, not the desired long-term public API.

## Documentation

- [Overview](docs/overview.md) - product positioning and relationship to the SEEDRunner prototype
- [Requirements](REQUIREMENTS.md) - MVP requirements and acceptance criteria
- [Remote Runner API Contract](docs/reference/REMOTE_RUNNER_API.md) - target agent-facing CLI
- [Launch Acceptance Suite](docs/testing/remote-runner-launch-acceptance.md) - reusable pre-release validation
- [Legacy seed-runner API](docs/reference/SEED_RUNNER_API.md) - current prototype CLI reference

## Development

```bash
python3 -m pytest tests/
```

Run the reusable Remote Runner launch acceptance suite before release:

```bash
python3 -m pytest tests/test_remote_runner_launch_suite.py -q
```

Run the opt-in VM-backed integration test only when a real test machine is configured:

```bash
SEED_RUNNER_RUN_REAL_VM_TESTS=1 python3 -m pytest tests/test_real_vm_integration.py -q
```

Run the opt-in Remote Runner integration test only when a real Remote Runner machine and a safe
remote test directory are configured:

```bash
REMOTE_RUNNER_RUN_REAL_TESTS=1 \
  REMOTE_RUNNER_REAL_MACHINE=<machine_id> \
  REMOTE_RUNNER_REAL_TEST_CWD=<remote_cwd> \
  python3 -m pytest tests/test_remote_runner_real_integration.py -q
```

Remote Runner target implementation modules now live under `remote_runner`. The `remote-runner`
console script points to `remote_runner.cli:main`; legacy `seed_runner.remote_*` modules are
compatibility wrappers that re-export the target implementation. The older `seed-runner` prototype
CLI remains available for legacy mount/session workflows.

## License

MIT
