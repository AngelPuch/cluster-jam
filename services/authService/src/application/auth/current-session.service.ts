import { Inject, Injectable } from '@nestjs/common';

import {
    CURRENT_SESSION_PORT,
    type CurrentIdentity,
    type CurrentSessionPort,
} from '../ports/current-session.port';

@Injectable()
export class CurrentSessionService {
    constructor(
        @Inject(CURRENT_SESSION_PORT)
        private readonly provider: CurrentSessionPort,
    ) {}

    getIdentity(accessToken: string): Promise<CurrentIdentity> {
        return this.provider.getCurrentIdentity(accessToken);
    }

    end(accessToken: string): Promise<void> {
        return this.provider.endCurrentSession(accessToken);
    }
}
