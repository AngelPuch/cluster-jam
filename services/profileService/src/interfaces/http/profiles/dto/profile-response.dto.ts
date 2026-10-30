import { ApiProperty } from '@nestjs/swagger';
import type { CustomerProfile } from '../../../../application/profile/profile';

export class ProfileResponseDto {
    @ApiProperty({ format: 'uuid', example: '11111111-1111-4111-8111-111111111111' })
    userId!: string;

    @ApiProperty({ type: String, nullable: true, maxLength: 120, example: 'María López' })
    fullName!: string | null;

    @ApiProperty({ type: String, nullable: true, maxLength: 30, example: '+52 55 1234 5678' })
    phone!: string | null;

    @ApiProperty({
        type: String,
        nullable: true,
        format: 'email',
        maxLength: 254,
        example: 'contact@example.com',
        description:
            'Null only for historical profiles predating contact email; new profiles have the registration contact email.',
    })
    contactEmail!: string | null;

    @ApiProperty({ enum: ['PENDING', 'COMPLETED'], example: 'COMPLETED' })
    onboardingStatus!: 'PENDING' | 'COMPLETED';

    @ApiProperty({ format: 'date-time', example: '2026-10-29T18:00:00.000Z' })
    createdAt!: string;

    @ApiProperty({ format: 'date-time', example: '2026-10-29T18:05:00.000Z' })
    updatedAt!: string;

    static from(profile: CustomerProfile): ProfileResponseDto {
        return {
            userId: profile.userId,
            fullName: profile.fullName,
            phone: profile.phone,
            contactEmail: profile.contactEmail,
            onboardingStatus: profile.onboardingStatus,
            createdAt: profile.createdAt.toISOString(),
            updatedAt: profile.updatedAt.toISOString(),
        };
    }
}
