from promo_processor.processor import PromoProcessor


class AddTotalForOfferProcessor(PromoProcessor):
    patterns = [r"Add\s+(?P<quantity>\d+)\s+Total\s+For\s+Offer"]
    
    
    # Example: "Add 2 Total For Offer"

    async def calculate_deal(self, item, match):
        item_data = item.copy()
        quantity = int(match.group('quantity'))
        unit_price = item_data.get("sale_price") or item_data.get("regular_price", 0)
        
        item_data['volume_deals_price'] = round(unit_price * quantity, 2)
        item_data['unit_price'] = round(unit_price, 2)
        item_data['digital_coupon_price'] = ""
        return item_data

    async def calculate_coupon(self, item, match):
        item_data = item.copy()
        quantity = int(match.group('quantity'))
        unit_price = item_data.get("unit_price") or item_data.get("sale_price") or item_data.get("regular_price", 0)
        
        item_data['digital_coupon_price'] = round(unit_price * quantity, 2)
        item_data['unit_price'] = round(unit_price, 2)
        return item_data