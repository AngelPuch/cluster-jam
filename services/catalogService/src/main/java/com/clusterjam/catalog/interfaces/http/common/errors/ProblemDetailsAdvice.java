package com.clusterjam.catalog.interfaces.http.common.errors;

import java.util.ArrayList;
import java.util.List;

import com.clusterjam.catalog.application.products.CatalogProductException;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.transaction.CannotCreateTransactionException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.ServletWebRequest;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;
import tools.jackson.core.exc.StreamConstraintsException;
import tools.jackson.databind.exc.UnrecognizedPropertyException;

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
        if (exception instanceof HttpMessageNotReadableException unreadable) {
            Throwable cause = unreadable.getMostSpecificCause();
            if (cause instanceof StreamConstraintsException) {
                return convert(mapper.response(HttpStatus.CONTENT_TOO_LARGE, headers, httpRequest, List.of()));
            }
            if (cause instanceof UnrecognizedPropertyException) {
                return convert(mapper.response(HttpStatus.UNPROCESSABLE_CONTENT, headers, httpRequest,
                    List.of("The request contains an unsupported field.")));
            }
        }
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

    @ExceptionHandler(CatalogProductException.class)
    public ResponseEntity<?> catalogProduct(CatalogProductException exception, HttpServletRequest request) {
        ProblemCode code = switch (exception.reason()) {
            case MISSING -> ProblemCode.NOT_FOUND;
            case DUPLICATE, INVALID_TRANSITION -> ProblemCode.CONFLICT;
            case INVALID_REFERENCE -> ProblemCode.UNPROCESSABLE_ENTITY;
            case STALE -> ProblemCode.PRECONDITION_FAILED;
        };
        return mapper.response(code, request);
    }

    @ExceptionHandler(OptimisticLockingFailureException.class)
    public ResponseEntity<?> concurrentEdit(HttpServletRequest request) {
        return mapper.response(ProblemCode.PRECONDITION_FAILED, request);
    }

    @ExceptionHandler({
        DataAccessResourceFailureException.class, TransientDataAccessException.class,
        CannotCreateTransactionException.class
    })
    public ResponseEntity<?> postgresUnavailable(HttpServletRequest request) {
        return mapper.response(ProblemCode.SERVICE_UNAVAILABLE, request);
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
