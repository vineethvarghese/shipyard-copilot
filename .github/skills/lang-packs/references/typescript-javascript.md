# TypeScript and JavaScript pack

Applies to: `.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs`, `.cjs` · Loaded by: code-review, security-review, implementer, verifier

## Idioms to follow

- `const` by default, `let` when reassigned, never `var`.
- `===` and `!==`; `== null` is the one accepted loose check (matches `null` and `undefined`).
- `??` for defaults when `0`, `""` or `false` are valid values; `||` treats them as missing.
- Optional chaining `?.` for genuinely optional paths, not to silence a value that must exist.
- TypeScript: `strict` on; `unknown` over `any` at boundaries, then narrow; avoid `as` casts that skip checks.
- Model variants with discriminated unions; make `switch` exhaustive with a `never` check.
- Validate external data (HTTP bodies, env, files) at the boundary with a schema; types alone do not check runtime data.
- `async`/`await` over raw `.then` chains; ES modules over CommonJS unless the repository uses CommonJS.
- `readonly` and `as const` for data that should not change.

## Error-handling conventions

- Throw `Error` objects (or subclasses), never strings; pass `{ cause }` when wrapping.
- In `catch (e)`, `e` is `unknown`; narrow before reading `.message`.
- Every promise is awaited, returned, or explicitly handled. A floating promise loses its error; in Node an
  unhandled rejection ends the process by default.
- `try` around `return promise` without `await` does not catch its rejection — use `return await` there.
- `Promise.all` rejects on the first failure and leaves others running; use `allSettled` when you need all results.
- Express-style handlers: async errors need the framework's async support or an explicit `next(err)`.

## Concurrency model and pitfalls

- One thread runs an event loop. Anything synchronous and slow blocks every request: `fs.*Sync`, large
  `JSON.parse`/`stringify`, heavy regex, crypto in a loop. Offload to `worker_threads` or stream.
- `array.forEach(async ...)` does not wait; use `for...of` with `await`, or `Promise.all` over `map`.
- Sequential `await` in a loop when calls are independent wastes latency; unbounded `Promise.all` over thousands
  of items exhausts sockets or memory — use a concurrency limit.
- State can change across an `await`: check-then-act on shared data is a race even on one thread.
- Module-level mutable state is shared by every request in a server process.
- Timers, listeners and intervals that are never cleared leak memory and keep the process alive.
- Abort work with `AbortController`/`AbortSignal`; pass the signal through to `fetch` and child calls.

## Performance traps

- Spreading into an accumulator inside `reduce` (`[...acc, x]`, `{...acc, k}`) is O(n²). Evidence: input sizes.
- Repeated `array.find`/`includes` inside a loop — build a `Map`/`Set`. Evidence: a micro-benchmark.
- Catastrophic regex backtracking on user input. Evidence: a crafted long input timed in a test.
- UI: unstable props (inline objects/functions) and missing `key`s causing re-renders; heavy work in render.
  Evidence: the framework's profiler or render counts in a test.
- Importing a whole library for one function; check bundle size with the repository's bundle analyser.
- Evidence tools: `node --cpu-prof`, `node --heap-prof`, browser devtools performance panel, `vitest bench` or
  `tinybench`.

## Security sinks and footguns

- `eval`, `new Function`, `setTimeout(string)`, `vm` (not a sandbox) with untrusted input (CWE-95).
- `innerHTML`, `outerHTML`, `document.write`, `dangerouslySetInnerHTML`, `v-html` with user data (CWE-79).
- `child_process.exec`/`execSync` with interpolated strings (CWE-78); use `execFile`/`spawn` with an args array.
- Deep merge or `Object.assign` of user JSON into objects; keys like `__proto__`, `constructor` (CWE-1321).
- SQL built with template literals (CWE-89); use parameters or the query builder's binding.
- `path.join(root, userPath)` without a containment check after `path.resolve` (CWE-22).
- `fetch(userSuppliedUrl)` from a server (CWE-918).
- `res.redirect(req.query.next)` without an allowlist (CWE-601).
- `Math.random()` for tokens or IDs that must be unguessable (CWE-338); use `crypto.randomUUID`/`getRandomValues`.
- JWT decode without verify, or accepting `alg: none` (CWE-347).
- `postMessage` handlers that do not check `event.origin` (CWE-346).
- Regex built from user input or vulnerable patterns on user input (CWE-1333).
- `NODE_TLS_REJECT_UNAUTHORIZED=0` or `rejectUnauthorized: false` (CWE-295).

## Testing conventions

- Frameworks: Vitest, Jest, Mocha, the built-in `node:test`; Playwright or Cypress for browser end-to-end.
- Canonical commands: `npm test` (or `pnpm test` / `yarn test`), `npx vitest run`, `npx jest`, `node --test`.
- Run type checking as its own step when configured: `npx tsc --noEmit`.
- Use fake timers instead of real waits; mock the network at the HTTP layer, not by patching internals.
- `await expect(promise).rejects...` — a missing `await` makes the test pass vacuously.
- Snapshot tests only for stable, reviewed output; a large updated snapshot is not evidence.

## Readability conventions

- Formatter: Prettier (or Biome). Linter: ESLint with `typescript-eslint` (or Biome).
- `camelCase` values and functions, `PascalCase` types, classes and components, `UPPER_SNAKE` for true constants.

## Things NOT to flag

- Semicolons, quotes, trailing commas, wrapping — the formatter owns them.
- `== null` as a combined null/undefined check; `!!value` to coerce to boolean.
- Non-null assertion `!` right after a check the compiler cannot see, when the reason is obvious or commented.
- `void promise` for deliberate fire-and-forget with a comment and an attached `.catch`.
- `_`-prefixed unused parameters; IIFEs at module top level; `as const` objects in place of enums.
