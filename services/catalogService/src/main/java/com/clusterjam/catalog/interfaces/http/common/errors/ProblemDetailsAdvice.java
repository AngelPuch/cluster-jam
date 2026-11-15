package com.clusterjam.catalog.interfaces.http.common.errors;

import java.util.ArrayList;
import java.util.List;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.ServletWebRequest;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ProblemDetailsAdvice extends ResponseEntityExceptionHandler {

    private final ProblemDetailsMapper mapper;

    public ProblemDetailsAdvice(ProblemDetailsMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    protected ResponseEntity<Object> handleExceptionInternal(
        Exception exception,
        Object body,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request
    ) {
        if (request instanceof ServletWebRequest servlet && servlet.getResponse() != null
            && servlet.getResponse().isCommitted()) {
            return null;
        }
        HttpServletRequest httpRequest = ((ServletWebRequest) request).getRequest();
        if (exception instanceof MethodArgumentNotValidException invalid) {
            return convert(mapper.response(
                HttpStatus.UNPROCESSABLE_CONTENT, headers, httpRequest, fieldErrors(invalid)));
        }
        if (exception instanceof HandlerMethodValidationException invalid && !invalid.isForReturnValue()) {
            return convert(mapper.response(
                HttpStatus.UNPROCESSABLE_CONTENT, headers, httpRequest, List.of("Invalid request parameters.")));
        }
        return convert(mapper.response(status, headers, httpRequest, List.of()));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<?> unexpected(Exception exception, HttpServletRequest request) {
        return mapper.response(ProblemCode.INTERNAL_SERVER_ERROR, request);
    }

    private List<String> fieldErrors(MethodArgumentNotValidException exception) {
        List<String> messages = new ArrayList<>();
        for (FieldError error : exception.getBindingResult().getFieldErrors()) {
            if (error.getField().matches("[A-Za-z][A-Za-z0-9_.]{0,79}")) {
                messages.add(error.getField() + ": invalid value");
            }
        }
        if (messages.isEmpty()) {
            return List.of("Invalid request fields.");
        }
        return messages.stream().distinct().sorted().limit(20).toList();
    }

    private ResponseEntity<Object> convert(ResponseEntity<?> response) {
        return ResponseEntity.status(response.getStatusCode()).headers(response.getHeaders()).body(response.getBody());
    }
}
