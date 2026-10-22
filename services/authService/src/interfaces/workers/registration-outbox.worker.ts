import {
    Injectable,
    Logger,
    OnApplicationBootstrap,
    OnModuleDestroy,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

import { PublishRegistrationEventsService } from '../../application/events/publish-registration-events.service';

@Injectable()
export class RegistrationOutboxWorker
    implements OnApplicationBootstrap, OnModuleDestroy
{
    private readonly logger = new Logger(RegistrationOutboxWorker.name);
    private timer?: ReturnType<typeof setTimeout>;
    private running?: Promise<void>;
    private stopped = false;

    constructor(
        private readonly config: ConfigService,
        private readonly publisher: PublishRegistrationEventsService,
    ) {}

    onApplicationBootstrap(): void {
        if (this.config.getOrThrow<boolean>('OUTBOX_PUBLISHER_ENABLED'))
            this.schedule(0);
    }

    private schedule(delay: number): void {
        if (this.stopped) return;
        this.timer = setTimeout(() => {
            this.running = this.tick();
        }, delay);
    }

    private async tick(): Promise<void> {
        try {
            await this.publisher.execute(10, () => this.stopped);
        } catch {
            this.logger.warn({
                event: 'auth.outbox.poll.failed',
                code: 'OUTBOX_UNAVAILABLE',
            });
        } finally {
            this.schedule(1_000);
        }
    }

    async onModuleDestroy(): Promise<void> {
        this.stopped = true;
        clearTimeout(this.timer);
        await this.running;
    }
}
