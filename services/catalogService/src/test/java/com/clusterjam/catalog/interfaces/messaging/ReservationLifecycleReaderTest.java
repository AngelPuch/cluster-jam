package com.clusterjam.catalog.interfaces.messaging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.clusterjam.catalog.application.reservations.InvalidReservationMessage;
import com.clusterjam.catalog.application.reservations.ReservationMessages;
import com.clusterjam.catalog.application.reservations.ReservationMessages.Command;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConfirmCommand;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConfirmData;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConsumeCommand;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConsumeData;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ReleaseCommand;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ReleaseData;
import jakarta.validation.Validation;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class ReservationLifecycleReaderTest {

    @Test
    void readsTheThreeLifecycleCommandsWithNormalDtos() {
        try (var factory = Validation.buildDefaultValidatorFactory()) {
            var mapper = new JsonMapper();
            var reader = new ReservationMessageReader(mapper, factory.getValidator());
            UUID order = UUID.randomUUID();
            UUID reservation = UUID.randomUUID();
            List<Command> commands = List.of(
                new ConfirmCommand(UUID.randomUUID(), ReservationMessages.CONFIRM, order, Instant.now(),
                    new ConfirmData(reservation, UUID.randomUUID())),
                new ReleaseCommand(UUID.randomUUID(), ReservationMessages.RELEASE, order, Instant.now(),
                    new ReleaseData(reservation, "Customer cancellation")),
                new ConsumeCommand(UUID.randomUUID(), ReservationMessages.CONSUME, order, Instant.now(),
                    new ConsumeData(reservation)));
            for (Command command : commands) {
                assertEquals(command, reader.readCommand(mapper.writeValueAsBytes(command), command.type()));
            }
            var missingPayment = new ConfirmCommand(UUID.randomUUID(), ReservationMessages.CONFIRM, order,
                Instant.now(), new ConfirmData(reservation, null));
            assertThrows(InvalidReservationMessage.class,
                () -> reader.readCommand(mapper.writeValueAsBytes(missingPayment), missingPayment.type()));
            var blankReason = new ReleaseCommand(UUID.randomUUID(), ReservationMessages.RELEASE, order,
                Instant.now(), new ReleaseData(reservation, " "));
            assertThrows(InvalidReservationMessage.class,
                () -> reader.readCommand(mapper.writeValueAsBytes(blankReason), blankReason.type()));
            assertThrows(InvalidReservationMessage.class,
                () -> reader.readCommand(mapper.writeValueAsBytes(commands.getFirst()), ReservationMessages.CONSUME));
        }
    }
}
