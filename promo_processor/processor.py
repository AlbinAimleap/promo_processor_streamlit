import re
import json
import logging
import asyncio
from logging.handlers import RotatingFileHandler
from typing import Dict, Any, TypeVar, Union, List, Callable, Tuple
from pathlib import Path
from abc import ABC, abstractmethod
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import threading
import os

T = TypeVar("T", bound="PromoProcessor")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

handler = RotatingFileHandler('app.log', maxBytes=1000000, backupCount=10)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(handler)

class PromoProcessor(ABC):
    subclasses = []
    results = []
    _lock = threading.Lock()
    _thread_pool = ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 1) * 4))
    NUMBER_MAPPING = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9, "TEN": 10}
    _store_brands = {
        'marianos': frozenset(["Private Selection", "Kroger", "Simple Truth", "Simple Truth Organic"]),
        'target': frozenset(["Deal Worthy", "Good & Gather", "Market Pantry", "Favorite Day", "Kindfull", "Smartly", "Up & Up"]),
        'jewel': frozenset(['Lucerne', "Signature Select", "O Organics", "Open Nature", "Waterfront Bistro", "Primo Taglio",
                    "Soleil", "Value Corner", "Ready Meals"]),
        'walmart': frozenset(["Clear American", "Great Value", "Home Bake Value", "Marketside", 
                    "Co Squared", "Best Occasions", "Mash-Up Coffee", "World Table"])
    }
    _compiled_patterns = {}

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        PromoProcessor.subclasses.append(cls)
    
    def __init__(self) -> None:
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__name__)
        PromoProcessor.set_processor_precedence()
        self.update_save()

    @classmethod
    def apply(cls, func: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]) -> T:
        cls.results = func(cls.results)
        return cls

    def update_save(self):
        with open("patterns.json", "w") as f:
            patterns = [pattern for subclass in self.subclasses for pattern in subclass.patterns]
            json.dump(patterns, f, indent=4)

    @classmethod
    @lru_cache(maxsize=1024)
    def apply_store_brands(cls, product_title: str) -> str:
        title_lower = product_title.casefold()
        for brands in cls._store_brands.values():
            if any(brand.casefold() in title_lower for brand in brands):
                return "yes"
        return "no"

    @property
    @abstractmethod
    def patterns(self):
        pass

    @abstractmethod
    async def calculate_deal(self, item_data: Dict[str, Any], match: re.Match) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def calculate_coupon(self, item_data: Dict[str, Any], match: re.Match) -> Dict[str, Any]:
        pass

    @classmethod
    async def process_item(cls, item_data: Dict[str, Any]) -> T:
        if isinstance(item_data, list):
            loop = asyncio.get_event_loop()
            tasks = [loop.run_in_executor(cls._thread_pool, lambda x: asyncio.run(cls.process_single_item(x)), item) 
                    for item in item_data]
            processed_items = await asyncio.gather(*tasks)
            with cls._lock:
                cls.results.extend(processed_items)
        else:
            processed_item = await cls.process_single_item(item_data)
            with cls._lock:
                cls.results.append(processed_item)
        return cls

    @classmethod
    async def to_json(cls, filename: Union[str, Path]) -> None:
        if not isinstance(filename, Path):
            filename = Path(filename)
        filename = filename.with_suffix(".json") if not filename.suffix else filename
        filename.parent.mkdir(parents=True, exist_ok=True)
        
        def write_to_file():
            with open(filename, "w") as f:
                json.dump(cls.results, f, indent=4)
                
        await asyncio.get_event_loop().run_in_executor(cls._thread_pool, write_to_file)

    @classmethod
    def _get_compiled_pattern(cls, pattern: str) -> re.Pattern:
        if pattern not in cls._compiled_patterns:
            cls._compiled_patterns[pattern] = re.compile(pattern, re.IGNORECASE)
        return cls._compiled_patterns[pattern]

    @classmethod
    def find_best_match(cls, description: str, patterns: List[str]) -> Tuple[str, re.Match, int]:
        def process_pattern(pattern):
            compiled_pattern = cls._get_compiled_pattern(pattern)
            match = compiled_pattern.search(description)
            if match:
                score = cls.calculate_pattern_precedence(pattern)
                return pattern, match, score
            return pattern, None, -1

        results = list(cls._thread_pool.map(process_pattern, patterns))
        best_result = max(results, key=lambda x: x[2])
        return best_result

    @classmethod
    async def process_single_item(cls, item_data: Dict[str, Any]) -> Dict[str, Any]:
        updated_item = item_data.copy()
        if not hasattr(cls, "logger"):
            cls.logger = logging.getLogger(cls.__name__)

        sorted_processors = sorted(cls.subclasses, key=lambda x: getattr(x, 'PRECEDENCE', float('inf')))
        
        loop = asyncio.get_event_loop()
        
        async def process_description(desc, processor_type):
            if not desc:
                return None, None
                
            best_processor = None
            best_match = None
            best_score = -1
            
            async def check_processor(processor_class):
                processor = processor_class()
                pattern, match, score = await loop.run_in_executor(
                    cls._thread_pool, 
                    cls.find_best_match, 
                    desc, 
                    processor.patterns
                )
                return processor, match, score
            
            tasks = [check_processor(p) for p in sorted_processors]
            results = await asyncio.gather(*tasks)
            
            for processor, match, score in results:
                if match and score > best_score:
                    best_score = score
                    best_match = match
                    best_processor = processor
                    
            return best_processor, best_match

        # Process deals
        deals_desc = updated_item.get("volume_deals_description", "")
        best_deal_processor, best_deal_match = await process_description(deals_desc, "DEALS")
        
        if best_deal_processor and best_deal_match:
            cls.logger.info(f"DEALS: {best_deal_processor.__class__.__name__}: {deals_desc}")
            updated_item = await best_deal_processor.calculate_deal(updated_item, best_deal_match)
            if updated_item.get("sale_price") == updated_item.get("unit_price"):
                updated_item["volume_deals_description"] = ""
                updated_item["volume_deals_price"] = ""

        # Process coupons
        coupon_desc = updated_item.get("digital_coupon_description", "")
        best_coupon_processor, best_coupon_match = await process_description(coupon_desc, "COUPONS")
        
        if best_coupon_processor and best_coupon_match:
            cls.logger.info(f"COUPONS: {best_coupon_processor.__class__.__name__}: {coupon_desc}")
            updated_item = await best_coupon_processor.calculate_coupon(updated_item, best_coupon_match)

        updated_item["store_brand"] = await loop.run_in_executor(
            cls._thread_pool,
            cls.apply_store_brands,
            updated_item["product_title"]
        )
        return updated_item

    @staticmethod
    @lru_cache(maxsize=1024)
    def calculate_pattern_precedence(pattern: str) -> int:
        score = len(pattern) * 2
        score += len(re.findall(r'\((?!\?:).*?\)', pattern)) * 15
        score -= len(re.findall(r'[\*\+\?]', pattern)) * 8
        score -= len(re.findall(r'\{.*?\}', pattern)) * 6
        score -= len(re.findall(r'\.', pattern)) * 4
        score += len(re.findall(r'\[.*?\]', pattern)) * 5
        score += len(re.findall(r'\b', pattern)) * 3
        score += len(re.findall(r'\^|\$', pattern)) * 4
        score += len(re.findall(r'\(\?:.*?\)', pattern)) * 8
        return score

    @classmethod
    def set_processor_precedence(cls) -> None:
        for processor_class in cls.subclasses:
            processor_class.PRECEDENCE = max(
                (cls.calculate_pattern_precedence(pattern) for pattern in processor_class.patterns),
                default=0
            )

    @classmethod
    @lru_cache(maxsize=1024)
    def matcher(cls, description: str) -> str:
        def process_pattern(args):
            pattern, processor_class = args
            if cls._get_compiled_pattern(pattern).search(description):
                return pattern, cls.calculate_pattern_precedence(pattern)
            return None

        patterns = [(pattern, processor_class) 
                   for processor_class in cls.subclasses 
                   for pattern in processor_class.patterns]
        
        results = list(cls._thread_pool.map(process_pattern, patterns))
        valid_results = [r for r in results if r is not None]
        
        if not valid_results:
            return None
            
        return max(valid_results, key=lambda x: x[1])[0]