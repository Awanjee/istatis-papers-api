from database import (
    get_products_with_pricing,
    get_pricing_for_product,
    get_dashboard_metrics,
)

print("=== Products ===")
products = get_products_with_pricing()
for p in products:
    print(f"{p['name']} — " f"{len(p['pricing_tiers'])} tiers")

print("\n=== Pricing test ===")
result = get_pricing_for_product("C4 Envelope", 7500)
print(result)

print("\n=== Metrics ===")
metrics = get_dashboard_metrics()
print(metrics)
