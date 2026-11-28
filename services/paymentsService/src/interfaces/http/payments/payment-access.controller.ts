import {
    Controller,
    Get,
    Param,
    ParseUUIDPipe,
    Req,
    UseGuards,
    NotFoundException,
    ConflictException,
    ServiceUnavailableException,
    UnauthorizedException,
} from '@nestjs/common';
import {
    ApiTags,
    ApiBearerAuth,
    ApiOkResponse,
    ApiUnauthorizedResponse,
    ApiNotFoundResponse,
    ApiConflictResponse,
    ApiServiceUnavailableResponse,
} from '@nestjs/swagger';
import { PaymentAccessService } from '../../../application/payments/payment-access.service';
import { PaymentNotFound, PaymentNotPayable } from '../../../application/payments/payment-access.error';
import {
    PaymentPersistenceUnavailable,
    PaymentProviderMismatch,
    PaymentProviderUnavailable,
} from '../../../application/payments/payment.error';
import { PaymentJwtGuard, type PaymentRequest } from './payment-jwt.guard';
@ApiTags('Payments')
@ApiBearerAuth()
@ApiUnauthorizedResponse({ description: 'A valid authenticated Supabase session is required.' })
@ApiNotFoundResponse({ description: 'No payment belongs to this buyer with that identifier.' })
@ApiServiceUnavailableResponse({
    description: 'Identity keys, persistence or Stripe access are temporarily unavailable.',
})
@UseGuards(PaymentJwtGuard)
@Controller('payments')
export class PaymentAccessController {
    constructor(private readonly payments: PaymentAccessService) {}
    private async response<T>(request: PaymentRequest, operation: (buyerId: string) => Promise<T>): Promise<T> {
        if (!request.paymentBuyerId) throw new UnauthorizedException();
        try {
            return await operation(request.paymentBuyerId);
        } catch (error) {
            if (error instanceof PaymentNotFound) throw new NotFoundException();
            if (error instanceof PaymentNotPayable) throw new ConflictException();
            if (
                error instanceof PaymentProviderUnavailable ||
                error instanceof PaymentPersistenceUnavailable ||
                error instanceof PaymentProviderMismatch
            )
                throw new ServiceUnavailableException();
            throw error;
        }
    }
    @Get(':paymentId')
    @ApiOkResponse({
        description: 'Owned payment status, server amount, currency and refund status.',
        schema: {
            type: 'object',
            required: ['paymentId', 'orderId', 'status', 'amountCents', 'currency', 'refundStatus'],
            properties: {
                paymentId: { type: 'string', format: 'uuid' },
                orderId: { type: 'string', format: 'uuid' },
                status: { type: 'string', enum: ['PENDIENTE', 'PAGADO', 'CANCELADO', 'REEMBOLSADO', 'FALLIDO'] },
                amountCents: { type: 'integer', minimum: 1 },
                currency: { type: 'string', enum: ['MXN'] },
                refundStatus: { type: 'string', nullable: true },
            },
        },
    })
    summary(@Param('paymentId', new ParseUUIDPipe()) id: string, @Req() request: PaymentRequest) {
        return this.response(request, (buyer) => this.payments.summary(id, buyer));
    }
    @Get(':paymentId/client-secret')
    @ApiOkResponse({
        description: 'Owner-only PaymentSheet access. Never persist or log the returned secret.',
        schema: {
            type: 'object',
            required: ['paymentId', 'clientSecret'],
            properties: { paymentId: { type: 'string', format: 'uuid' }, clientSecret: { type: 'string' } },
        },
    })
    @ApiConflictResponse({ description: 'The payment is not currently payable or its reservation expired.' })
    access(@Param('paymentId', new ParseUUIDPipe()) id: string, @Req() request: PaymentRequest) {
        return this.response(request, (buyer) => this.payments.access(id, buyer));
    }
}
