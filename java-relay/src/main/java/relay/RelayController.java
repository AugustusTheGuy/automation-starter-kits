package relay;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RelayController {
    static final int MAX_BODY = 1_000_000;
    private final ObjectMapper mapper = new ObjectMapper();
    private final Path out;
    private final Path kill;

    public RelayController(@Value("${relay.out}") String out, @Value("${relay.kill}") String kill) {
        this.out = Path.of(out);
        this.kill = Path.of(kill);
    }

    @GetMapping({"/", "/health"})
    public ResponseEntity<Map<String, Object>> health() {
        if (Files.exists(kill)) return killed();
        return ResponseEntity.ok(Map.of("ok", true));
    }

    @PostMapping("/")
    public ResponseEntity<Map<String, Object>> post(HttpServletRequest request) {
        if (Files.exists(kill)) return killed();
        long n;
        String header = request.getHeader("Content-Length");
        if (header == null || header.isBlank()) {
            n = 0;
        } else {
            try {
                n = Long.parseLong(header.trim());
            } catch (NumberFormatException e) {
                return error(400, "bad content-length");
            }
        }
        if (n < 0 || n > MAX_BODY) return error(413, "body too large");
        try {
            byte[] raw = n == 0 ? "{}".getBytes(StandardCharsets.UTF_8) : request.getInputStream().readNBytes((int) n);
            JsonNode node = mapper.readTree(raw.length == 0 ? "{}".getBytes(StandardCharsets.UTF_8) : raw);
            if (!(node instanceof ObjectNode obj)) return error(400, "json object required");
            JsonNode text = obj.get("text");
            String echo = text == null || text.isNull() ? "" : text.isValueNode() ? text.asText() : text.toString();
            if (echo.length() > 200) echo = echo.substring(0, 200);
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("ok", true);
            row.put("echo", echo);
            append(row);
            return ResponseEntity.ok(row);
        } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
            return error(400, "invalid json");
        } catch (Exception e) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("ok", false);
            row.put("error", e.getMessage() == null ? "write failed" : e.getMessage());
            try {
                append(row);
            } catch (Exception ignored) {
                // The sheet itself could not be written.
            }
            return error(500, String.valueOf(row.get("error")));
        }
    }

    private void append(Map<String, Object> row) throws java.io.IOException {
        Files.writeString(
                out,
                mapper.writeValueAsString(row) + "\n",
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.APPEND);
    }

    private static ResponseEntity<Map<String, Object>> killed() {
        return error(503, "killed");
    }

    private static ResponseEntity<Map<String, Object>> error(int code, String message) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("ok", false);
        body.put("error", message);
        return ResponseEntity.status(code).body(body);
    }
}
