package com.clusterjam.catalog.interfaces.messaging;

import java.util.HashSet;
import java.util.UUID;

import com.clusterjam.catalog.application.reservations.InvalidReservationMessage;
import com.clusterjam.catalog.application.reservations.ReservationMessages;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ReserveCommand;
import jakarta.validation.Validator;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

@Component
public final class ReservationMessageReader {

    private final JsonMapper json;
    private final Validator validator;

    public ReservationMessageReader(JsonMapper json, Validator validator) {
        this.json = json;
        this.validator = validator;
    }

    public ReserveCommand read(byte[] body, String routingKey) {
        try {
            ReserveCommand command = json.readValue(body, ReserveCommand.class);
            if (command == null || !validator.validate(command).isEmpty()
                || !ReservationMessages.RESERVE.equals(command.type()) || !command.type().equals(routingKey)) {
                throw new InvalidReservationMessage();
            }
            var variants = new HashSet<UUID>();
            for (var line : command.data().lines()) {
                if (!variants.add(line.variantId())) {
                    throw new InvalidReservationMessage();
                }
            }
            return command;
        } catch (InvalidReservationMessage invalid) {
            throw invalid;
        } catch (RuntimeException malformed) {
            throw new InvalidReservationMessage();
        }
    }
}
