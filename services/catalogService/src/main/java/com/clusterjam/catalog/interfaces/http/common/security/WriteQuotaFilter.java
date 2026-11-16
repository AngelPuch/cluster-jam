package com.clusterjam.catalog.interfaces.http.common.security;

import java.io.IOException;
import java.time.Duration;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.filter.OncePerRequestFilter;

final class WriteQuotaFilter extends OncePerRequestFilter {

    private static final Set<String> WRITES = Set.of("POST", "PUT", "PATCH", "DELETE");
    private static final long WINDOW_NANOS = Duration.ofMinutes(1).toNanos();

    private final int writesPerMinute;
    private final long maxJsonBytes;
    private final SecurityProblemHandlers problems;
    private final Cache<String, Window> quotas = Caffeine.newBuilder()
        .maximumSize(2000)
        .expireAfterAccess(Duration.ofMinutes(2))
        .build();

    WriteQuotaFilter(int writesPerMinute, long maxJsonBytes, SecurityProblemHandlers problems) {
        this.writesPerMinute = writesPerMinute;
        this.maxJsonBytes = maxJsonBytes;
        this.problems = problems;
    }

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain
    ) throws ServletException, IOException {
        var authentication = SecurityContextHolder.getContext().getAuthentication();
        if (WRITES.contains(request.getMethod()) && authentication instanceof JwtAuthenticationToken token) {
            String mediaType = request.getContentType();
            if (mediaType != null && mediaType.toLowerCase(Locale.ROOT).contains("json")
                && request.getContentLengthLong() > maxJsonBytes) {
                problems.write(request, response, HttpStatus.CONTENT_TOO_LARGE);
                return;
            }
            String identity = token.getToken().getIssuer() + "|" + token.getName();
            long now = System.nanoTime();
            Window window = quotas.asMap().compute(identity, (key, current) -> advance(current, now));
            if (window.count() > writesPerMinute) {
                long seconds = TimeUnit.NANOSECONDS.toSeconds(Math.max(0, window.endsAt() - now)) + 1;
                response.setHeader(HttpHeaders.RETRY_AFTER, Long.toString(Math.min(60, seconds)));
                problems.write(request, response, HttpStatus.TOO_MANY_REQUESTS);
                return;
            }
        }
        chain.doFilter(request, response);
    }

    private Window advance(Window current, long now) {
        if (current == null || now - current.endsAt() >= 0) {
            return new Window(now + WINDOW_NANOS, 1);
        }
        return new Window(current.endsAt(), Math.min(current.count() + 1, writesPerMinute + 1));
    }

    private record Window(long endsAt, int count) {
    }
}
