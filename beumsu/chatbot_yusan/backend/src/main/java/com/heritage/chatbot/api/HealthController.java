package com.heritage.chatbot.api;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class HealthController {
  private final WebClient aiServerWebClient;

  public HealthController(WebClient aiServerWebClient) {
    this.aiServerWebClient = aiServerWebClient;
  }

  @GetMapping("/health")
  public Mono<Map<String, Object>> health() {
    return aiServerWebClient.get()
        .uri("/health")
        .retrieve()
        .bodyToMono(Map.class)
        .map(ai -> Map.of("status", "ok", "backend", "ok", "aiServer", ai))
        .onErrorReturn(Map.of("status", "degraded", "backend", "ok", "aiServer", "unavailable"));
  }
}
