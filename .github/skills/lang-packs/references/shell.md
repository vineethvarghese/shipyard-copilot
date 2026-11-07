# Shell pack

Applies to: `.sh`, `.bash`, files with a `sh`/`bash` shebang, `run:` blocks in CI files · Loaded by: code-review, security-review, implementer, verifier

Check the shebang first: POSIX `sh` and `bash` differ, and bash-only syntax in an `sh` script is a real bug.

## Idioms to follow

- Shebang `#!/usr/bin/env bash` (or `#!/bin/sh` for portable scripts) and strict mode `set -euo pipefail` in bash.
- Quote every expansion: `"$var"`, `"$(cmd)"`, `"${arr[@]}"`; pass arguments on with `"$@"`.
- `$(...)` over backticks; `[[ ... ]]` in bash; `(( ... ))` for arithmetic.
- `local` for function variables; a `main` function called at the end of the script.
- Build argument lists in arrays, not in strings.
- Temp files with `mktemp`, cleaned up by `trap 'rm -rf "$tmp"' EXIT`.
- `printf '%s\n' "$x"` over `echo` for arbitrary data; `--` before user-supplied file names.
- `command -v tool` to test for a tool; `readonly` for constants; `${VAR:?message}` for required variables.
- `while IFS= read -r line` to read lines unchanged.

## Error-handling conventions

- `set -e` does not fire inside `if`/`while` conditions, in `&&`/`||` lists except the last command, or in
  functions called from those contexts. Check important commands explicitly.
- `local x=$(cmd)` hides `cmd`'s exit status; declare first, then assign.
- Without `pipefail`, a pipeline's status is only the last command's.
- Send errors to stderr (`>&2`) and exit non-zero with a clear message.
- `|| true` to ignore a failure needs a comment saying why.

## Concurrency model and pitfalls

- Background jobs (`&`) need `wait "$pid"` per job to collect each exit status; a bare `wait` drops them.
- Two runs of the same script race on shared files; serialise with `flock` where needed.
- Fixed temp file names in `/tmp` race with other users and runs.
- Traps and cleanup must handle `INT` and `TERM` as well as normal exit.
- `xargs -P` and parallel loops interleave output; write per-job logs.

## Performance traps

- Spawning processes per line in a loop (`$(echo ...)`, `cat | grep`, `sed` per item); use one `awk`/`sed` pass
  or shell built-ins. Evidence: `time` on realistic input, or `hyperfine`.
- `while read` loops over large files are slow; use stream tools.
- `find ... -exec cmd {} \;` runs once per file; `-exec cmd {} +` batches.
- Unneeded subshells and pipelines in tight loops.

## Security sinks and footguns

- Unquoted variables split and glob, letting input add arguments or match files (CWE-88, CWE-78).
- `eval` and `sh -c "$input"` (CWE-78).
- `curl ... | sh` or running downloaded code without a checksum or signature (CWE-494).
- Predictable temp files (CWE-377); use `mktemp`.
- Secrets passed as command-line arguments are visible to other processes (CWE-214); use files or stdin.
- `set -x` tracing that prints secrets into logs (CWE-532).
- `rm -rf "$dir/"` when `$dir` may be empty; use `"${dir:?}"`.
- Relying on `PATH` in privileged scripts (CWE-426); set `PATH` or use absolute paths.
- File names starting with `-` read as options (CWE-88); use `--` or `./`.
- `chmod 777` or world-writable files (CWE-732).
- Parsing `ls` output; use globs or `find -print0` with `xargs -0`.

## Testing conventions

- Frameworks: `bats` (Bash Automated Testing System), `shunit2`.
- Canonical commands: `bats test/` (or the repository's path), `shellcheck` on every script as a gate.
- Syntax check without running: `bash -n script.sh`.
- Run scripts in a temp directory with stubbed commands on `PATH`; never against real systems.

## Readability conventions

- Linter: `shellcheck`. Formatter: `shfmt`.
- `UPPER_CASE` for exported and environment variables, `lower_case` for locals.
- Long options (`--force`) over short ones in scripts for readability.

## Things NOT to flag

- `[ ]` in POSIX `sh` scripts (where `[[ ]]` is not available).
- `: "${VAR:=default}"` to set defaults; `$(( ))` arithmetic.
- `|| true` with a reason; heredocs for multi-line text.
- Deliberate unquoted expansion with a `# shellcheck disable=SC2086` and a reason.
- Indentation and spacing — `shfmt` owns them.
