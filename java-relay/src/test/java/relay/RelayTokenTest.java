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
import org.springframework.http.HttpHeaders;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class RelayTokenTest {
    private static Path dir;

    @DynamicPropertySource
    static void props(DynamicPropertyRegistry registry) throws Exception {
        dir = Files.createTempDirectory("java-relay-token");
        registry.add("relay.out", () -> dir.resolve("runs.jsonl").toString());
        registry.add("relay.kill", () -> dir.resolve("KILL").toString());
        registry.add("relay.token", () -> "test-token");
    }

    @Autowired
    MockMvc mvc;

    @Test
    void healthStaysOpenAndPostRequiresBearer() throws Exception {
        mvc.perform(get("/health")).andExpect(status().isOk()).andExpect(jsonPath("$.ok").value(true));
        mvc.perform(post("/").contentType("application/json").content("{\"text\":\"nope\"}"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer wrong")
                        .contentType("application/json")
                        .content("{\"text\":\"nope\"}"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer test-token")
                        .contentType("application/json")
                        .content("{\"text\":\"ok\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.echo").value("ok"));
    }
}
