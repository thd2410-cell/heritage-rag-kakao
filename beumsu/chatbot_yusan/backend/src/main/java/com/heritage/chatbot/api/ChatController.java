package com.heritage.chatbot.api;

import com.heritage.chatbot.dto.ChatRequest;
import jakarta.validation.Valid;
import java.util.HashMap;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ChatController {
  private final WebClient aiServerWebClient;

  public ChatController(WebClient aiServerWebClient) {
    this.aiServerWebClient = aiServerWebClient;
  }

  @PostMapping(value = "/chat", produces = MediaType.APPLICATION_JSON_VALUE)
  public Mono<Map> chat(@Valid @RequestBody ChatRequest request) {
    Map<String, Object> payload = new HashMap<>();
    payload.put("session_id", request.sessionId());
    payload.put("query", request.query());
    payload.put("language", request.language() == null ? "auto" : request.language());
    payload.put("audience", request.audience() == null ? "general" : request.audience());
    payload.put("location", request.location());
    payload.put("options", request.options() == null ? Map.of("include_citations", true, "stream", false, "tts_ready", false) : request.options());
    return aiServerWebClient.post()
        .uri("/chat")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(payload)
        .retrieve()
        .bodyToMono(Map.class);
  }

  @PostMapping("/ingest/sample")
  public Mono<Map> ingestSample() {
    return aiServerWebClient.post().uri("/ingest/sample").retrieve().bodyToMono(Map.class);
  }

  @PostMapping("/ingest/official")
  public Mono<Map> ingestOfficial(@RequestBody(required = false) Map<String, Object> request) {
    Map<String, Object> payload = request == null ? Map.of() : request;
    return aiServerWebClient.post()
        .uri("/ingest/official")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(payload)
        .retrieve()
        .bodyToMono(Map.class);
  }

  @PostMapping("/ingest/khs/images")
  public Mono<Map> ingestKhsImages(@RequestBody Map<String, Object> request) {
    return aiServerWebClient.post()
        .uri("/ingest/khs/images")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(request)
        .retrieve()
        .bodyToMono(Map.class);
  }

  @PostMapping("/ingest/khs/bulk")
  public Mono<Map> ingestKhsBulk(@RequestBody Map<String, Object> request) {
    return aiServerWebClient.post()
        .uri("/ingest/khs/bulk")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(request)
        .retrieve()
        .bodyToMono(Map.class);
  }

  @PostMapping("/ingest/khs/text-jobs")
  public Mono<Map> startKhsTextJob(@RequestBody Map<String, Object> request) {
    return aiServerWebClient.post()
        .uri("/ingest/khs/text-jobs")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(request)
        .retrieve()
        .bodyToMono(Map.class);
  }

  @GetMapping("/ingest/khs/text-jobs")
  public Mono<Map[]> listKhsTextJobs() {
    return aiServerWebClient.get()
        .uri("/ingest/khs/text-jobs")
        .retrieve()
        .bodyToMono(Map[].class);
  }

  @GetMapping("/ingest/khs/text-jobs/{jobId}")
  public Mono<Map> getKhsTextJob(@org.springframework.web.bind.annotation.PathVariable String jobId) {
    return aiServerWebClient.get()
        .uri("/ingest/khs/text-jobs/{jobId}", jobId)
        .retrieve()
        .bodyToMono(Map.class);
  }

  @GetMapping("/ingest/embeddings/status")
  public Mono<Map> embeddingStatus() {
    return aiServerWebClient.get()
        .uri("/ingest/embeddings/status")
        .retrieve()
        .bodyToMono(Map.class);
  }

  @PostMapping("/ingest/embeddings/rebuild")
  public Mono<Map> rebuildEmbeddings(@RequestBody(required = false) Map<String, Object> request) {
    Map<String, Object> payload = request == null ? Map.of() : request;
    return aiServerWebClient.post()
        .uri("/ingest/embeddings/rebuild")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(payload)
        .retrieve()
        .bodyToMono(Map.class);
  }

  @GetMapping("/ingest/embeddings/jobs")
  public Mono<Map[]> listEmbeddingJobs() {
    return aiServerWebClient.get()
        .uri("/ingest/embeddings/jobs")
        .retrieve()
        .bodyToMono(Map[].class);
  }

  @GetMapping("/ingest/embeddings/jobs/{jobId}")
  public Mono<Map> getEmbeddingJob(@org.springframework.web.bind.annotation.PathVariable String jobId) {
    return aiServerWebClient.get()
        .uri("/ingest/embeddings/jobs/{jobId}", jobId)
        .retrieve()
        .bodyToMono(Map.class);
  }

  @PostMapping("/eval/run")
  public Mono<Map> runEval() {
    return aiServerWebClient.post().uri("/eval/run").retrieve().bodyToMono(Map.class);
  }

  @GetMapping("/admin/entities")
  public Mono<Map[]> entities() {
    return aiServerWebClient.get().uri("/admin/entities").retrieve().bodyToMono(Map[].class);
  }
}
