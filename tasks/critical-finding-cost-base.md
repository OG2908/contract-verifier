# Critical Finding: Cost Percentage Base

## Discovery

While verifying the sample contract math, I found that the cost percentages in Appendix A are NOT applied to the total price (כולל עלויות). They are applied to the **price before costs** (the base purchase price).

## Proof

Total price with costs: €122,224
If costs (8.5%) were on total: 8.5% × 122,224 = €10,389
Actual costs sum: €9,575

Working backwards:
122,224 - 9,575 = 112,649 (price without costs)
9,575 / 112,649 = 8.50% ✓

Checking individual lines against base price 112,649:
- 3.09% × 112,649 = 3,480.85 → contract says 3,481 ✓
- 1.24% × 112,649 = 1,396.85 → contract says 1,397 ✓
- 1.00% × 112,649 = 1,126.49 → contract says 1,126 ✓
- 1.50% × 112,649 = 1,689.74 → contract says 1,690 ✓
- 0.67% × 112,649 = 754.75  → contract says 755   ✓

## Impact on Verification Logic

The formula for CHECK 10 (cost line amounts) must be:

```python
# WRONG — would fail verification
expected = total_price_with_costs * line_pct / 100

# CORRECT
price_without_costs = total_price_with_costs / (1 + total_costs_pct / 100)
expected = price_without_costs * line_pct / 100
```

Or equivalently, derive `price_without_costs` from the reservation agreement, which states it explicitly (e.g., "במחיר רכישה של 91,322 אירו").

## Rule

**Always use `reservation.price_without_costs` as the base for verifying cost line amounts.** The contract's "סכום הרכישה" is the sum (base + costs), not the base.
