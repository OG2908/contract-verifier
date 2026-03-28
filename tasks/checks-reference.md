# Verification Checks Reference

## Cross-Document Checks (Reservation ↔ Contract)

| #  | Check | Source (Reservation) | Target (Contract) | Tolerance | Severity |
|----|-------|---------------------|--------------------|-----------|----------|
| 1  | Apartment number | paragraph 2: "דירה מספר X" | Appendix A: "מספר דירה" row | exact | error |
| 2  | Floor | paragraph 2: "בקומה/מפלס X" | Appendix A: "קומה" row | normalized text | error |
| 3  | Area (sqm) | paragraph 2: "שטח של כ- X מטר" | Appendix A: "שטח דירה" row | ±0.01 | error |
| 4  | Total price (with costs) | paragraph 2: "ובמחיר כולל של X" | Appendix A: "סכום הרכישה" | exact | error |
| 5  | Total price (with costs) | paragraph 2: "ובמחיר כולל של X" | Appendix D: "מחיר רכישה כולל" | exact | error |
| 6  | Registration fee | paragraph 3: "דמי רצינות בסך X" | Appendix D: "דמי הרשמה" | exact | error |
| 7  | Project name | paragraph 1: "בפרויקט X" | Appendix D header | contains | warning |
| 8  | Client name | page 2: "שם ושם משפחה" | Contract preamble | normalized | error |
| 9  | Client ID | page 2: "מס' ת.ז" | Contract preamble | exact | error |

## Internal Math Checks (Contract Only)

| #  | Check | Formula | Tolerance | Severity |
|----|-------|---------|-----------|----------|
| 10 | Each cost line amount | `total_price × line_pct / 100` | ±1€ | error |
| 11 | Total costs sum | `sum(cost_lines) == total_price × total_costs_pct / 100` | ±1€ | error |
| 12 | Price without costs | `price_with_costs - sum_of_costs == reservation.price_without_costs` | ±1€ | error |
| 13 | Remaining after registration | `total_price - registration_fee` | exact | error |
| 14 | Payment percentages | `sum(payment_pcts) == 100` | exact | error |
| 15 | Each payment base amount | `remaining × pct / 100` | ±1€ | error |
| 16 | Each payment surcharge amount | `base_amount × (1 + surcharge_pct/100)` | ±1€ | error |
| 17 | Total payments sum | `sum(base_amounts) == remaining` | ±1€ | error |

## Expected Values from Sample Documents

### Reservation (Apartment 1 — Kriopigi)
```
apartment_number:     1
floor:                קרקע
area_gross_sqm:       29.59
price_without_costs:  91,322
price_with_costs:     99,085
registration_fee:     2,000
project_name:         קריופיגי
client_name:          ורד יסעור
client_id:            28402808
```

### Contract (Apartment 6 — Kriopigi)
```
apartment_number:     6
floor:                קרקע
area_gross_sqm:       37.07
balcony_sqm:          7.19
total_purchase_price: 122,224
total_costs_pct:      8.5%
registration_fee:     2,000
remaining:            120,224
surcharge_pct:        2.0%

Cost breakdown:
  מס רכישה (3.09%)         = €3,481
  עו"ד מקומי (1.24%)       = €1,397
  נאמן ישראלי (1%)         = €1,126
  רישום בטאבו (1%)         = €1,126
  נוטריון יווני (1.5%)     = €1,690
  אגרות, מספר זיהוי (0.67%) = €755

Payment schedule:
  מקדמה      10%  €12,022  →  €12,263
  תשלום ראשון 50%  €60,112  →  €61,314
  תשלום שני   20%  €24,045  →  €24,526
  תשלום שלישי 20%  €24,045  →  €24,526
```

## Math Verification of Sample Contract

```
Costs check:
  3.09% of 122,224 = 3,776.72  BUT contract says 3,481 → ⚠️ costs appear to be calculated on base price, not total
  Need to determine: is the base for cost % the total price or the price-before-costs?

  If base = 112,650 (price without costs):
    3.09% × 112,650 = 3,480.89 ≈ 3,481 ✓
    1.24% × 112,650 = 1,396.86 ≈ 1,397 ✓
    1.00% × 112,650 = 1,126.50 ≈ 1,126 ✓ (rounded down)
    1.00% × 112,650 = 1,126.50 ≈ 1,126 ✓
    1.50% × 112,650 = 1,689.75 ≈ 1,690 ✓
    0.67% × 112,650 = 754.76   ≈ 755   ✓

  SUM of costs: 3,481 + 1,397 + 1,126 + 1,126 + 1,690 + 755 = 9,575
  122,224 - 9,575 = 112,649 ≈ 112,650 (rounding)

  ⚡ FINDING: Cost percentages are applied to PRICE WITHOUT COSTS, not total price.
  This is critical for the verification engine.

Payment check:
  Remaining: 122,224 - 2,000 = 120,224 ✓
  10% of 120,224 = 12,022.40 ≈ 12,022 ✓
  50% of 120,224 = 60,112.00 = 60,112 ✓
  20% of 120,224 = 24,044.80 ≈ 24,045 ✓
  20% of 120,224 = 24,044.80 ≈ 24,045 ✓
  Sum: 12,022 + 60,112 + 24,045 + 24,045 = 120,224 ✓

  Surcharge (2%):
  12,022 × 1.02 = 12,262.44 ≈ 12,263 ✓
  60,112 × 1.02 = 61,314.24 ≈ 61,314 ✓
  24,045 × 1.02 = 24,525.90 ≈ 24,526 ✓
  24,045 × 1.02 = 24,525.90 ≈ 24,526 ✓
```
