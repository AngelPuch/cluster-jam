package com.clusterjam.catalog.interfaces.messaging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.clusterjam.catalog.application.reservations.InvalidReservationMessage;
import com.clusterjam.catalog.application.reservations.ReservationMessages;
import com.clusterjam.catalog.application.reservations.ReservationMessages.CreatedData;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ResultMessage;
import jakarta.validation.Validation;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class ReservationMessageReaderTest {

    @Test
    void acceptsOrdinarySerializationAndRejectsInvalidDomainData() {
        try (var factory = Validation.buildDefaultValidatorFactory()) {
            var reader = new ReservationMessageReader(new JsonMapper(), factory.getValidator());
            for (String timestamp : List.of("2026-11-25T18:00:00Z",
                "2026-11-25T18:00:00.12Z", "2026-11-25T18:00:00.123456Z")) {
                var command = reader.read(body(timestamp, 2), ReservationMessages.RESERVE);
                assertEquals(Instant.parse(timestamp), command.occurredAt());
                assertEquals(UUID.fromString("AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"), command.messageId());
            }
            assertThrows(InvalidReservationMessage.class,
                () -> reader.read(body("2026-11-25T18:00:00Z", 0), ReservationMessages.RESERVE));
            var mapper = new JsonMapper();
            Instant now = Instant.parse("2026-11-25T18:00:00Z");
            var result = new ResultMessage(UUID.randomUUID(), ReservationMessages.CREATED, UUID.randomUUID(), now,
                new CreatedData(UUID.randomUUID(), now.plusSeconds(900)));
            var output = mapper.readTree(mapper.writeValueAsString(result));
            assertEquals(now.toString(), output.get("occurredAt").asString());
            assertEquals(now.plusSeconds(900).toString(), output.get("data").get("expiresAt").asString());
            assertThrows(InvalidReservationMessage.class,
                () -> reader.read("{}".getBytes(StandardCharsets.UTF_8), ReservationMessages.RESERVE));
            assertThrows(InvalidReservationMessage.class,
                () -> reader.read(body("2026-11-25T18:00:00Z", 2), "unknown.command"));
        }
    }

    private byte[] body(String timestamp, int quantity) {
        return """
            {
              "messageId":"AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA",
              "type":"cmd.catalog.reserve-stock.v1",
              "orderId":"00000000-0000-4000-8000-000000000001",
              "occurredAt":"%s",
              "data":{
                "quoteValidUntil":"2026-11-25T18:05:00Z",
                "lines":[{
                  "variantId":"00000000-0000-4000-8000-000000000004",
                  "quantity":%d,
                  "expectedBasePriceCents":19900
                }]
              }
            }
            """.formatted(timestamp, quantity).getBytes(StandardCharsets.UTF_8);
    }
}
