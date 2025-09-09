"""
Menu Manager for FoodPollBot - handles menu items and poll data storage in MongoDB
"""
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from .mongo_storage import MongoStorage

logger = logging.getLogger(__name__)

class MenuManager:
    """Manages menu items and poll data using MongoDB storage"""
    
    def __init__(self, storage: MongoStorage):
        self.storage = storage
        self._categories = ["Первые блюда", "Вторые блюда", "Гарниры", "Салаты"]
    
    async def initialize_menu_from_json(self, schedule_file: str = "schedule.json") -> None:
        """Initialize menu items from schedule.json file"""
        try:
            with open(schedule_file, "r", encoding="utf-8") as file:
                schedule_data = json.load(file)
            
            logger.info("Loading menu items from schedule.json")
            
            # Collect all unique menu items by category
            menu_items_by_category = {category: set() for category in self._categories}
            
            # Process each day's polls
            for day_polls in schedule_data:
                for poll in day_polls:
                    category = poll.get("question", "")
                    options = poll.get("options", [])
                    
                    if category in menu_items_by_category:
                        for option in options:
                            menu_items_by_category[category].add(option)
            
            # Save menu items to MongoDB
            for category, items in menu_items_by_category.items():
                display_order = 1
                for item_name in sorted(items):
                    # Check if item already exists
                    existing_items = await self.storage.get_menu_items(
                        category=category, 
                        active_only=False
                    )
                    
                    item_exists = any(
                        item['name'] == item_name 
                        for item in existing_items
                    )
                    
                    if not item_exists:
                        await self.storage.save_menu_item(
                            category=category,
                            name=item_name,
                            display_order=display_order
                        )
                        logger.debug(f"Added menu item: {category} - {item_name}")
                    
                    display_order += 1
            
            logger.info("Menu initialization completed")
            
        except Exception as e:
            logger.error(f"Failed to initialize menu from JSON: {e}")
            raise
    
    async def get_menu_for_day(self, day_index: int) -> List[Dict]:
        """Get menu configuration for a specific day"""
        try:
            with open("schedule.json", "r", encoding="utf-8") as file:
                schedule_data = json.load(file)
            
            if 0 <= day_index < len(schedule_data):
                return schedule_data[day_index]
            else:
                logger.warning(f"Invalid day index: {day_index}")
                return []
                
        except Exception as e:
            logger.error(f"Failed to get menu for day {day_index}: {e}")
            return []
    
    async def save_poll_data(self, poll_id: str, category: str, poll_date: str,
                           question: str, options: List[str], votes: List[int]) -> None:
        """Save poll data to MongoDB"""
        try:
            # Save basic poll information
            await self.storage.save_poll(
                poll_id=poll_id,
                category=category,
                poll_date=poll_date,
                question=question,
                options=options,
                is_anonymous=False
            )
            
            # Update vote counts
            total_votes = sum(votes)
            await self.storage.update_poll_votes(
                poll_id=poll_id,
                option_votes=votes,
                total_votes=total_votes
            )
            
            logger.debug(f"Saved poll data: {poll_id} - {category}")
            
        except Exception as e:
            logger.error(f"Failed to save poll data: {e}")
    
    async def save_user_vote_data(self, poll_id: str, user_id: int, user_name: str,
                                option_indices: List[int], poll_date: str, 
                                category: str, options: List[str]) -> None:
        """Save user vote data and update combinations"""
        try:
            # Get chosen option texts
            chosen_texts = [options[i] for i in option_indices if i < len(options)]
            
            # Save individual vote
            await self.storage.save_user_vote(
                poll_id=poll_id,
                user_id=user_id,
                user_name=user_name,
                option_indices=option_indices,
                option_texts=chosen_texts
            )
            
            # Update user combinations for "Вторые блюда" and "Гарниры"
            if category in ["Вторые блюда", "Гарниры"]:
                await self.storage.update_user_combination(
                    date=poll_date,
                    user_id=user_id,
                    category=category,
                    choices=chosen_texts
                )
            
            logger.debug(f"Saved user vote: {user_id} - {poll_id}")
            
        except Exception as e:
            logger.error(f"Failed to save user vote data: {e}")
    
    async def get_poll_results_for_date(self, date: str) -> Dict[str, Any]:
        """Get comprehensive poll results for a specific date"""
        try:
            # Get all polls for the date
            polls = await self.storage.get_polls_by_date(date)
            
            # Get aggregated results
            poll_results = await self.storage.get_poll_results(date)
            
            result = {
                'date': date,
                'polls': {},
                'user_combinations': {}
            }
            
            # Process individual polls
            for poll in polls:
                category = poll['category']
                result['polls'][category] = {
                    'poll_id': poll['_id'],
                    'question': poll['question'],
                    'options': []
                }
                
                for option in poll['options']:
                    if option['voter_count'] > 0:  # Only include options with votes
                        result['polls'][category]['options'].append({
                            'text': option['text'],
                            'votes': option['voter_count']
                        })
            
            # Add user combinations
            if poll_results and 'user_combinations' in poll_results:
                result['user_combinations'] = poll_results['user_combinations']
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get poll results for date {date}: {e}")
            return {'date': date, 'polls': {}, 'user_combinations': {}}
    
    async def get_categories(self) -> List[str]:
        """Get list of available categories"""
        return self._categories.copy()
    
    async def get_active_menu_items(self, category: Optional[str] = None) -> List[Dict]:
        """Get active menu items, optionally filtered by category"""
        return await self.storage.get_menu_items(category=category, active_only=True)
    
    async def add_menu_item(self, category: str, name: str, description: str = "") -> str:
        """Add a new menu item"""
        if category not in self._categories:
            raise ValueError(f"Invalid category: {category}")
        
        # Get current max display order
        existing_items = await self.storage.get_menu_items(category=category)
        max_order = max([item.get('display_order', 0) for item in existing_items], default=0)
        
        return await self.storage.save_menu_item(
            category=category,
            name=name,
            description=description,
            display_order=max_order + 1
        )
    
    async def update_menu_item(self, item_id: str, **kwargs) -> bool:
        """Update an existing menu item"""
        return await self.storage.update_menu_item(item_id, **kwargs)
    
    async def deactivate_menu_item(self, item_id: str) -> bool:
        """Deactivate a menu item (soft delete)"""
        return await self.storage.update_menu_item(item_id, is_active=False)
    
    async def cleanup_old_data(self, days_to_keep: int = 30) -> None:
        """Clean up old poll data"""
        await self.storage.clear_old_data(days_to_keep)
        logger.info(f"Cleaned up data older than {days_to_keep} days")