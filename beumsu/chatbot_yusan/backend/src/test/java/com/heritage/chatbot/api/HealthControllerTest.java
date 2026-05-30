package com.heritage.chatbot.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.heritage.chatbot.HeritageBackendApplication;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(classes = HeritageBackendApplication.class)
class HealthControllerTest {
  @Test
  void contextLoads() {
    assertThat(true).isTrue();
  }
}
