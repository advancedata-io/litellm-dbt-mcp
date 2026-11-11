select
    id                                   as payment_id,
    order_id,
    payment_method,
    toDecimal64(amount / 100, 2)         as amount
from {{ source('raw', 'payments') }}
