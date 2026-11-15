package com.clusterjam.catalog.interfaces.http.common.errors;

import java.util.List;

import jakarta.servlet.RequestDispatcher;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.webmvc.error.ErrorController;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
public class ProblemErrorController implements ErrorController {

    private final ProblemDetailsMapper mapper;

    public ProblemErrorController(ProblemDetailsMapper mapper) {
        this.mapper = mapper;
    }

    @RequestMapping("/error")
    public ResponseEntity<ProblemDetail> error(HttpServletRequest request) {
        Object attribute = request.getAttribute(RequestDispatcher.ERROR_STATUS_CODE);
        int status = attribute instanceof Integer number && number >= 400 && number <= 599 ? number : 404;
        return mapper.response(HttpStatusCode.valueOf(status), HttpHeaders.EMPTY, request, List.of());
    }
}
