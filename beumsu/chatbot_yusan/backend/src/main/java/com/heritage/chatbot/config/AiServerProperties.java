package com.heritage.chatbot.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "heritage.ai-server")
public record AiServerProperties(String baseUrl) {}
