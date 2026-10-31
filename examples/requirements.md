## Customers can pay by card

Priority: high
Tags: payments, checkout

A customer with items in the cart can pay with a valid credit card and receives
a confirmation.

Acceptance criteria:
- The card number is validated before the payment is sent.
- An approved payment shows an order confirmation.
- A declined payment shows a clear message and keeps the cart.

## Customers can pay by cash on delivery

Priority: medium
Tags: payments

A customer can choose to pay when the order is delivered.

Acceptance criteria:
- The cash option is offered only for supported regions.
- The order is created as pending payment.

## Customers receive a receipt by email

Priority: low
Tags: notifications

Acceptance criteria:
- The receipt is sent after an approved payment.
- The receipt lists the items and the total.
