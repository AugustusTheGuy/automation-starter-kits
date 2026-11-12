package relay;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class RelayControllerTest {
    private static Path dir;

    @DynamicPropertySource
    static void props(DynamicPropertyRegistry registry) throws Exception {
        dir = Files.createTempDirectory("java-relay");
        registry.add("relay.out", () -> dir.resolve("runs.jsonl").toString());
        registry.add("relay.kill", () -> dir.resolve("KILL").toString());
    }

    @Autowired
    MockMvc mvc;

    @Test
    void healthAndEcho() throws Exception {
        mvc.perform(get("/health")).andExpect(status().isOk()).andExpect(jsonPath("$.ok").value(true));
        mvc.perform(get("/actuator/health")).andExpect(status().isOk());
        mvc.perform(post("/").contentType("application/json").content("{\"text\":\"hi\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.echo").value("hi"));
        String line = Files.readString(dir.resolve("runs.jsonl")).lines().findFirst().orElse("");
        org.junit.jupiter.api.Assertions.assertTrue(line.contains("\"echo\":\"hi\""));
    }

    @Test
    void rejectsBadJsonOversizedBodyAndKillFile() throws Exception {
        mvc.perform(post("/").contentType("application/json").content("not json"))
                .andExpect(status().isBadRequest());
        mvc.perform(post("/").contentType("application/json").content("[1]"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("json object required"));
        mvc.perform(post("/").contentType("application/json").content("x".repeat(RelayController.MAX_BODY + 1)))
                .andExpect(status().isPayloadTooLarge());
        Files.writeString(dir.resolve("KILL"), "1");
        mvc.perform(get("/health")).andExpect(status().isServiceUnavailable());
        Files.delete(dir.resolve("KILL"));
    }
}
