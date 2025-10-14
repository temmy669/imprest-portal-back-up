# Dashboard Fixes TODO

## 1. Fix Weekly Expenses Query
- Correct syntax: Move store filter to `filter()` method
- Use `total_amount` instead of `amount`

## 2. Fix Top Weekly Expenses Query
- Use `ReimbursementItem` model for item names and totals
- Filter by user's assigned stores
- Aggregate by `item_name` and sum `item_total`

## 3. Implement Imprest Amount
- Calculate sum of `balance` from user's assigned stores

## 4. Fix Line Chart Data Query
- Filter by user's assigned stores
- Use `total_amount` for sum

## 5. Handle Weekly Income
- Determine source (e.g., PurchaseRequest approvals); currently hardcoded to 0

## 6. Add Store Filters Consistently
- Ensure all queries filter by `store__in=user.assigned_stores.all()`

## 7. Test and Validate
- Run tests to ensure queries work and data is accurate
- [x] Django check passed: System check identified no issues (0 silenced).
