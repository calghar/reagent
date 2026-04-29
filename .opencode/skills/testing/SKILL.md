---
name: testing
description: >-
  Testing standards for the dtguard project (Go). Load when writing or reviewing
  tests under cmd/ or internal/.
---
# Testing Standards for dtguard

## Layout

- Tests live next to the package they test, named `<thing>_test.go`.
- Integration tests that span packages live under `tests/` at the
  repo root and use the `_test` package suffix.
- Use the standard `testing` package. No external assertion
  libraries unless they earn it.

## Table-driven tests

The default pattern. One `t.Run(name, ...)` per case.

```go
func TestContentHash(t *testing.T) {
	tests := []struct {
		name string
		in   []byte
		want string
	}{
		{"empty", nil, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
		{"hello", []byte("hello"), "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ContentHash(tt.in)
			if got != tt.want {
				t.Errorf("ContentHash(%q) = %q, want %q", tt.in, got, tt.want)
			}
		})
	}
}
```

## Cobra CLI tests

Test commands via `cmd.SetArgs([...])` + captured `bytes.Buffer`,
not via `os/exec`.

```go
func TestVersionCommand(t *testing.T) {
	var buf bytes.Buffer
	root := cli.NewRootCmd()
	root.SetOut(&buf)
	root.SetArgs([]string{"version"})
	if err := root.Execute(); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(buf.String(), "dtguard") {
		t.Errorf("unexpected output: %q", buf.String())
	}
}
```

## Filesystem and SQLite

- Use `t.TempDir()` for any path under test. Never write to `$HOME`.
- For SQLite, open against `t.TempDir()/test.db`. Don't mock the
  driver.

```go
func TestStorageOpen(t *testing.T) {
	path := filepath.Join(t.TempDir(), "test.db")
	db, err := storage.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	// ...
}
```

## HTTP / DT API

- Use `httptest.NewServer` to fake the DT endpoint. Inject the URL
  into the client under test.
- Don't mock `*http.Client`; mock the server it talks to.

## What to test

- Happy path.
- Each documented error path (boundary inputs, malformed YAML,
  missing required fields, signature mismatch).
- Round-trip: marshal -> unmarshal -> equal.
- Regressions: when fixing a bug, add the test that would have caught
  it.

## What NOT to test

- Stdlib behavior (`crypto/ed25519`, `encoding/json`, `net/http`).
- Cobra's own machinery — test our handlers, not theirs.
- Trivial getters/setters.
- Things that are easier to verify by reading the code than by
  asserting in a test.

## Quality bar

- `go test ./...` passes.
- Tests run in < 5 s for the unit suite.
- Use `t.Parallel()` where the test doesn't share state.
- No `time.Sleep` in tests — use `context.WithDeadline` or fake clocks.
- Coverage is a reporting metric, not a gate. Target meaningful
  paths, not lines.

## Useful flags

```bash
go test ./... -run TestName -v          # one test, verbose
go test ./... -race                      # race detector
go test ./... -count=1                   # bypass cache
go test ./internal/scanner -coverprofile=cover.out
go tool cover -html=cover.out
```
