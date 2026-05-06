# miniserv_tester

A small black-box test runner for the 42 **mini_serv** exam project.

It scans your source file for forbidden functions, compiles it with `gcc`,
spawns the resulting binary on a free local port, then opens real TCP
connections and verifies the server's behavior against the subject.

## Requirements

- Linux (or WSL)
- `python3`
- `gcc`

## Usage

```sh
python3 miniserv_tester.py [source.c] [-v|--verbose]
```

- `source.c` — path to the C file to test. Defaults to `mini_serv.c`.
- `-v` / `--verbose` — also print section headers and extra debug info.

Examples:

```sh
python3 miniserv_tester.py                  # tests mini_serv.c
python3 miniserv_tester.py oefen2.c         # tests oefen2.c
python3 miniserv_tester.py mini_serv.c -v   # verbose mode
```

The tester compiles the source to `./mini_serv` in the current directory
and picks a free port in the range 8888–9999 automatically.

## What it checks

1. **Forbidden functions** — scans for any function call that is not in
   the subject's allowed list. The check is regex-based (so it can have
   false positives on unusual macros), and it now **warns and continues**
   instead of aborting, so you still see the runtime test results.
2. **Compilation** — must succeed with plain `gcc`.
3. **Arrival message** — `server: client N just arrived\n` is broadcast.
4. **Split `recv`** — a message sent in two `send()` calls is reassembled
   into a single `client N: ...` line.
5. **Multiple `\n`** — `a\nb\nc\n` produces three separate `client N:`
   lines.
6. **`\x04` (Ctrl+D)** — does not terminate or corrupt the message.
7. **Empty lines** — `\n\n\n` does not crash the server.
8. **Large messages** — 100 KB, 200 KB, and 500 KB payloads are
   delivered intact.
9. **Disconnect** — `server: client N just left\n` is broadcast.
10. **ID cycling** — IDs keep incrementing across connect/disconnect
    cycles (no reuse).

## Output legend

- ✅ — test passed
- ❌ — test failed (exits non-zero)
- ⚠ — non-fatal warning (e.g. forbidden functions detected)

## Notes

- The tester always binds to `127.0.0.1`.
- It registers an `atexit` cleanup that kills the server process and
  closes all client sockets, so a crashed test won't leave a dangling
  server behind.
- The forbidden-function scanner is intentionally lenient (warn-only)
  because the real 42 moulinette is the source of truth — this script
  is just for fast local iteration.
