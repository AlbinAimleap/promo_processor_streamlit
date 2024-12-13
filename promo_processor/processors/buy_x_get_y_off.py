from promo_processor.processor import PromoProcessor


class BuyGetDiscountProcessor(PromoProcessor):
    patterns = [
        r"Buy\s+(?P<quantity>\d+)\s+get\s+(?P<discount>\d+)%\s+off\b" 
    ]
    
    #"Buy 2 get 50% off"
    
    async def calculate_deal(self, item, match):
        """Calculate promotion price for 'Buy X get Y% off' promotions."""
        
        item_data = item.copy()
        price = item_data.get("sale_price") or item_data.get("regular_price", 0)
        quantity = int(match.group('quantity'))
        discount_percentage = int(match.group('discount')) 
        
        volume_deals_price = (price * quantity) - ((price * quantity) * (discount_percentage / 100))
        unit_price = volume_deals_price / quantity
        
        item_data['volume_deals_price'] = round(volume_deals_price, 2)
        item_data['unit_price'] = round(unit_price, 2)
        item_data['digital_coupon_price'] = ""
 
        return item_data

    async def calculate_coupon(self, item, match):
        """Calculate the final price after applying a coupon discount."""
        
        item_data = item.copy()
        price = item_data.get("sale_price") or item_data.get("regular_price", 0)
        quantity = int(match.group('quantity'))
        discount_percentage = int(match.group('discount')) 
        
        volume_deals_price = (price * quantity) - ((price * quantity) * (discount_percentage / 100))
        unit_price = volume_deals_price / quantity

        item_data['digital_coupon_price'] = round(volume_deals_price, 2)
        item_data['unit_price'] = round(unit_price, 2)
        
        return item_data