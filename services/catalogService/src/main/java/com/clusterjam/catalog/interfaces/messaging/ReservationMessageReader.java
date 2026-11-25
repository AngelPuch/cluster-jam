package com.clusterjam.catalog.interfaces.messaging;

import java.util.HashSet;
import java.util.UUID;

import com.clusterjam.catalog.application.reservations.InvalidReservationMessage;
import com.clusterjam.catalog.application.reservations.ReservationMessages;
import com.clusterjam.catalog.application.reservations.ReservationMessages.Command;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConfirmCommand;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ConsumeCommand;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ReleaseCommand;
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
        Command command = readCommand(body, routingKey);
        if (command instanceof ReserveCommand reserve) {
            return reserve;
        }
        throw new InvalidReservationMessage();
    }

    public Command readCommand(byte[] body, String routingKey) {
        try {
            Class<? extends Command> target = switch (routingKey) {
                case ReservationMessages.RESERVE -> ReserveCommand.class;
                case ReservationMessages.CONFIRM -> ConfirmCommand.class;
                case ReservationMessages.RELEASE -> ReleaseCommand.class;
                case ReservationMessages.CONSUME -> ConsumeCommand.class;
                default -> throw new InvalidReservationMessage();
            };
            Command command = json.readValue(body, target);
            if (command == null || !validator.validate(command).isEmpty() || !routingKey.equals(command.type())) {
                throw new InvalidReservationMessage();
            }
            if (command instanceof ReserveCommand reserve) {
                var variants = new HashSet<UUID>();
                for (var line : reserve.data().lines()) {
                    if (!variants.add(line.variantId())) {
                        throw new InvalidReservationMessage();
                    }
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
