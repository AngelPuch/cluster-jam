import {
    Column,
    CreateDateColumn,
    Entity,
    PrimaryColumn,
    UpdateDateColumn,
} from 'typeorm';

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
    })
    name!: string;

    @Column({
        type: 'varchar',
        length: 30,
        nullable: true,
    })
    phone!: string | null;

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
