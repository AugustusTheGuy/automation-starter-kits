# java-relay

Spring Boot 3 port of `webhook-relay/glue.py`. `POST /` checks the body size (`MAX_BODY = 1000000`), requires a JSON object, and appends one JSON line. `GET /` and `GET /health` return `{"ok": true}`. `GET /actuator/health` is Spring Actuator. A `KILL` file makes `/` and `/health` return 503. `glue.py` does not check that file; this port adds the guard named in the build plan.

Default listen port is 8080, not 8787.

## Test

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
export PATH="$JAVA_HOME/bin:$PATH"
mvn test
```

The image is described in `Dockerfile`. It has not been built.

## Verified

2026-11-12, from this directory, Java 21.0.13.0.3:

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
mvn -Dmaven.repo.local=/Volumes/NoxSSD/Codex/m2 test
```

Tests run: 2, Failures: 0, Errors: 0, Skipped: 0. BUILD SUCCESS. Exit 0. The image was not built.
