import { Column, CreateDateColumn, Entity, PrimaryColumn, UpdateDateColumn } from 'typeorm';

export enum OnboardingStatus {
    PENDING = 'PENDING',
    COMPLETED = 'COMPLETED',
}

@Entity({
    name: 'profile',
    schema: 'app',
})
export class ProfileEntity {
    @PrimaryColumn({
        name: 'user_id',
        type: 'uuid',
    })
    userId!: string;

    @Column({
        type: 'varchar',
        length: 120,
        nullable: true,
    })
    name!: string | null;

    @Column({
        type: 'varchar',
        length: 30,
        nullable: true,
    })
    phone!: string | null;

    @Column({
        name: 'contact_email',
        type: 'varchar',
        length: 254,
        nullable: true,
    })
    contactEmail!: string | null;

    @Column({
        name: 'onboarding_status',
        type: 'varchar',
        length: 20,
        default: OnboardingStatus.PENDING,
    })
    onboardingStatus!: OnboardingStatus;

    @CreateDateColumn({
        name: 'created_at',
        type: 'timestamptz',
    })
    createdAt!: Date;

    @UpdateDateColumn({
        name: 'updated_at',
        type: 'timestamptz',
    })
    updatedAt!: Date;
}
