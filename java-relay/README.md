# java-relay

Spring Boot 3 port of `webhook-relay/glue.py`. `POST /` checks the body size (`MAX_BODY = 1000000`), requires a JSON object, and appends one JSON line. `GET /` and `GET /health` return `{"ok": true}`. `GET /actuator/health` is Spring Actuator. A `KILL` file makes `/` and `/health` return 503. `glue.py` does not check that file; this port adds the guard named in the build plan.

Default listen port is 8080, not 8787.

## Test

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
export PATH="$JAVA_HOME/bin:$PATH"
mvn test
```

The image is described in `Dockerfile`. The local tag is `java-relay:local`. It has not been pushed to a registry.

## Verified

2026-11-12, from this directory, Java 21.0.13.0.3:

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
mvn -Dmaven.repo.local=/Volumes/NoxSSD/Codex/m2 test
```

Tests run: 2, Failures: 0, Errors: 0, Skipped: 0. BUILD SUCCESS. Exit 0.

2026-11-13: `mvn package` exit 0. OrbStack built `java-relay:local` (`dc496c43b9ad`). `docker run -p 127.0.0.1:8080:8080` then `curl` : `GET /health` returned `{"ok":true}` HTTP 200, `GET /actuator/health` returned `{"status":"UP"}` HTTP 200, and `POST /` with `{"text":"ping"}` returned `{"ok":true,"echo":"ping"}` HTTP 200. The container was stopped and removed. The image was not pushed. There is no registry login on this Mac.
