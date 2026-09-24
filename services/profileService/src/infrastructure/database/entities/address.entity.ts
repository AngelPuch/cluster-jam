import {
    Column,
    Entity,
    Index,
    JoinColumn,
    ManyToOne,
    PrimaryGeneratedColumn,
} from 'typeorm';

import { ProfileEntity } from './profile.entity';

@Entity({
    name: 'address',
    schema: 'app',
})
@Index('UQ_address_default_user', ['userId'], {
    unique: true,
    where: '"is_default" = true',
})
export class AddressEntity {
    @PrimaryGeneratedColumn('uuid')
    id!: string;

    @Column({
        name: 'user_id',
        type: 'uuid',
    })
    userId!: string;

    @ManyToOne(() => ProfileEntity, {
        nullable: false,
    })
    @JoinColumn({
        name: 'user_id',
        referencedColumnName: 'userId',
    })
    profile!: ProfileEntity;

    @Column({
        type: 'varchar',
        length: 40,
    })
    label!: string;

    @Column({
        type: 'varchar',
        length: 120,
    })
    recipient!: string;

    @Column({
        type: 'varchar',
        length: 160,
    })
    street!: string;

    @Column({
        name: 'exterior_number',
        type: 'varchar',
        length: 20,
    })
    exteriorNumber!: string;

    @Column({
        name: 'interior_number',
        type: 'varchar',
        length: 20,
        nullable: true,
    })
    interiorNumber!: string | null;

    @Column({
        type: 'varchar',
        length: 120,
    })
    neighborhood!: string;

    @Column({
        type: 'varchar',
        length: 120,
    })
    municipality!: string;

    @Column({
        type: 'varchar',
        length: 120,
    })
    state!: string;

    @Column({
        name: 'postal_code',
        type: 'varchar',
        length: 5,
    })
    postalCode!: string;

    @Column({
        type: 'char',
        length: 2,
    })
    country!: string;

    @Column({
        name: 'is_default',
        type: 'boolean',
        default: false,
    })
    isDefault!: boolean;
}
