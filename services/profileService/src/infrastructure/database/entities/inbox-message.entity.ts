import { CreateDateColumn, Entity, PrimaryColumn, Column } from 'typeorm';

@Entity({ schema: 'app', name: 'inbox_messages' })
export class InboxMessageEntity {
    @PrimaryColumn({ name: 'event_id', type: 'uuid' })
    eventId!: string;

    @Column({ name: 'event_type', type: 'varchar', length: 100 })
    eventType!: string;

    @CreateDateColumn({ name: 'processed_at', type: 'timestamptz' })
    processedAt!: Date;
}
