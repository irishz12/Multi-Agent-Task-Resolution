-- Synthetic seed data for AgentFlow Support.
-- Cases are intentionally not seeded; they are created at runtime.

-- Customers
INSERT INTO customers (id, name, email, created_at) VALUES
    (1001, 'Emma Carter',     'emma.carter@example.com',     '2026-06-01 09:00:00+00'),
    (1002, 'Liam Johnson',    'liam.johnson@example.com',    '2026-06-03 11:30:00+00'),
    (1003, 'Olivia Martinez', 'olivia.martinez@example.com', '2026-06-10 14:15:00+00'),
    (1004, 'Noah Thompson',   'noah.thompson@example.com',   '2026-06-15 08:45:00+00'),
    (1005, 'Ava Robinson',    'ava.robinson@example.com',    '2026-07-02 16:20:00+00'),
    (1006, 'William Clark',   'william.clark@example.com',   '2026-07-20 10:05:00+00');

-- Orders
-- 2001: damaged_order scenario   (status itself records the damage)
-- 2002: wrong_item scenario      (delivered_item differs from item_name)
-- 2003: missing_delivery scenario (order lost in transit)
-- 2004: normal delivered order, no issue
-- 2005: order still in transit, no issue yet
INSERT INTO orders (id, customer_id, item_name, status, delivered_item, delivery_date, created_at) VALUES
    (2001, 1001, 'Wireless Headphones',    'delivered_damaged', 'Wireless Headphones', '2026-08-01 12:00:00+00', '2026-07-28 09:00:00+00'),
    (2002, 1002, 'Bluetooth Speaker',      'delivered',   'USB-C Cable',    '2026-08-02 15:30:00+00', '2026-07-29 10:15:00+00'),
    (2003, 1003, 'Running Shoes - Size 10','lost',        NULL,             NULL,                     '2026-08-05 08:20:00+00'),
    (2004, 1004, 'Coffee Maker',           'delivered',   NULL,             '2026-08-05 13:00:00+00', '2026-08-01 09:30:00+00'),
    (2005, 1005, 'Yoga Mat',               'in_transit',  NULL,             NULL,                     '2026-08-18 11:00:00+00'),
    (2006, 1006, 'Desk Lamp',              'delivered',   NULL,             '2026-08-07 14:45:00+00', '2026-08-03 10:00:00+00'),
    (2007, 1001, 'Phone Case',             'delivered',   NULL,             '2026-08-10 16:10:00+00', '2026-08-06 09:00:00+00'),
    (2008, 1002, 'Kitchen Knife Set',      'in_transit',  NULL,             NULL,                     '2026-08-19 10:30:00+00'),
    (2009, 1003, 'Backpack',               'delivered',   NULL,             '2026-08-12 12:40:00+00', '2026-08-08 09:15:00+00');

-- Policies
INSERT INTO policies (id, issue_type, refund_allowed, replacement_allowed, max_resolution_days, description) VALUES
    (3001, 'damaged_order',    TRUE,  TRUE,  5, 'Customer received a damaged item; eligible for refund or replacement within 5 days of delivery.'),
    (3002, 'missing_delivery', TRUE,  FALSE, 7, 'Package was never delivered or lost in transit; eligible for refund within 7 days of the reported issue.'),
    (3003, 'wrong_item',       FALSE, TRUE,  5, 'Customer received an incorrect item; eligible for replacement with the correct item within 5 days.');
