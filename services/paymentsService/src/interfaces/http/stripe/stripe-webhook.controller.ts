import {
    BadRequestException,
    Controller,
    Headers,
    HttpCode,
    Post,
    Req,
    ServiceUnavailableException,
    UnsupportedMediaTypeException,
    type RawBodyRequest,
} from '@nestjs/common';
import {
    ApiBadRequestResponse,
    ApiBody,
    ApiConsumes,
    ApiHeader,
    ApiOkResponse,
    ApiOperation,
    ApiServiceUnavailableResponse,
    ApiTags,
} from '@nestjs/swagger';
import type { Request } from 'express';
import { ReceivePaymentNoticeService } from '../../../application/payments/receive-payment-notice.service';
import {
    PaymentPersistenceUnavailable,
    PaymentProviderMismatch,
    PaymentProviderUnavailable,
    PaymentRecoveryRequired,
} from '../../../application/payments/payment.error';
import { JsonLogger } from '../../../infrastructure/observability/json-logger.service';
import { InvalidStripeWebhook, StripeWebhookVerifier } from '../../../infrastructure/stripe/stripe-webhook.verifier';

@ApiTags('Stripe webhooks')
@Controller('webhooks/stripe')
export class StripeWebhookController {
    constructor(
        private readonly verifier: StripeWebhookVerifier,
        private readonly payments: ReceivePaymentNoticeService,
        private readonly logger: JsonLogger,
    ) {}

    @Post()
    @HttpCode(200)
    @ApiOperation({ summary: 'Receive signed Stripe test-mode PaymentIntent events' })
    @ApiConsumes('application/json')
    @ApiHeader({
        name: 'Stripe-Signature',
        required: true,
        description: 'Stripe signature of the original request body.',
    })
    @ApiBody({ schema: { type: 'object', additionalProperties: true } })
    @ApiOkResponse({ description: 'Committed, already processed, or an unrelated event ignored.' })
    @ApiBadRequestResponse({ description: 'Invalid signature or inconsistent financial evidence.' })
    @ApiServiceUnavailableResponse({
        description: 'Configuration or provider/database recovery is required; retry delivery.',
    })
    async receive(
        @Req() request: RawBodyRequest<Request>,
        @Headers('stripe-signature') signature: unknown,
    ): Promise<{ received: true }> {
        if (!request.is('application/json')) throw new UnsupportedMediaTypeException();
        try {
            const notice = this.verifier.verify(request.rawBody, signature);
            if (notice) {
                await this.payments.execute(notice);
                this.logger.log({ event: 'payments.webhook.processed', stripe_event_id: notice.eventId });
            }
            return { received: true };
        } catch (error) {
            if (error instanceof InvalidStripeWebhook || error instanceof PaymentProviderMismatch)
                throw new BadRequestException();
            if (
                error instanceof PaymentProviderUnavailable ||
                error instanceof PaymentPersistenceUnavailable ||
                error instanceof PaymentRecoveryRequired
            )
                throw new ServiceUnavailableException();
            throw error;
        }
    }
}
