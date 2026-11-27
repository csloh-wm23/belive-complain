# Customer records placeholder

Open **Customer records** in the staff sidebar. The live store starts empty. Nothing is seeded and no phone lookup, sales API or external database connection is enabled.

When company data is available, an administrator can save a customer ID, name, optional phone, tenancy reference and affected property/unit, plus its source. Use distinct tenancy references for multiple rentals under one customer ID. Review/edit updates require the latest version. An inactive record cannot be used by Hermes.

Choose a WhatsApp conversation and explicitly select the checked record for that support case. Hermes receives only the selected property reference, property name and room/unit; names and phone numbers remain in the staff interface. This is support context, not verified identity, company policy, refund approval or proof of a repair. A different location reported by the customer takes precedence. Property-specific SOP selection is unchanged and must still be scoped through the existing reviewed SOP controls.

Changing or deactivating a record invalidates its previous selection. Staff must check and select the updated version before it can be reused. Queued replies using obsolete facts are suppressed and regenerated through the normal sending checks. Ordinary support and greetings continue when no record is selected.

Records use the private local SQLite store (`customer_profile` objects). They are excluded from approved SOP/self-learning exports and public Git publication. Local database backups are separate. `LocalCustomerRecords` in `belive/customer_directory.py` is the replacement point for a future sales database adapter; do not connect one until its identifiers, access and update contract are agreed.

Tests use disposable databases only. `test_customer_directory.py` checks selection/version boundaries and stale sending; `browser_customer_records.py` checks the empty UI and record operations in a separate headless browser. Neither adds records to the live installation.
