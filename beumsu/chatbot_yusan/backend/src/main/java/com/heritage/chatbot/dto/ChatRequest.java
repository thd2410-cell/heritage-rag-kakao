package com.heritage.chatbot.dto;

import jakarta.validation.constraints.NotBlank;
import java.util.Map;

public record ChatRequest(
    String sessionId,
    @NotBlank String query,
    String language,
    String audience,
    Map<String, Object> location,
    Map<String, Object> options
) {}
