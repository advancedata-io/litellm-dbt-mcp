select
    id                       as order_id,
    customer_id,
    toDate(order_date)       as order_date,
    lower(status)            as status
from {{ source('raw', 'orders') }}
