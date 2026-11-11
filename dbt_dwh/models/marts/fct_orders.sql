{{
    config(
        order_by='(order_date, order_id)',
        partition_by='toYYYYMM(order_date)',
        tags=['finance']
    )
}}

{% set payment_methods = ['credit_card', 'ideal', 'bank_transfer', 'gift_card'] %}

with orders as (
    select * from {{ ref('stg_orders') }}
),

payments as (
    select * from {{ ref('stg_payments') }}
),

order_payments as (
    select
        order_id,
        {% for method in payment_methods -%}
        sumIf(amount, payment_method = '{{ method }}') as {{ method }}_amount,
        {% endfor -%}
        sum(amount) as total_amount
    from payments
    group by order_id
)

select
    {{ dbt_utils.generate_surrogate_key(['orders.order_id', 'orders.customer_id']) }} as order_key,
    orders.order_id,
    orders.customer_id,
    orders.order_date,
    orders.status,
    {% for method in payment_methods -%}
    order_payments.{{ method }}_amount,
    {% endfor -%}
    order_payments.total_amount as amount
from orders
left join order_payments
    on orders.order_id = order_payments.order_id
