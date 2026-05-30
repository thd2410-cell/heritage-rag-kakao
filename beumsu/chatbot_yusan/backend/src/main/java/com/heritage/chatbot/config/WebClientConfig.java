package com.heritage.chatbot.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableConfigurationProperties(AiServerProperties.class)
public class WebClientConfig {
  @Bean
  WebClient aiServerWebClient(AiServerProperties properties) {
    return WebClient.builder().baseUrl(properties.baseUrl()).build();
  }
}
