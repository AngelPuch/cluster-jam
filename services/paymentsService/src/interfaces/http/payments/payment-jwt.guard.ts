import {
    Inject,
    Injectable,
    UnauthorizedException,
    ServiceUnavailableException,
    type CanActivate,
    type ExecutionContext,
} from '@nestjs/common';
import type { Request } from 'express';
import { PAYMENT_TOKEN_VERIFIER, type PaymentTokenVerifier } from '../../../application/ports/payment-access.port';
import { PaymentKeysUnavailable } from '../../../application/payments/payment-access.error';
export interface PaymentRequest extends Request {
    paymentBuyerId?: string;
}
@Injectable()
export class PaymentJwtGuard implements CanActivate {
    constructor(@Inject(PAYMENT_TOKEN_VERIFIER) private readonly verifier: PaymentTokenVerifier) {}
    async canActivate(context: ExecutionContext): Promise<boolean> {
        const request = context.switchToHttp().getRequest<PaymentRequest>();
        delete request.paymentBuyerId;
        const count = request.rawHeaders
            .filter((_, index) => index % 2 === 0)
            .filter((name) => name.toLowerCase() === 'authorization').length;
        const token =
            typeof request.headers.authorization === 'string'
                ? /^Bearer ([^\s]+)$/i.exec(request.headers.authorization)?.[1]
                : undefined;
        if (count !== 1 || !token || token.length > 16384) throw new UnauthorizedException();
        try {
            request.paymentBuyerId = await this.verifier.verify(token);
        } catch (error) {
            if (error instanceof PaymentKeysUnavailable) throw new ServiceUnavailableException();
            throw new UnauthorizedException();
        }
        return true;
    }
}
